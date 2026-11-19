"""E4: contribution of each pruning layer."""
import sys, os, csv; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcadse.model import make_space, WORKLOADS
from hcadse.search import exhaustive, hca_dse
from hcadse.metrics import objset, recall

VARIANTS = {"structural-only": dict(use_bounds=False, use_dominance=False),
            "struct+feasibility": dict(use_bounds=True, use_dominance=False),
            "struct+dominance": dict(use_bounds=False, use_dominance=True),
            "HCA-full": dict(use_bounds=True, use_dominance=True)}
rows = []
for scale in ("S2", "S3"):
    sp = make_space(scale)
    for name, wl in WORKLOADS.items():
        ref = exhaustive(sp, wl)
        for vn, kw in VARIANTS.items():
            h = hca_dse(sp, wl, **kw)
            rows.append(dict(scale=scale, workload=name, variant=vn, nodes=h.n_nodes,
                             evals=h.n_evaluated, t=round(h.runtime, 4),
                             recall=round(recall(h.front, ref.front), 4),
                             exact=objset(h.front) == objset(ref.front)))
            print(rows[-1], flush=True)
with open("results/e4_ablation.csv", "w", newline="") as f:
    w = csv.DictWriter(f, sorted(rows[0])); w.writeheader(); w.writerows(rows)
print("written results/e4_ablation.csv")
