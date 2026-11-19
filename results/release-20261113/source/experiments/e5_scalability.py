"""E5: scalability to 10^7 logical designs (the space is never materialised)."""
import sys, os, csv, tracemalloc; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcadse.model import (DesignSpace, EDGE_CLASSES, GW_CLASSES, CLOUD_CLASSES,
                          LINK_CLASSES, POLICIES, WORKLOADS)
from hcadse.search import hca_dse
from hcadse.metrics import objset

def space_of(n_edge, n_gw, n_rep):
    return DesignSpace(list(range(2, 2 + n_edge)), EDGE_CLASSES,
                       sorted({1 + i for i in range(n_gw)}), GW_CLASSES,
                       LINK_CLASSES, CLOUD_CLASSES, list(range(1, 1 + n_rep)),
                       list(POLICIES))

CONFS = [(3, 2, 2), (6, 3, 3), (24, 5, 4), (80, 8, 5), (200, 16, 8),
         (600, 24, 10), (1600, 40, 12)]
rows = []
for ne, ng, nr in CONFS:
    sp = space_of(ne, ng, nr)
    for name, wl in WORKLOADS.items():
        tracemalloc.start()
        h = hca_dse(sp, wl)
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        rows.append(dict(raw=sp.size, workload=name, nodes=h.n_nodes,
                         evals=h.n_evaluated, pareto=len(objset(h.front)),
                         runtime=round(h.runtime, 4), peak_kib=round(peak / 1024, 1),
                         visited_frac=h.n_nodes / sp.size))
        print(rows[-1], flush=True)
with open("results/e5_scalability.csv", "w", newline="") as f:
    w = csv.DictWriter(f, sorted(rows[0])); w.writeheader(); w.writerows(rows)
print("written results/e5_scalability.csv")
