// Closed-loop-free (open) load generator: Poisson arrivals at rate lambda,
// one goroutine per request, end-to-end latency percentiles per configuration.
package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"io"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"sort"
	"sync"
	"time"
)

type Step struct {
	Host    string   `json:"host"`
	Hosts   []string `json:"hosts,omitempty"` // replicas of this tier
	WorkMI  float64  `json:"work_mi"`
	PayInMB float64  `json:"pay_mb"`
}

// planFor resolves each stage to one replica, round-robin over request index,
// so that every replica of a tier receives its share of the load.
func planFor(steps []Step, i int) []Step {
	out := make([]Step, len(steps))
	for k, s := range steps {
		h := s.Host
		if len(s.Hosts) > 0 {
			h = s.Hosts[i%len(s.Hosts)]
		}
		out[k] = Step{Host: h, WorkMI: s.WorkMI, PayInMB: s.PayInMB}
	}
	return out
}

type Spec struct {
	Design   map[string]interface{} `json:"design"`
	Entry    []string               `json:"entry"` // replicas receiving stage 1
	Rep      int                    `json:"rep"`   // replication factor of stage 1 only
	Steps    []Step                 `json:"steps"` // [stage1, stage2, stage3]
	Lambda   float64                `json:"lambda"`
	NReq     int                    `json:"n_req"`
	Warmup   int                    `json:"warmup"`
	FirstPay float64                `json:"first_pay_mb"`
	SyncMB   float64                `json:"sync_mb"` // replica synchronisation payload
}

// encode builds the wire message for a plan and an inbound payload size.
func encode(steps []Step, payMB float64) []byte {
	p := struct {
		Steps []Step `json:"steps"`
	}{steps}
	buf, _ := json.Marshal(p)
	out := make([]byte, 4+len(buf)+int(payMB*1e6))
	binary.BigEndian.PutUint32(out[:4], uint32(len(buf)))
	copy(out[4:], buf)
	return out
}

func main() {
	raw, err := os.ReadFile(os.Getenv("SPEC"))
	if err != nil {
		log.Fatal(err)
	}
	var s Spec
	if err := json.Unmarshal(raw, &s); err != nil {
		log.Fatal(err)
	}
	client := &http.Client{Timeout: 120 * time.Second, Transport: &http.Transport{
		MaxIdleConns: 4096, MaxIdleConnsPerHost: 4096, IdleConnTimeout: 90 * time.Second,
		DisableCompression: true}}
	// wait for the topology to come up
	for _, h := range s.Entry {
		for i := 0; i < 120; i++ {
			if r, e := client.Get("http://" + h + "/health"); e == nil {
				r.Body.Close()
				break
			}
			time.Sleep(500 * time.Millisecond)
		}
	}
	rng := rand.New(rand.NewSource(42))
	lat := make([]float64, 0, s.NReq)
	var mu sync.Mutex
	var wg sync.WaitGroup
	var errs int
	post := func(host string, body []byte) bool {
		resp, err := client.Post("http://"+host+"/step", "application/octet-stream",
			bytes.NewReader(body))
		if err != nil {
			return false
		}
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		return resp.StatusCode == 200
	}
	start := time.Now()
	for i := 0; i < s.NReq; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			plan := planFor(s.Steps, i)
			t0 := time.Now()
			// stage 1 runs on `Rep` distinct replicas in parallel; the
			// synchronisation payload rides along with each replica
			stage1 := []Step{{Host: plan[0].Host, WorkMI: plan[0].WorkMI}}
			pay := s.FirstPay + float64(s.Rep-1)*s.SyncMB
			var swg sync.WaitGroup
			bad := false
			for r := 0; r < s.Rep; r++ {
				swg.Add(1)
				go func(r int) {
					defer swg.Done()
					h := s.Entry[(i+r)%len(s.Entry)]
					if !post(h, encode([]Step{{Host: h, WorkMI: stage1[0].WorkMI}}, pay)) {
						bad = true
					}
				}(r)
			}
			swg.Wait()
			// the remainder of the chain is executed once
			if !bad && !post(plan[1].Host, encode(plan[1:], plan[1].PayInMB)) {
				bad = true
			}
			d := time.Since(t0).Seconds()
			mu.Lock()
			if bad {
				errs++
			} else if i >= s.Warmup {
				lat = append(lat, d)
			}
			mu.Unlock()
		}(i)
		time.Sleep(time.Duration(rng.ExpFloat64() / s.Lambda * float64(time.Second)))
	}
	wg.Wait()
	sort.Float64s(lat)
	q := func(p float64) float64 {
		if len(lat) == 0 {
			return math.NaN()
		}
		return lat[int(p*float64(len(lat)-1))]
	}
	mean := 0.0
	for _, v := range lat {
		mean += v
	}
	if len(lat) > 0 {
		mean /= float64(len(lat))
	}
	out := map[string]interface{}{
		"design": s.Design, "n": len(lat), "errors": errs,
		"mean": mean, "p50": q(0.5), "p95": q(0.95), "p99": q(0.99),
		"wall": time.Since(start).Seconds(),
	}
	b, _ := json.MarshalIndent(out, "", " ")
	out_path := os.Getenv("OUT")
	if out_path == "" {
		out_path = "/out/result.json"
	}
	os.WriteFile(out_path, b, 0644)
	os.Stdout.Write(b)
}
