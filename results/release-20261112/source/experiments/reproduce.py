"""Create a clean source export, execute experiments, and seal checksummed results.

A release path is never overwritten. Timings are measurements and not expected
to be bit-identical; discrete results are verified across independent runs.
"""
import argparse,datetime,hashlib,json,os,platform,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--release',default='v1.2-canonical-order');ap.add_argument('--testbed',type=Path);a=ap.parse_args()
 release=ROOT/'results'/a.release
 if (release/'manifest.json').exists() or (release/'source').exists():raise SystemExit('Refusing to overwrite an existing run; choose a new --release')
 source=release/'source';source.mkdir(parents=True);(source/'results').mkdir();(release/'logs').mkdir(exist_ok=True)
 for folder in ['hcadse','experiments','tests','configs']:
  if (ROOT/folder).exists():
   shutil.copytree(ROOT/folder,source/folder,ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copytree(ROOT/'testbed',source/'testbed',ignore=shutil.ignore_patterns('run','run-round2','bin','__pycache__'))
 shutil.copyfile(ROOT/'requirements-lock.txt',source/'requirements-lock.txt')
 shutil.copyfile(ROOT/'Makefile',source/'Makefile')
 source_hashes={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()}
 env=dict(os.environ,PYTHONHASHSEED='0',MPLCONFIGDIR='/private/tmp/hcadse-mpl',XDG_CACHE_HOME='/private/tmp/hcadse-cache',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 scripts=['tests/test_core.py','tests/test_regression.py','tests/test_pruning_safety.py','tests/test_revision.py',
 'experiments/e1_pruning.py','experiments/e2_costsweep.py','experiments/e3_baselines.py','experiments/e4_ablation.py',
 'experiments/e5_scalability.py','experiments/e6_simvalidation.py','experiments/e7_calibration.py','experiments/e8_stats.py',
 'experiments/e10_order.py','experiments/e11_solver.py','experiments/e12_symbolic.py']
 for script in scripts:
  print('RUN',script,flush=True)
  with (release/'logs'/(Path(script).stem+'.log')).open('w') as log:
   subprocess.run([sys.executable,script],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
 # Re-run deterministic search counters from a new interpreter, without comparing wall times.
 subprocess.run([sys.executable,str(ROOT/'experiments/verify_run.py'),str(source/'results')],cwd=source,env=env,check=True)
 data=release/'data';shutil.copytree(source/'results',data)
 if a.testbed:
  shutil.copyfile(a.testbed.resolve(),data/'e9_testbed_round2.csv')
  for metric,tag in [('p50','docker'),('mean','mean')]:
   subprocess.run([sys.executable,'testbed/analyze.py','--input',str(data/'e9_testbed_round2.csv'),
    '--designs','testbed/specs/designs.json','--tag',tag,'--metric',metric,'--output-dir',str(data),
    '--figure-dir',str(release/'validation-figures')],cwd=source,env=env,check=True)
  # decision reliability needs the per-design deployment summary written just above
  subprocess.run([sys.executable,'experiments/e13_reliability.py'],cwd=source,
   env=dict(env,HCADSE_RESULTS=str(data)),check=True)

 manifest=dict(release=a.release,started_utc=start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 python=sys.version,platform=platform.platform(),machine=platform.machine(),processor=platform.processor(),
 git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 source_sha256=source_hashes,data_sha256={p.name:sha(p) for p in data.iterdir() if p.is_file()},
 packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
 testbed_provenance=({'image_id':'sha256:a19f9e9bff01108fb9bc651d105797b5b1e134a2c68d8cc8b1af5ada0026ca25','independent_round':2,'model_frozen_before_round':True} if a.testbed else None),
 timing_policy='Single sequential computational run; wall time and traced memory may vary. Three repetitions for cost and order experiments.')
 (release/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print('SEALED',release,flush=True)
if __name__=='__main__':main()
