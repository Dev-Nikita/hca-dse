"""Gate 10 analysis: accuracy (MAPE) and, more importantly, ranking agreement."""
import sys, os, csv, json, statistics, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, kendalltau

ap = argparse.ArgumentParser()
ap.add_argument("--input", default="results/e9_testbed_local.csv")
ap.add_argument("--designs", default="testbed/specs/designs_local.json")
ap.add_argument("--tag", default="local")
ap.add_argument("--output-dir", default="results")
ap.add_argument("--figure-dir", default="figures")
ap.add_argument("--metric", choices=["p50", "mean"], default="p50")
a = ap.parse_args()
os.makedirs(a.output_dir, exist_ok=True)
os.makedirs(a.figure_dir, exist_ok=True)

designs = json.load(open(a.designs))
rows = list(csv.DictReader(open(a.input)))
assert rows and all(r["ok"] == "True" and int(r.get("errors") or 0) == 0 for r in rows), "Incomplete or failed testbed runs must not be silently discarded"
by = {}
for r in rows:
    by.setdefault((r["workload"], int(r["design_idx"])), []).append(r)

out = []
for (w, i), rs in sorted(by.items()):
    assert len(rs) == 3, (w, i, len(rs))
    med = statistics.median(float(r[a.metric]) for r in rs)
    p95 = statistics.median(float(r["p95"]) for r in rs)
    d = [x for x in designs if x["workload"] == w][0] if False else designs[i]
    rho = max(d["rho"].values())
    out.append(dict(workload=w, design=i, kind=rs[0]["kind"], policy=rs[0]["policy"],
                    n_e=rs[0]["n_e"], max_rho=round(rho, 3),
                    L_analytical=float(rs[0]["L_analytical"]), p50_measured=round(med, 6),
                    p95_measured=round(p95, 6), repeats=len(rs),
                    iqr_ms=round(1000 * (statistics.quantiles([float(r[a.metric]) for r in rs], n=4, method="inclusive")[2] -
                                         statistics.quantiles([float(r[a.metric]) for r in rs], n=4, method="inclusive")[0]), 2),
                    spread=round(max(float(r[a.metric]) for r in rs) /
                                 min(float(r[a.metric]) for r in rs), 2),
                    rel_err=round((float(rs[0]["L_analytical"]) - med) / med, 3)))

def pair_agreement(sub, thr):
    """Share of design pairs whose measured order matches the model order,
    among pairs the model separates by more than `thr` (relative)."""
    ok = tot = 0
    for i in range(len(sub)):
        for j in range(i + 1, len(sub)):
            a, b = sub[i], sub[j]
            lo = min(a["L_analytical"], b["L_analytical"])
            if abs(a["L_analytical"] - b["L_analytical"]) / lo <= thr:
                continue
            tot += 1
            if (a["L_analytical"] - b["L_analytical"]) * (a["p50_measured"] - b["p50_measured"]) > 0:
                ok += 1
    return (round(ok / tot, 3) if tot else float("nan")), tot


def stats(sub, label):
    an = [r["L_analytical"] for r in sub]; me = [r["p50_measured"] for r in sub]
    ag10, n10 = pair_agreement(sub, 0.10)
    ag25, n25 = pair_agreement(sub, 0.25)
    spread = (max(me) - min(me)) / min(me) if len(sub) > 1 else 0
    return dict(subset=label, n=len(sub),
                agree_10pct=ag10, pairs_10pct=n10,
                agree_25pct=ag25, pairs_25pct=n25,
                measured_spread=round(spread, 2),
                median_repeat_iqr_ms=round(statistics.median(r["iqr_ms"] for r in sub), 2),
                MAPE=round(100 * statistics.mean(abs((x - y) / y) for x, y in zip(an, me)), 1),
                median_AE_ms=round(1000 * statistics.median(abs(x - y) for x, y in zip(an, me)), 2),
                spearman=round(float(spearmanr(an, me).correlation), 3),
                kendall=round(float(kendalltau(an, me).correlation), 3))

summary = []
for w in sorted({r["workload"] for r in out}):
    sub = [r for r in out if r["workload"] == w]
    summary.append(dict(workload=w, **stats(sub, "all")))
    for lbl, sel in (("rho<=0.75", [r for r in sub if r["max_rho"] <= 0.75]),
                     ("reproducible", [r for r in sub if r["spread"] < 1.5])):
        if len(sel) >= 5 and len(sel) < len(sub):
            summary.append(dict(workload=w, **stats(sel, lbl)))
allr = out
summary.append(dict(workload="ALL", **stats(allr, "all")))
summary.append(dict(workload="ALL", **stats([r for r in allr if r["max_rho"] <= 0.75], "rho<=0.75")))
summary.append(dict(workload="ALL", **stats([r for r in allr if r["spread"] < 1.5], "reproducible")))
for s in summary:
    print(s)
with open(f"{a.output_dir}/e9_summary_{a.tag}.csv", "w", newline="") as f:
    w_ = csv.DictWriter(f, sorted(summary[0])); w_.writeheader(); w_.writerows(summary)
with open(f"{a.output_dir}/e9_per_design_{a.tag}.csv", "w", newline="") as f:
    w_ = csv.DictWriter(f, sorted(out[0])); w_.writeheader(); w_.writerows(out)

fig, ax = plt.subplots(figsize=(3.5, 3.2), dpi=200)
for w, mk in zip(sorted({r["workload"] for r in out}), "osv"):
    sub = [r for r in out if r["workload"] == w]
    hi = [r for r in sub if r["spread"] >= 1.5]; lo = [r for r in sub if r["spread"] < 1.5]
    ax.scatter([r["p50_measured"] * 1e3 for r in lo], [r["L_analytical"] * 1e3 for r in lo],
               s=12, marker=mk, label=w)
    ax.scatter([r["p50_measured"] * 1e3 for r in hi], [r["L_analytical"] * 1e3 for r in hi],
               s=22, marker=mk, facecolors="none", edgecolors="crimson", linewidths=0.8)
lim = [3, 4000]; ax.plot(lim, lim, "k--", lw=0.8)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(*lim); ax.set_ylim(*lim)
ax.set_xlabel(f"measured {a.metric} latency [ms]"); ax.set_ylabel("analytical latency [ms]")
ax.set_title("open markers: repeat spread $\\geq$ 1.5x", fontsize=6)
ax.legend(fontsize=6); fig.savefig(f"{a.figure_dir}/fig7_testbed_{a.tag}.png", bbox_inches="tight")
print(f"written results/e9_summary_{a.tag}.csv, results/e9_per_design_{a.tag}.csv, "
      f"{a.figure_dir}/fig7_testbed_{a.tag}.png")
