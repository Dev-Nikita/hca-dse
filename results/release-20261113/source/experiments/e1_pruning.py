"""E1: pruning funnel + exactness across scales and workloads."""
import sys, os, csv, json; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcadse.model import make_space, WORKLOADS
from hcadse.search import exhaustive, hca_dse
from hcadse.metrics import objset, recall, precision

rows = []
fronts = {}
for scale in ("S1", "S2", "S3", "S4"):
    sp = make_space(scale)
    for name, wl in WORKLOADS.items():
        h = hca_dse(sp, wl)
        fronts[scale+"/"+name] = [list(f) for _,f in h.front]
        row = dict(scale=scale, workload=name, raw=sp.size, nodes=h.n_nodes,
                   pruned_struct=h.pruned_structural, pruned_bound=h.pruned_bound,
                   pruned_dom=h.pruned_dominance, evals=h.n_evaluated,
                   feasible=h.n_feasible, pareto=len(objset(h.front)),
                   t_hca=round(h.runtime, 4), t_bounds=round(h.t_bounds, 4),
                   t_dom=round(h.t_dominance, 4), t_eval=round(h.t_eval, 4))
        if scale != "S4":
            e = exhaustive(sp, wl)
            assert {f for _,f in h.front} == {f for _,f in e.front}, "Raw binary64 fronts differ"
            row.update(exh_evals=e.n_evaluated, t_exh=round(e.runtime, 4),
                       recall=round(recall(h.front, e.front), 6),
                       prec=round(precision(h.front, e.front), 6),
                       exact=objset(h.front) == objset(e.front),
                       speedup=round(e.runtime / h.runtime, 2))
        rows.append(row); print(row, flush=True)
keys = sorted({k for r in rows for k in r})
with open("results/e1_pruning.csv", "w", newline="") as f:
    w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(rows)
print("written results/e1_pruning.csv")

with open("results/e1_fronts.json", "w") as f: json.dump(fronts,f,indent=2)
