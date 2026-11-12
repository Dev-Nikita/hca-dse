"""Exact Z3 baseline on a fully evaluated finite table, including table construction cost.

No continuous linearisation or rounding: integer objective ranks preserve the
strict ordering of the stored binary64 values. This is an exact table baseline,
not a compact symbolic reformulation and not an evaluator-saving competitor.
"""
import sys,time,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import z3
from hcadse.model import make_space,WORKLOADS
from hcadse.search import structurally_valid,exhaustive
from hcadse.evaluate import evaluate
from hcadse.metrics import objset
rows=[]
for scale in ['S1','S2']:
 for name,wl in WORKLOADS.items():
  start=time.perf_counter();sp=make_space(scale);points=[];ne=0
  for x in sp.enumerate():
   if not structurally_valid(x):continue
   result=evaluate(x,wl);ne+=1
   if result.feasible:points.append((x,result.objectives))
  table_time=time.perf_counter()-start
  unique=sorted({f for _,f in points})
  values=[sorted({f[i] for f in unique}) for i in range(4)]
  ranks=[{v:j for j,v in enumerate(vs)} for vs in values]
  rankvec=[tuple(ranks[i][f[i]] for i in range(4)) for f in unique]
  obj=z3.Ints('L E C D');solver=z3.Solver();solver.set(timeout=60000,random_seed=0)
  solver.add(z3.Or([z3.And([obj[i]==f[i] for i in range(4)]) for f in rankvec]))
  front=[];calls=0
  def check():
   global calls
   calls+=1;r=solver.check()
   if r==z3.unknown:raise RuntimeError(solver.reason_unknown())
   return r
  while check()==z3.sat:
   p=tuple(solver.model()[v].as_long() for v in obj)
   solver.push()
   while True:
    solver.add(z3.And([obj[i]<=p[i] for i in range(4)]),z3.Or([obj[i]<p[i] for i in range(4)]))
    if check()==z3.unsat:break
    p=tuple(solver.model()[v].as_long() for v in obj)
   solver.pop();front.append(tuple(values[i][p[i]] for i in range(4)))
   solver.add(z3.Or([obj[i]<p[i] for i in range(4)]))
  total=time.perf_counter()-start
  ref=exhaustive(sp,wl)
  assert set(front)=={f for _,f in ref.front}
  assert objset([(None,f) for f in front])==objset(ref.front)
  row=dict(scale=scale,workload=name,full_evaluator_calls=ne,feasible_rows=len(points),
    table_seconds=table_time,total_seconds=total,solver_and_encoding_seconds=total-table_time,
    solver_checks=calls,pareto=len(objset(ref.front)),exact=True)
  rows.append(row);print(row,flush=True)
with open('results/e11_solver.csv','w') as f:
 w=csv.DictWriter(f,rows[0]);w.writeheader();w.writerows(rows)
