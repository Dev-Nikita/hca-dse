// Generic compute node of the edge/gateway/cloud testbed.
//
// Wire format:  [4-byte big-endian plan length][plan JSON][payload padding]
// A node pops the first step of the plan, burns the prescribed amount of CPU
// work, and forwards the remainder of the plan (with the next payload) to the
// next host. The design under test is fully described by the plan, so the same
// binary serves every tier.
package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

type Step struct {
	Host    string  `json:"host"`     // where this step executes
	WorkMI  float64 `json:"work_mi"`  // computational work [MI]
	PayInMB float64 `json:"pay_mb"`   // payload carried INTO this step [MB]
}

type Plan struct {
	Steps []Step `json:"steps"`
}

var (
	opsPerSec float64
	client    = &http.Client{Timeout: 60 * time.Second, Transport: &http.Transport{
		MaxIdleConns: 2048, MaxIdleConnsPerHost: 2048, IdleConnTimeout: 90 * time.Second,
		DisableCompression: true}}
	mips      float64
)

// calibrate measures the iteration rate of the burn loop on this container.
func calibrate() float64 {
	const n = 20_000_000
	t0 := time.Now()
	burnIters(n)
	return float64(n) / time.Since(t0).Seconds()
}

//go:noinline
func burnIters(n int) {
	x := 1.000001
	for i := 0; i < n; i++ {
		x = x*1.0000001 + 1e-9
		if x > 1e6 {
			x = 1.000001
		}
	}
	sink = x
}

var sink float64

// burn consumes CPU work equivalent to `mi` million instructions at `mips`.
func burn(mi float64) {
	seconds := mi / mips
	burnIters(int(seconds * opsPerSec))
}

func handle(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil || len(body) < 4 {
		http.Error(w, "bad request", 400)
		return
	}
	n := binary.BigEndian.Uint32(body[:4])
	var p Plan
	if err := json.Unmarshal(body[4:4+n], &p); err != nil {
		http.Error(w, "bad plan", 400)
		return
	}
	if len(p.Steps) == 0 {
		w.WriteHeader(200)
		return
	}
	cur := p.Steps[0]
	burn(cur.WorkMI)
	rest := Plan{Steps: p.Steps[1:]}
	if len(rest.Steps) == 0 {
		w.WriteHeader(200)
		w.Write([]byte("ok"))
		return
	}
	next := rest.Steps[0]
	buf, _ := json.Marshal(rest)
	out := make([]byte, 4+len(buf)+int(next.PayInMB*1e6))
	binary.BigEndian.PutUint32(out[:4], uint32(len(buf)))
	copy(out[4:], buf)
	resp, err := client.Post("http://"+next.Host+"/step", "application/octet-stream",
		bytes.NewReader(out))
	if err != nil {
		http.Error(w, "downstream: "+err.Error(), 502)
		return
	}
	io.Copy(io.Discard, resp.Body)
	resp.Body.Close()
	w.WriteHeader(resp.StatusCode)
}

func main() {
	mips, _ = strconv.ParseFloat(os.Getenv("MIPS"), 64)
	if mips == 0 {
		mips = 6000
	}
	opsPerSec = calibrate()
	log.Printf("node role=%s mips=%.0f calibrated=%.3e ops/s", os.Getenv("ROLE"), mips, opsPerSec)
	http.HandleFunc("/step", handle)
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
