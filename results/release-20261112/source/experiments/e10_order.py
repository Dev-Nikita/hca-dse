"""O1/O2 x queue on/off; timed run is separate from instrumentation."""
import sys,csv,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hcadse.model import make_space,WORKLOADS,VAR_ORDER,ORDER_DETERMINANTS_LAST
from hcadse.search import hca_dse,exhaustive
from hcadse.metrics import objset
# "determinants-early" is the canonical order used everywhere else in the paper;
# "determinants-late" assigns replication and placement policy last.
ORDERS=[('determinants-early',VAR_ORDER),('determinants-late',ORDER_DETERMINANTS_LAST)]
rows=[]
for scale in ['S1','S2','S3']:
 for w,wl in WORKLOADS.items():
  sp=make_space(scale);reference=exhaustive(sp,wl).front;ref=objset(reference)
  for name,order in ORDERS:
   for queue in [False,True]:
    runs=[hca_dse(sp,wl,variable_order=order,use_queue_bound=queue) for _ in range(3)]
    h=hca_dse(sp,wl,variable_order=order,use_queue_bound=queue,measure_queue=True)
    assert all(objset(r.front)==ref for r in runs+[h])
    assert all({f for _,f in r.front}=={f for _,f in reference} for r in runs+[h])
    assert len({(r.n_nodes,r.n_evaluated) for r in runs+[h]})==1
    row=dict(scale=scale,workload=w,order=name,queue=queue,nodes=h.n_nodes,
      bound_calls=h.n_bound_calls,evals=h.n_evaluated,partial_queue_active=h.queue_active_partial,
      partial_queue_pruned=h.queue_pruned_partial,runtime=statistics.median(r.runtime for r in runs),exact=True)
    rows.append(row);print(row,flush=True)
with open('results/e10_order.csv','w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
