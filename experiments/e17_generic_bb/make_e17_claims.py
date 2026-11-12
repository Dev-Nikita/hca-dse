"""Generate the macros, prose and table of the controlled bound comparison."""
import csv, json, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
R = ROOT / "results" / "e17_generic_bb"
G = ROOT / "manuscript" / "generated"
T = ROOT / "manuscript" / "tables"
G.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader((R / "bb_matrix.csv").open()))
adm = json.load((R / "admissible_S1.json").open())
cross = list(csv.DictReader((R / "crossover.csv").open()))
des_path = next((q for q in (ROOT / "results").glob("*/data/e2_des_timing.json")), None)
des_cost = json.load(des_path.open())["mean_seconds"] if des_path else None
crossed = [r for r in cross if r["crossover_vs_generic_s"]]
s3cross = [r for r in crossed if r["scale"] == "S3"]
by = {}
for r in rows:
    by.setdefault((r["scale"], r["workload"]), {})[r["config"]] = r
cells = [v for _, v in sorted(by.items())]
assert all(r["exact"] == "True" for r in rows), "a configuration lost the exact front"
assert all("G1c" in c for c in cells), "the cached generic baseline is missing"


def ran(vals, d=0, sep=r"\text{--}"):
    vals = list(vals)
    lo, hi = min(vals), max(vals)
    f = lambda v: f"{v:.{d}f}"
    return f(lo) if lo == hi else f(lo) + sep + f(hi)


def thin(n):
    return f"{int(n):,}".replace(",", "\\,")


