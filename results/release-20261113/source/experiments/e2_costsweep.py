"""Cost projections from repeated search overheads and persisted DES timing samples."""
import sys,csv,json,time,random,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hcadse.model import make_space,WORKLOADS
from hcadse.search import exhaustive,hca_dse,structurally_valid
from hcadse.evaluate import evaluate
from hcadse.simulate import simulate
sp=make_space('S1');wl=WORKLOADS['telemetry']
pool=[x for x in sp.enumerate() if structurally_valid(x) and evaluate(x,wl).feasible]
random.Random(11).shuffle(pool);samples=[]
for i,x in enumerate(pool[:40]):
 start=time.perf_counter();result=simulate(x,wl,n_req=3000,warmup=400,seed=i)
 elapsed=time.perf_counter()-start
 samples.append(dict(sample=i,seconds=elapsed,n_req=3000,warmup=400,seed=i,
   design={k:getattr(v,'name',v) for k,v in x.items()},result=result))
ce=statistics.mean(r['seconds'] for r in samples)
Path('results/e2_des_timing.json').write_text(json.dumps(dict(scale='S1',workload='telemetry',
 selection_seed=11,mean_seconds=ce,median_seconds=statistics.median(r['seconds'] for r in samples),
 samples=samples),indent=2))
rows=[]
for scale in ['S2','S3']:
 for name,wl in WORKLOADS.items():
  sp=make_space(scale);hs=[];es=[]
  for _ in range(3):hs.append(hca_dse(sp,wl));es.append(exhaustive(sp,wl))
  h,e=hs[0],es[0]
  assert len({r.n_evaluated for r in hs})==len({r.n_evaluated for r in es})==1
  oh=statistics.median(r.runtime-r.t_eval for r in hs);oe=statistics.median(r.runtime-r.t_eval for r in es)
  for cost in sorted(set([1e-6,1e-5,5e-5,1e-4,5e-4,1e-3,5e-3,ce,.1,1.0])):
   th,te=oh+h.n_evaluated*cost,oe+e.n_evaluated*cost
   rows.append(dict(scale=scale,workload=name,C_E=cost,N_hca=h.n_evaluated,N_exh=e.n_evaluated,
    overhead_hca=oh,overhead_exh=oe,T_hca=th,T_exh=te,speedup=te/th))
  print(scale,name,'DES seconds',ce,'projected speedup',(oe+e.n_evaluated*ce)/(oh+h.n_evaluated*ce),flush=True)
with open('results/e2_costsweep.csv','w') as f:
 w=csv.DictWriter(f,rows[0]);w.writeheader();w.writerows(rows)
