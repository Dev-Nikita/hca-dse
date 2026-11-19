"""E6: analytical model vs. discrete-event simulation (accuracy and ranking)."""
import sys, os, csv, random, statistics, json; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.setrecursionlimit(10000)
from hcadse.model import make_space, WORKLOADS
from hcadse.evaluate import evaluate
from hcadse.simulate import simulate
from hcadse.search import hca_dse, structurally_valid
from scipy.stats import spearmanr

rows = []; raw_samples = []
sp = make_space("S2")
for name, wl in WORKLOADS.items():
    rng = random.Random(7)
    front = [x for x, _ in hca_dse(sp, wl).front]
    pool = [x for x in sp.enumerate() if structurally_valid(x) and evaluate(x, wl).feasible]
    rng.shuffle(pool)
    selected = front[:20] + pool
    seen = set(); sel = []
    for x in selected:
        key = tuple(x.values())
        if key not in seen:
            seen.add(key); sel.append(x)
        if len(sel) == 40: break
    an, sm = [], []
    for idx, x in enumerate(sel):
        L = evaluate(x, wl).objectives[0]
        reps = [simulate(x, wl, n_req=3000, seed=s)["mean"] for s in range(5)]
        raw_samples.append(dict(workload=name, design_index=idx, design={k:getattr(v,"name",v) for k,v in x.items()}, mean_by_seed=reps))
        m = statistics.median(reps)
        if not (m < float("inf")):
            continue
        an.append(L); sm.append(m)
        rows.append(dict(workload=name,design_index=idx, L_analytical=round(L, 6), L_sim=round(m, 6),
                         rel_err=round((L - m) / m, 4)))
    mape = 100 * statistics.mean(abs((a - s) / s) for a, s in zip(an, sm))
    rho = spearmanr(an, sm).correlation
    print(f"{name}: n={len(an)} MAPE={mape:.1f}% Spearman rho={rho:.3f}", flush=True)
with open("results/e6_simvalidation.csv", "w", newline="") as f:
    w = csv.DictWriter(f, sorted(rows[0])); w.writeheader(); w.writerows(rows)
print("written results/e6_simvalidation.csv")

with open("results/e6_samples.json", "w") as f: json.dump(raw_samples,f,indent=2)