delta = [int(c["G1c"]["evals"]) - int(c["G2"]["evals"]) for c in cells]
macros = {
    "BBRuns": str(len(cells)),
    "BBRepeats": "3",
    "BBGenericFewer": ran((-d for d in delta), 0),
    "BBGenericEqual": str(sum(1 for d in delta if d == 0)),
    "BBGenericWorse": str(sum(1 for d in delta if d > 0)),
    "BBEvalRange": ran((int(c["G2"]["evals"]) for c in cells), 0),
    "BBGenericEvalRange": ran((int(c["G1c"]["evals"]) for c in cells), 0),
    "BBStateFactor": ran((int(c["G1c"]["nodes"]) / int(c["G2"]["nodes"]) for c in cells), 1),
    "BBStateFactorLarge": ran((int(c["G1c"]["nodes"]) / int(c["G2"]["nodes"])
                               for c in cells if c["G2"]["scale"] == "S3"), 1),
    "BBTimeFactor": ran((float(c["G1c"]["seconds"]) / float(c["G2"]["seconds"])
                         for c in cells), 1),
    "BBZeroedFactor": ran((int(c["G2m"]["evals"]) / int(c["G2"]["evals"]) for c in cells), 1),
    "BBPositiveStateCut": ran((100 * (1 - int(c["G3"]["nodes"]) / int(c["G2"]["nodes"]))
                               for c in cells), 0),
    "BBLateStateFactor": ran((int(c["G4"]["nodes"]) / int(c["G3"]["nodes"]) for c in cells), 1),
    "BBCrossNone": str(len(cross) - len(crossed)),
    "BBWindowLow": ran((float(r["crossover_vs_exhaustive_us"]) for r in cross
                        if r["crossover_vs_exhaustive_us"]), 0),
    "BBWindowLowLarge": ran((float(r["crossover_vs_exhaustive_us"]) for r in cross
                             if r["scale"] == "S3" and r["crossover_vs_exhaustive_us"]), 0),
    "BBDesCost": "%.1f" % (des_cost * 1000) if des_cost else "",
    "BBExtraCalls": ran((int(r["extra_evals"]) for r in crossed), 0),
    "BBCrossRange": ran((float(r["crossover_vs_generic_s"]) for r in crossed), 2),
    "BBCrossRangeLarge": ran((float(r["crossover_vs_generic_s"]) for r in s3cross), 2),
    "BBAdmPrefix": thin(adm[0]["prefixes"]),
    "BBAdmChecks": thin(sum(a["checks"] for a in adm)),
}
bad = [k for k in macros if not k.isalpha()]
assert not bad, "a TeX macro name must be letters only: " + repr(bad)
(ROOT / "manuscript" / "generated_numbers_e17.tex").write_text(
    "\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros.items()) + "\n")

# ------------------------------------------------------------------ the table
body = []
for cell in cells:
    line = [cell["G0"]["scale"], cell["G0"]["workload"], thin(cell["G0"]["evals"])]
    for cfg in ("G1c", "G2m", "G2", "G3", "G4"):
        line.append("%s/%s" % (cell[cfg]["evals"], thin(cell[cfg]["nodes"])))
    line.append("%.1f/%.1f" % (float(cell["G1c"]["seconds"]), float(cell["G2"]["seconds"])))
    body.append(" & ".join(line) + r" \\")
(T / "bb_matrix.tex").write_text(
    "\\scriptsize\n\\setlength{\\tabcolsep}{3pt}\n"
    "\\begin{tabular}{llrrrrrrr}\n\\toprule\n"
    r"scale & workload & exh. & G1c & G2$^{-}$ & G2 & G3 & G4 & G1c/G2 \\"
    "\n" + r" & & evals & \multicolumn{5}{c}{full evaluations / expanded partial designs} & [s] \\"
    + "\n\\midrule\n" + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}\n")

# ------------------------------------------------------------------ the prose
prose = (
    r"\input{generated/refdefs}%" "\n"
    r"\RefBBTab{} reports \BBRuns{} scale/workload combinations under five bound "
    r"configurations that share the traversal order, the feasibility and dominance rules, "
    r"the same archive, the two-stage proposal/certification protocol and the "
    r"evaluator, so a difference between two columns is a difference between two bounds. "
    r"G1c is the generic branch-and-bound bound: the assignment-monotone partial cost, in "
    r"which a term enters only once the assigned variables determine it, with the same "
    r"caching and the same cheap-proposal protocol the proposed implementation uses. "
    r"G2$^{-}$ is the bound of Section~\ref{sec:method} with the contention term relaxed "
    r"to zero everywhere, G2 is the proposed bound, G3 adds the positive waiting bound "
    r"described below, and G4 runs G3 under the determinants-late order. Wall-clock is the "
    r"median of \BBRepeats{} runs with no instrumentation; memory is measured in separate "
    r"runs, because tracing allocation inflates every configuration and would not be "
    r"comparable with Section~\ref{sec:results}. Every configuration returns the "
    r"exhaustive front."
    "\n\n"
    r"The first result is negative. On full evaluations the "
    r"generic bound is \emph{not} worse: it spends \BBGenericEvalRange{} calls against "
    r"\BBEvalRange{} for the proposed bound, equal in \BBGenericEqual{} of the "
    r"\BBRuns{} combinations and \BBGenericFewer{} calls fewer in the rest. Both bounds "
    r"compute the contention term exactly once its determinants are assigned, and that "
    r"term, not the relaxation style around it, is what saves evaluator calls: relaxing it "
    r"to zero while keeping every other relaxation costs $\BBZeroedFactor\times$ more full "
    r"evaluations. We therefore do not claim an evaluator-call advantage over a generic "
    r"branch-and-bound, and the within-run counterfactual of \RefOrderTab{}, which holds "
    r"the archive fixed, understates the term for the same reason."
    "\n\n"
    r"What the term-wise relaxation does provide is search-side economy. The proposed bound "
    r"expands $\BBStateFactor\times$ fewer partial designs than the generic bound, "
    r"$\BBStateFactorLarge\times$ on the largest scale, and completes "
    r"$\BBTimeFactor\times$ faster under the identical protocol, both ratios growing with "
    r"the scale. That economy is in the search, not in the evaluator, and the cost model "
    r"of Section~\ref{sec:complexity} says when it is worth having."
    "\n\n"
    r"Charging both configurations the same price per full evaluation, "
    r"$T(C_E)=\textit{overhead}+N\,C_E$, with the overhead taken as wall-clock minus the "
    r"time spent inside the evaluator, locates the cost at which one overtakes the other. "
    r"In \BBCrossNone{} of the \BBRuns{} combinations the two spend the same number of "
    r"evaluations, so the lower overhead wins at every evaluator cost. In the remaining "
    r"ones the proposed bound pays \BBExtraCalls{} extra evaluations for its lower "
    r"overhead, and the generic bound becomes the cheaper of the two once one full "
    r"evaluation costs more than \BBCrossRange{}\,s (\BBCrossRangeLarge{}\,s on S3). "
    r"These are thresholds computed from the measured overheads and evaluation counts, not "
    r"observed switch-overs: we did not run the search with an evaluator priced at a "
    r"second a call."
    "\n\n"
    r"Read together with the comparison against exhaustive enumeration, which the same "
    r"model places at \BBWindowLow{}\,$\mu$s per evaluation "
    r"(\BBWindowLowLarge{}\,$\mu$s on S3), this delimits the regime of the method. "
    r" Below the lower figure enumeration is cheaper, because the bounds cost more "
    r"than the evaluations they avoid. Above the upper figure a generic partial-cost bound "
    r"with the same traversal order is cheaper, because its one to five fewer evaluations "
    r"outweigh its larger search. Between them the proposed bound is the cheapest of the "
    r"three, and that interval spans roughly four orders of magnitude. The discrete-event "
    r"simulator of Section~\ref{sec:methodology}, measured at \BBDesCost{}\,ms per "
    r"evaluation, sits inside it --- well above the enumeration threshold and below every "
    r"generic threshold measured --- so for that evaluator the proposed bound has the "
    r"lowest total cost of the three. An industrial evaluator of the kind "
    r"the introduction cites sits at or above the upper edge: at a second a design point the "
    r"choice still depends on the workload, because the thresholds reach "
    r"\BBCrossRangeLarge{}\,s on S3, and by a minute a design point the generic bound is "
    r"cheaper everywhere we measured. In that range the remaining advantage of the method is the exactness of "
    r"Section~\ref{sec:method} under its stated numerical policy, not speed. "
    r"\RefMethodTab{} states the resulting choice rule."
    "\n\n"
    r"A strengthening of our own bound does not pay either. The zero of "
    r"Section~\ref{sec:method} can be replaced by a positive quantity: the waiting term is "
    r"non-decreasing in the service time and in the utilisation, so substituting the "
    r"smallest reachable load, the largest reachable capacity and the minimum over the "
    r"still-reachable placement policies bounds it from below before its determinants are "
    r"fixed. The bound is admissible --- checked against every completion of every one of "
    r"\BBAdmPrefix{} prefixes on S1, \BBAdmChecks{} pairs --- and it changes no evaluation "
    r"count at all, cutting \BBPositiveStateCut\% of expanded partial designs. With the "
    r"largest reachable capacity in the denominator the utilisation lower bound is close to "
    r"zero on the prefixes that matter. We report it as a tested and rejected strengthening "
    r"rather than as a contribution."
)
(G / "e17.tex").write_text(prose + "\n")
print("macros:")
for k, v in macros.items():
    print("  \\%-22s %s" % (k, v))
