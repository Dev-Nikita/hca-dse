"""E3: budget-matched comparison with random search and NSGA-II (20 seeds)."""
import sys, os, csv, statistics; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcadse.model import make_space, WORKLOADS
from hcadse.search import exhaustive, hca_dse, random_search
from hcadse.baselines import nsga2
from hcadse.metrics import recall, hypervolume, igd_plus, bounds_from, objset

SEEDS = range(20)
rows = []
SCALES = [sys.argv[1]] if len(sys.argv) > 1 else ["S2", "S3"]
WLS = [sys.argv[2]] if len(sys.argv) > 2 else list(WORKLOADS)
for scale in SCALES:
    sp = make_space(scale)
    for name in WLS:
        wl = WORKLOADS[name]
        ref = exhaustive(sp, wl)
        h = hca_dse(sp, wl)
        lo, hi = bounds_from(ref.front)
        hv_ref = hypervolume(ref.front, lo, hi)
        def add(method, budget, fr, ne, t, seed=None, counters=None):
            counters = counters or {}
            rows.append(dict(proposal_count=counters.get("proposal_count", ne),
                             structural_rejections=counters.get("structural_rejections", 0),
                             feasibility_rejections=counters.get("feasibility_rejections", 0),
                             full_evaluator_calls=ne,scale=scale, workload=name, method=method, budget=budget,
                             seed=seed, n_eval=ne, runtime=round(t, 4),
                             recall=round(recall(fr, ref.front), 4),
                             hv_ratio=round(hypervolume(fr, lo, hi) / hv_ref, 4) if hv_ref else 0,
                             igd_plus=round(igd_plus(fr, ref.front, lo, hi), 5)))
        add("exhaustive", ref.n_evaluated, ref.front, ref.n_evaluated, ref.runtime)
        add("HCA-DSE", h.n_evaluated, h.front, h.n_evaluated, h.runtime)
        for B in (100, 250, 500, 1000):
            for s in SEEDS:
                r = random_search(sp, wl, B, seed=s); add("random", B, r.front, r.n_evaluated, r.runtime, s, vars(r))
                g = nsga2(sp, wl, B, seed=s);        add("nsga2",  B, g.front, g.n_evaluated, g.runtime, s, vars(g))
            for m in ("random", "nsga2"):
                sel = [r for r in rows if r["method"] == m and r["budget"] == B
                       and r["scale"] == scale and r["workload"] == name and r["seed"] is not None]
                print(f"{scale}/{name} {m} B={B}: recall med={statistics.median(r['recall'] for r in sel):.3f} "
                      f"HV med={statistics.median(r['hv_ratio'] for r in sel):.3f} "
                      f"IGD+ med={statistics.median(r['igd_plus'] for r in sel):.4f}", flush=True)
        print(f"{scale}/{name} HCA-DSE: n_eval={h.n_evaluated} recall=1.0 (exact={objset(h.front)==objset(ref.front)})", flush=True)
out = f"results/e3_{SCALES[0]}_{WLS[0]}.csv" if len(sys.argv) > 2 else "results/e3_baselines.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, sorted(rows[0])); w.writeheader(); w.writerows(rows)
print("written", out)
