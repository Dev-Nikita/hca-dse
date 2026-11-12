"""Gate 10 runner: executes every selected architecture on Docker and records
measured end-to-end latency.

  python3 testbed/run_testbed.py --repeats 3            # all 36 designs
  python3 testbed/run_testbed.py --workload control     # one workload only

Each design becomes a generated docker-compose topology (n_e edge containers,
n_g gateways, one cloud), each container pinned to one CPU and shaped with
`tc netem` according to the link class of the design.
"""
import argparse, json, os, shutil, subprocess, sys, time, csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TB = os.path.join(ROOT, "testbed")
RUN = os.path.join(TB, "run")
IMAGE = "hcadse-testbed:latest"


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, text=True, capture_output=True, **kw)


def compose_for(d, cpus="1.0"):
    def node(name, role, mips, delay, rate):
        return f"""  {name}:
    image: {IMAGE}
    command: ["node"]
    environment:
      ROLE: {role}
      MIPS: "{mips:.0f}"
      NETEM_DELAY: "{delay:.3f}"
      NETEM_RATE: "{rate:.0f}"
    cap_add: ["NET_ADMIN"]
    cpus: "{cpus}"
"""
    s = "services:\n"
    for i in range(d["n_e"]):
        s += node(f"edge{i+1}", "edge", d["mips"]["edge"], d["link"]["delay_ms"], d["link"]["rate_mbit"])
    for i in range(d["n_g"]):
        s += node(f"gw{i+1}", "gw", d["mips"]["gw"], d["link"]["delay_ms"], d["link"]["rate_mbit"])
    s += node("cloud1", "cloud", d["mips"]["cloud"], d["wan"]["delay_ms"], d["wan"]["rate_mbit"])
    s += f"""  loadgen:
    image: {IMAGE}
    command: ["loadgen"]
    environment:
      SPEC: /spec/spec.json
      OUT: /out/result.json
    volumes:
      - ./spec:/spec
      - ./out:/out
    depends_on: [{", ".join([f"edge{i+1}" for i in range(d['n_e'])] +
                            [f"gw{i+1}" for i in range(d['n_g'])] + ["cloud1"])}]
"""
    return s


def spec_for(d):
    return {"design": d["design"], "entry": d["entry"], "rep": d["rep"],
            "steps": d["steps"], "lambda": d["lambda_"], "n_req": d["n_req"],
            "warmup": d["warmup"], "first_pay_mb": d["first_pay_mb"],
            "sync_mb": d["sync_mb"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=RUN)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--workload", default=None)
    ap.add_argument("--designs", default=os.path.join(TB, "specs/designs.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results/e9_testbed.csv"))
    a = ap.parse_args()
    run_dir = os.path.abspath(a.run_dir)

    if sh("docker info").returncode != 0:
        sys.exit("Docker is not running. Start Docker Desktop and retry.")
    print("building image ...", flush=True)
    b = sh(f'docker build -q -t {IMAGE} "{TB}"')
    if b.returncode != 0:
        sys.exit(b.stderr[-2000:])

    designs = json.load(open(a.designs))

    rows = []
    if os.path.exists(a.out):
        rows = list(csv.DictReader(open(a.out)))
    t_start = time.time()
    for i, d in enumerate(designs):
        if a.workload and d["workload"] != a.workload:
            continue
        for rep in range(a.repeats):
            key = f"{d['workload']}|{i}|{rep}"
            if any(r.get("key") == key for r in rows):
                continue
            shutil.rmtree(run_dir, ignore_errors=True)
            os.makedirs(os.path.join(run_dir, "spec")); os.makedirs(os.path.join(run_dir, "out"))
            open(os.path.join(run_dir, "compose.yml"), "w").write(compose_for(d))
            json.dump(spec_for(d), open(os.path.join(run_dir, "spec/spec.json"), "w"))
            t0 = time.time()
            r = sh(f'docker compose -f "{run_dir}/compose.yml" up --abort-on-container-exit '
                   f'--exit-code-from loadgen --quiet-pull', cwd=run_dir, timeout=a.timeout)
            res_path = os.path.join(run_dir, "out/result.json")
            ok = r.returncode == 0 and os.path.exists(res_path)
            res = json.load(open(res_path)) if ok else {}
            sh(f'docker compose -f "{run_dir}/compose.yml" down -v --remove-orphans')
            if not ok:
                sys.exit("Testbed failed: " + r.stderr[-2000:])
            row = dict(key=key, workload=d["workload"], kind=d["kind"], design_idx=i, repeat=rep,
                       n_e=d["n_e"], n_g=d["n_g"], policy=d["design"]["policy"],
                       rep_factor=d["rep"], edge_cls=d["design"]["edge_cls"],
                       link_cls=d["design"]["link_cls"], L_analytical=d["L_analytical"],
                       mean=res.get("mean"), p50=res.get("p50"), p95=res.get("p95"),
                       p99=res.get("p99"), n=res.get("n"), errors=res.get("errors"),
                       wall=round(time.time() - t0, 1), ok=ok)
            rows.append(row)
            with open(a.out, "w", newline="") as f:
                w = csv.DictWriter(f, sorted(rows[0])); w.writeheader(); w.writerows(rows)
            print(f"[{len(rows)}] {d['workload']}/{d['kind']} n_e={d['n_e']} rep{rep}: "
                  f"model={d['L_analytical']*1000:.1f}ms measured p50="
                  f"{(res.get('p50') or float('nan'))*1000:.1f}ms "
                  f"({row['wall']}s)", flush=True)
    print(f"done in {(time.time()-t_start)/60:.1f} min -> {a.out}")


if __name__ == "__main__":
    main()
