"""E7: does a one-parameter calibration of the analytical latency help? (holdout)"""
import sys, os, csv, statistics, random; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from scipy.stats import spearmanr
rows = list(csv.DictReader(open("results/e6_simvalidation.csv")))
out = []
for wl in sorted({r["workload"] for r in rows}):
    d = [(float(r["L_analytical"]), float(r["L_sim"])) for r in rows if r["workload"] == wl]
    rng = random.Random(3); rng.shuffle(d)
    k = int(0.5 * len(d)); tr, te = d[:k], d[k:]
    A = np.array([[a, 1.0] for a, _ in tr]); y = np.array([s for _, s in tr])
    (a_, b_), *_ = np.linalg.lstsq(A, y, rcond=None)
    raw = 100 * statistics.mean(abs((a - s) / s) for a, s in te)
    cal = 100 * statistics.mean(abs((a_ * a + b_ - s) / s) for a, s in te)
    rho = spearmanr([a for a, _ in te], [s for _, s in te]).correlation
    out.append(dict(workload=wl, n_test=len(te), a=round(float(a_), 4), b=round(float(b_), 6),
                    MAPE_raw=round(raw, 1), MAPE_calibrated=round(cal, 1), spearman_test=round(rho, 3)))
    print(out[-1], flush=True)
with open("results/e7_calibration.csv", "w", newline="") as f:
    w = csv.DictWriter(f, sorted(out[0])); w.writeheader(); w.writerows(out)
