"""Generate the manuscript macros and prose for the end-to-end simulator study.

Reads results/e14_des_endtoend/des_endtoend.csv and des_margin.csv and writes
manuscript/generated/e14.tex plus manuscript/generated_numbers_e14.tex, so the
text carries no hand-copied number.
"""
import csv, os, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
R = ROOT / "results" / "e14_des_endtoend"
G = ROOT / "manuscript" / "generated"
T = ROOT / "manuscript" / "tables"
G.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader((R / "des_endtoend.csv").open()))
marg = list(csv.DictReader((R / "des_margin.csv").open()))
seed = list(csv.DictReader((R / "seedcheck.csv").open()))
s3 = [r for r in rows if r["scale"] == "S3"]


def ran(vals, d=0, sep=r"\text{--}"):
    vals = list(vals)
    lo, hi = min(vals), max(vals)
    f = lambda v: f"{v:.{d}f}"
    return f(lo) if lo == hi else f(lo) + sep + f(hi)


def col(rs, k, cast=float):
    return [cast(r[k]) for r in rs]


macros = {
    "DesExhMinutes": ran((float(r["exhaustive_seconds"]) / 60 for r in s3), 0),
    "DesExhSims": f"{int(s3[0]['exhaustive_sims']):,}".replace(",", "\\,"),
    "DesTwoSims": ran(col(s3, "twolevel_sims", int), 0),
    "DesTwoSpeedup": ran((round(v) for v in col(s3, "twolevel_speedup")), 0),
    "DesTwoRecall": ran(col(s3, "twolevel_recall"), 3),
    "DesInlineRecall": ran(col(s3, "inline_recall"), 3),
    "DesTwoRecallAll": ran(col(rows, "twolevel_recall"), 3),
    "DesInlineRecallAll": ran(col(rows, "inline_recall"), 3),
    "DesInlineWorse": str(sum(1 for r in rows
                              if float(r["inline_recall"]) < float(r["twolevel_recall"]))),
    "DesRuns": str(len(rows)),
}

m20 = [r for r in marg if r["scale"] == "S3" and abs(float(r["eps"]) - 0.20) < 1e-9]
m10 = [r for r in marg if r["scale"] == "S3" and abs(float(r["eps"]) - 0.10) < 1e-9]
if m20:
    macros["DesMarginSims"] = ran(col(m20, "sims", int), 0)
    macros["DesMarginRecall"] = ran(col(m20, "recall"), 3)
    macros["DesMarginFactor"] = ran(
        (int(r["exhaustive_sims"]) / int(r["sims"]) for r in m20), 0)
if m10:
    macros["DesMarginTenRecall"] = ran(col(m10, "recall"), 3)

# ------------------------------------------------- the seed-robustness check
macros["DesSeedCand"] = ran(col(seed, "candidates", int), 0)
macros["DesSeedSims"] = ran(col(seed, "sims", int), 0)
macros["DesSeedFront"] = ran(col(seed, "front0", int), 0)
macros["DesSeedRetained"] = ran(col(seed, "front_stable", int), 0)
macros["DesSeedRecallDrop"] = ran(
    (float(r["twolevel_recall_1seed"]) - float(r["twolevel_recall_5seed"]) for r in seed), 3)
macros["DesSeedSpread"] = ran((100 * float(r["spread_median"]) for r in seed), 2)
macros["DesSeedSpreadHigh"] = ran((100 * float(r["spread_p90"]) for r in seed), 1)
macros["DesSeedEps"] = "%.2f" % float(seed[0]["eps"])
assert all(int(r["front_stable"]) == int(r["front0"]) for r in seed), \
    "a single-seed front member was dominated under five seeds: reword this claim"

