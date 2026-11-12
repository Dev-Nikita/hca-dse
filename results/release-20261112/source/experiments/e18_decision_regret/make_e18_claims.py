"""Generate the macros, prose and table of the decision-regret study."""
import csv, statistics, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
R = ROOT / "results" / "e18_decision_regret"
G = ROOT / "manuscript" / "generated"
T = ROOT / "manuscript" / "tables"
G.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader((R / "decision_regret.csv").open()))
detail = list(csv.DictReader((R / "scenarios.csv").open()))
zero = [r for r in rows if float(r["eps"]) == 0]
assert zero, "no zero-margin rows"


def ran(vals, d=0, sep=r"\text{--}"):
    vals = list(vals)
    lo, hi = min(vals), max(vals)
    f = lambda v: f"{v:.{d}f}"
    return f(lo) if lo == hi else f(lo) + sep + f(hi)


def thin(n):
    return f"{int(n):,}".replace(",", "\\,")


n_sc = sum(int(r["scenarios"]) for r in zero)
hits = sum(int(r["optimum_found"]) for r in zero)
misses = sum(int(r["coverage_misses"]) for r in zero)
worst = max(float(r["regret_max"]) for r in zero if r["regret_max"] != "")
best_eps = [r for r in rows if float(r["eps"]) == 0.20]
hits20 = sum(int(r["optimum_found"]) for r in best_eps)
miss20 = sum(int(r["coverage_misses"]) for r in best_eps)

macros = {
    "RegScenarios": str(n_sc),
    "RegHits": str(hits),
    "RegMisses": str(misses),
    "RegWorst": "%.1f" % (worst * 100),
    "RegKept": ran((int(r["selected"]) for r in zero), 0),
    "RegArchive": ran((int(r["archive"]) for r in zero), 0),
    "RegHitsMargin": str(hits20),
    "RegMissesMargin": str(miss20),
    "RegScenariosPer": zero[0]["scenarios"],
    "RegKeptMargin": ran((int(r["selected"]) for r in best_eps), 0),
    "RegKeptGrowth": ran((int(m["selected"]) / int(z["selected"]) for z in zero for m in best_eps
                          if m["workload"] == z["workload"]), 0),
}
bad = [k for k in macros if not k.isalpha()]
assert not bad, "a TeX macro name must be letters only: " + repr(bad)
(ROOT / "manuscript" / "generated_numbers_e18.tex").write_text(
    "\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros.items()) + "\n")

body = []
for r in rows:
    body.append(" & ".join([
        r["workload"], "%.2f" % float(r["eps"]),
        thin(r["selected"]), thin(r["kept"]), thin(r["archive"]), r["scenarios"],
        r["coverage_misses"], r["optimum_found"],
        ("---" if r["regret_max"] == "" else "%.1f" % (100 * float(r["regret_max"])))])
        + r" \\")
(T / "decision_regret.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{lrrrrrrrr}\n\\toprule\n"
    r"workload & $\varepsilon$ & selected & in archive & archive & scenarios & no admissible"
    r" & optimum found & worst regret [\%] \\" + "\n\\midrule\n"
    + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}\n")

prose = (
    r"\input{generated/refdefs}%" "\n"
    r"Recall is a property of the front, not of a decision. A front point the screen "
    r"loses may be equivalent to one it keeps for every practical choice, or it may be the "
    r"only design that meets a deadline, and the recall figures above do not distinguish "
    r"the two cases. We therefore evaluate the stored archive retrospectively as a set of "
    r"constrained selection problems. A scenario is \emph{minimise one objective subject "
    r"to a cap on another}; the caps are quantiles of the archive's own distribution, so "
    r"they are admissible by construction and involve no hand-chosen target. The grid "
    r"follows one rule rather than a selection of cases: each objective is minimised under "
    r"a cap on latency, or on cost where latency is the objective, at the tenth, "
    r"twenty-fifth and fiftieth percentile, giving \RegScenariosPer{} scenarios per "
    r"workload. No further simulation is needed: the best value over the whole archive is "
    r"compared with the best over the designs that the sealed prospective screen of "
    r"Section~\ref{sec:desend} selected, both taken from the same "
    r"hybrid archive, in which latency is simulated and energy, cost and network volume "
    r"are analytical. The archive includes DES-feasible designs that the analytical model "
    r"rejects; the screen cannot select them, so they count against it."
    "\n\n"
    r"\RefRegretTab{} reports the outcome. At zero margin the screen selects "
    r"\RegKept{} designs out of \RegArchive{}, and across the \RegScenarios{} scenarios it "
    r"leaves an admissible design in every one (\RegMisses{} coverage failures) and "
    r"contains the archive optimum in \RegHits{} of them. The exception is the sensing "
    r"workload, which also has the lowest front recall: minimising cost under a latency "
    r"cap at the twenty-fifth percentile yields a design \RegWorst\% more expensive than "
    r"the archive optimum. At $\varepsilon=0.20$ this case is recovered as well "
    r"(\RegHitsMargin{} of \RegScenarios{} optima, \RegMissesMargin{} coverage failures), "
    r"but the selected set grows to \RegKeptMargin{} designs, \RegKeptGrowth{} times the "
    r"zero-margin set, so the margin trades simulator calls for decision quality."
    "\n\n"
    r"These results do not remove the recall loss, which remains a property of the "
    r"analytical front; they show that, on this archive and for these scenarios, the lost "
    r"points did not change the selected design except in one case. The analysis is "
    r"retrospective: the caps are derived from the complete archive, whereas real "
    r"requirements are fixed before exploration. Nine of the twelve scenarios per workload "
    r"cap latency, none caps energy or network volume, and all are on one scale. For the "
    r"\RegScenarios{} scenarios considered, front recall alone overstates the observed loss "
    r"in decision quality; we do not claim this for independently specified requirements."
)
(G / "e18.tex").write_text(prose + "\n")
print("macros:")
for k, v in macros.items():
    print("  \\%-20s %s" % (k, v))
