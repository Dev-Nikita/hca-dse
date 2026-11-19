"""E8: non-parametric statistics over the 20 NSGA-II/random seeds."""
import sys, os, csv, statistics; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scipy.stats import mannwhitneyu

def cliffs_delta(a, b):
    gt = sum(1 for x in a for y in b if x > y); lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (len(a) * len(b))

rows = list(csv.DictReader(open("results/e3_baselines.csv")))
out = []
for scale in sorted({r["scale"] for r in rows}):
    for wl in sorted({r["workload"] for r in rows}):
        sub = [r for r in rows if r["scale"] == scale and r["workload"] == wl]
        hca = [r for r in sub if r["method"] == "HCA-DSE"][0]
        for B in sorted({int(r["budget"]) for r in sub if r["seed"]}):
            g = [float(r["hv_ratio"]) for r in sub if r["method"] == "nsga2" and int(r["budget"]) == B]
            rd = [float(r["hv_ratio"]) for r in sub if r["method"] == "random" and int(r["budget"]) == B]
            u, p = mannwhitneyu(g, rd, alternative="greater")
            out.append(dict(scale=scale, workload=wl, budget=B,
                            nsga2_hv_med=round(statistics.median(g), 4),
                            nsga2_hv_iqr=round(statistics.quantiles(g)[2] - statistics.quantiles(g)[0], 4),
                            random_hv_med=round(statistics.median(rd), 4),
                            p_nsga2_gt_random=round(float(p), 6),
                            cliffs_delta=round(cliffs_delta(g, rd), 3),
                            nsga2_recall_med=round(statistics.median(
                                float(r["recall"]) for r in sub if r["method"] == "nsga2"
                                and int(r["budget"]) == B), 3),
                            hca_n_eval=int(hca["n_eval"]), hca_recall=1.0))
            print(out[-1], flush=True)
with open("results/e8_stats.csv", "w", newline="") as f:
    w = csv.DictWriter(f, sorted(out[0])); w.writeheader(); w.writerows(out)
