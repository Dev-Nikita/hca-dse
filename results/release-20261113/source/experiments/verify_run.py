"""Validate a canonical run, including fresh search counters and baseline calls."""
import csv,json,sys,statistics,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from hcadse.search import hca_dse
from hcadse.model import make_space,WORKLOADS
from scipy.stats import mannwhitneyu
r=Path(sys.argv[1]);read=lambda n:list(csv.DictReader((r/n).open()))
e1=read('e1_pruning.csv')
for x in e1:
 h=hca_dse(make_space(x['scale']),WORKLOADS[x['workload']])
 assert (h.n_evaluated,h.n_nodes)==(int(x['evals']),int(x['nodes'])),x
 assert sum(int(x[k]) for k in ['pruned_struct','pruned_bound','pruned_dom','evals'])==int(x['raw'])
 if x['scale']!='S4':assert x['exact']=='True' and float(x['recall'])==float(x['prec'])==1
print('Fresh-process E1 counters and funnel conservation: PASS')
e3=read('e3_baselines.csv')
for x in e3:
 if x['method'] in ['random','nsga2']:
  assert int(x['n_eval'])==int(x['full_evaluator_calls'])==int(x['budget'])
  assert int(x['proposal_count'])==int(x['budget'])+int(x['structural_rejections'])
  assert 0<=int(x['feasibility_rejections'])<=int(x['budget'])
for x in read('e8_stats.csv'):
 groups=[[float(y['hv_ratio']) for y in e3 if all(y[k]==x[k] for k in ['scale','workload','budget']) and y['method']==m] for m in ['nsga2','random']]
 a,b=groups;assert len(a)==len(b)==20
 assert abs(mannwhitneyu(a,b,alternative='greater').pvalue-float(x['p_nsga2_gt_random']))<5.1e-7
 delta=sum((u>v)-(u<v) for u in a for v in b)/400
 assert abs(delta-float(x['cliffs_delta']))<.00051
print('960 stochastic runs: full-call budgets and 24 statistical comparisons: PASS')
for n in ['e4_ablation.csv','e10_order.csv','e11_solver.csv','e12_symbolic.csv']:
 assert all(x['exact']=='True' for x in read(n)),n
for x in read('e2_costsweep.csv'):
 h=next(y for y in e1 if all(x[k]==y[k] for k in ['scale','workload']))
 assert int(x['N_hca'])==int(h['evals']) and int(x['N_exh'])==int(h['exh_evals'])
 assert math.isclose(float(x['speedup']),float(x['T_exh'])/float(x['T_hca']),rel_tol=1e-12)
des=json.loads((r/'e2_des_timing.json').read_text());assert len(des['samples'])==40
assert math.isclose(des['mean_seconds'],statistics.mean(x['seconds'] for x in des['samples']),rel_tol=1e-12)
print('Exactness, cost projection and persisted DES timing: PASS')