bad = [k for k in macros if not k.isalpha()]
assert not bad, "a TeX macro name must be letters only: " + repr(bad)
(ROOT / "manuscript" / "generated_numbers_e14.tex").write_text(
    "\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros.items()) + "\n")

# ---------------------------------------------------------------- the table
head = (r"scale & workload & \multicolumn{2}{c}{exhaustive DES} & "
        r"\multicolumn{3}{c}{two-level} & \multicolumn{3}{c}{simulator in the loop}")
sub = r" & & sims & min & sims & speed-up & recall & sims & speed-up & recall"
body = []
for r in rows:
    body.append(" & ".join([
        r["scale"], r["workload"],
        f"{int(r['exhaustive_sims']):,}".replace(",", "\\,"),
        f"{float(r['exhaustive_seconds'])/60:.1f}",
        r["twolevel_sims"], f"{float(r['twolevel_speedup']):.0f}" + r"$\times$",
        f"{float(r['twolevel_recall']):.3f}",
        r["inline_sims"], f"{float(r['inline_speedup']):.0f}" + r"$\times$",
        f"{float(r['inline_recall']):.3f}"]) + r" \\")
(T / "des_endtoend.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{llrrrrrrrr}\n\\toprule\n"
    + head + r" \\" + "\n" + r"\cmidrule(lr){3-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}"
    + "\n" + sub + r" \\" + "\n\\midrule\n" + "\n".join(body)
    + "\n\\bottomrule\n\\end{tabular}\n")

# margin table, S3 only
mb = []
for r in [r for r in marg if r["scale"] == "S3"]:
    mb.append(" & ".join([r["workload"], f"{float(r['eps']):.2f}",
                          f"{int(r['sims']):,}".replace(",", "\\,"),
                          f"{float(r['recall']):.3f}"]) + r" \\")
(T / "des_margin.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{lrrr}\n\\toprule\n"
    r"workload & $\varepsilon$ & simulator calls & recall \\" + "\n\\midrule\n"
    + "\n".join(mb) + "\n\\bottomrule\n\\end{tabular}\n")

# ---------------------------------------------------------------- the prose
prose = (
    r"\input{generated/refdefs}%" "\n"
    r"\RefDesEndTab{} reports the three protocols on \DesRuns{} scale/workload "
    r"combinations. Exhaustive simulation of S3 costs \DesExhSims{} simulator runs and "
    r"\DesExhMinutes{} minutes per workload on the machine used here. The two-level "
    r"workflow --- the exact analytical search of Section~\ref{sec:method} followed by "
    r"simulation of the surviving front --- spends \DesTwoSims{} simulator runs, a "
    r"measured wall-clock speed-up of $\DesTwoSpeedup\times$, and returns "
    r"\DesTwoRecall{} of the simulated Pareto front. Placing the simulator inside the "
    r"search instead leaves \DesInlineRecall{} of that front; it is worse in "
    r"\DesInlineWorse{} of the \DesRuns{} runs. The bounds are admissible for the "
    r"analytical model, so with a simulated leaf the archive holds simulated vectors "
    r"while the bounds are computed from the analytical objective, and dominance "
    r"compares quantities that are not the same function. The guarantee does not "
    r"transfer, and the measurement shows what that costs."
    "\n\n"
    r"Screening with a margin converts the loss into a controllable quantity. "
    r"\RefDesMarginTab{} keeps every design that the analytical front fails to dominate "
    r"once that front is inflated by a relative margin $\varepsilon$; because both "
    r"objective vectors were recorded for every design of the exhaustive sweep, the "
    r"sweep required no further simulation. At $\varepsilon=0.10$ recall is "
    r"\DesMarginTenRecall{}, and at $\varepsilon=0.20$ it is \DesMarginRecall{} on all "
    r"three workloads at \DesMarginSims{} simulator calls, still a factor of "
    r"\DesMarginFactor{} below exhaustive simulation. The margin is a heuristic: it "
    r"carries no admissibility proof, and the recall it achieves is an observation on "
    r"this template, not a guarantee."
    "\n\n"
    r"The S3 runs use one seed per design. Re-simulating with five seeds every design that "
    r"the single-seed simulated front does not dominate by more than a relative "
    r"$\DesSeedEps$ --- \DesSeedCand{} designs per workload, \DesSeedSims{} further "
    r"simulator runs --- leaves every member of that front non-dominated under the medians, "
    r"adds at most one member, and moves the screening recall, recomputed identically under "
    r"both seed regimes, by at most \DesSeedRecallDrop. The per-design spread over seeds is "
    r"\DesSeedSpread\% of the median latency at the median design but \DesSeedSpreadHigh\% at "
    r"the ninetieth percentile, where designs run close to saturation; medians over seeds are "
    r"therefore used throughout."
)
(G / "e14.tex").write_text(prose + "\n")

print("macros:")
for k, v in macros.items():
    print("  \\%-22s %s" % (k, v))
print("wrote manuscript/generated/e14.tex, tables/des_endtoend.tex, tables/des_margin.tex")
