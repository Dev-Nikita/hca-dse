"""E13: how far can a model-based design decision be trusted?

For every pair of deployed architectures of the same workload, the analytical model
predicts which of the two is faster. This script reports the share of pairs whose
measured order (mean latency over three runs, the main-text metric) matches the predicted
order, as a function of how far apart the model places the two architectures. No model
parameter is fitted here: predictions come from the model frozen before deployment.
Pairs are counted within workloads only; the pooled figure sums within-workload pairs.
Pairs share architectures and are not independent, so intervals come from a cluster
bootstrap at architecture level: within each workload the architectures are resampled
with replacement, the eligible pairs are rebuilt from the resample (two copies of the
same architecture never form a pair), and the pooled agreement is recomputed; 95%
percentile intervals over 10,000 replicates, fixed seed.
"""
import csv, math, os, sys, random
THRESHOLDS = [0.0, 0.05, 0.10, 0.15, 0.25, 0.50, 1.00]
OUT_DIR = os.environ.get('HCADSE_RESULTS', 'results')
SRC = OUT_DIR + '/e9_per_design_mean.csv'

def counts(sub, thr):
    ok = tot = 0
    for i in range(len(sub)):
        for j in range(i + 1, len(sub)):
            a, b = sub[i], sub[j]
            if a is b:
                continue
            la, lb = float(a['L_analytical']), float(b['L_analytical'])
            if abs(la - lb) / min(la, lb) <= thr:
                continue
            tot += 1
            ok += (la - lb) * (float(a['p50_measured']) - float(b['p50_measured'])) > 0
    return ok, tot

rows = list(csv.DictReader(open(SRC)))
wls = sorted({r['workload'] for r in rows})
B = 10000
rng = random.Random(20260921)
out = []
for subset, keep in (('all', lambda r: True), ('reproducible', lambda r: float(r['spread']) < 1.5)):
    groups = {w: [r for r in rows if r['workload'] == w and keep(r)] for w in wls}
    for thr in THRESHOLDS:
        pooled_ok = pooled_tot = 0
        for w in wls:
            ok, tot = counts(groups[w], thr)
            pooled_ok += ok; pooled_tot += tot
            out.append(dict(subset=subset, threshold=thr, workload=w, agree=ok, pairs=tot,
                            agreement=round(ok / tot, 4) if tot else '', ci_low='', ci_high=''))
        boots = []
        for _ in range(B):
            k = n = 0
            for w in wls:
                g = groups[w]
                sample = [g[rng.randrange(len(g))] for _ in g]
                a, t = counts(sample, thr)
                k += a; n += t
            if n:
                boots.append(k / n)
        boots.sort()
        lo = boots[int(0.025 * len(boots))]; hi = boots[int(0.975 * len(boots)) - 1]
        out.append(dict(subset=subset, threshold=thr, workload='pooled', agree=pooled_ok, pairs=pooled_tot,
                        agreement=round(pooled_ok / pooled_tot, 4) if pooled_tot else '',
                        ci_low=round(lo, 4), ci_high=round(hi, 4)))
with open(OUT_DIR + '/e13_reliability.csv', 'w', newline='') as f:
    w_ = csv.DictWriter(f, list(out[0])); w_.writeheader(); w_.writerows(out)
for r in out:
    if r['workload'] == 'pooled':
        print(r)
print('written', OUT_DIR + '/e13_reliability.csv')
