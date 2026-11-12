"""Generate the manuscript macros, prose and table for the retry-term study."""
import csv, json, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
R = ROOT / "results" / "e15_feedback"
G = ROOT / "manuscript" / "generated"
T = ROOT / "manuscript" / "tables"
G.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader((R / "feedback.csv").open()))
adm1 = json.load((R / "admissible_S1.json").open())
adm2 = json.load((R / "admissible_S2.json").open())
s3 = [r for r in rows if r["scale"] == "S3"]
tab = [r for r in rows if r.get("table_evaluator_calls")]


def ran(vals, d=0, sep=r"\text{--}"):
    vals = list(vals)
    lo, hi = min(vals), max(vals)
    f = lambda v: f"{v:.{d}f}"
    return f(lo) if lo == hi else f(lo) + sep + f(hi)


def thin(n):
    return f"{int(n):,}".replace(",", "\\,")


macros = {
    "FbEvalAll": ran((int(r["hca_evals"]) for r in rows), 0),
    "FbEvalSthree": ran((int(r["hca_evals"]) for r in s3), 0),
    "FbRedAll": ran((float(r["eval_reduction"]) for r in rows), 0),
    "FbRedSthree": ran((float(r["eval_reduction"]) for r in s3), 0),
    "FbExhSthree": thin(s3[0]["exh_evals"]),
    "FbFrontSthree": ran((int(r["front"]) for r in s3), 0),
    "FbRuns": str(len(rows)),
    "FbTableCalls": ran((int(r["table_evaluator_calls"]) for r in tab), 0),
    "FbTableSolver": ran((float(r["table_solver_seconds"]) for r in tab), 1),
    "FbSupport": rows[0]["factorised_support"],
    "FbEntriesSthree": thin(s3[0]["factorised_entries"]),
    "FbIgnoreRecall": ran((float(r["ignore_screen_recall"]) for r in rows), 3),
    "FbIterMax": str(max(int(r["fp_iters_max"]) for r in rows)),
    "FbIterMean": ran((float(r["fp_iters_mean"]) for r in rows), 1),
    "FbAdmPrefix": thin(adm1[0]["prefixes"]),
    "FbAdmChecks": thin(sum(a["checks"] for a in adm1)),
    "FbAdmPrefixTwo": thin(adm2[0]["prefixes"]),
    "FbAdmChecksTwo": thin(sum(a["checks"] for a in adm2)),
}
assert all(r["exact"] == "True" for r in rows), "a run did not reproduce the retry front"

bad = [k for k in macros if not k.isalpha()]
assert not bad, "a TeX macro name must be letters only: " + repr(bad)
(ROOT / "manuscript" / "generated_numbers_e15.tex").write_text(
    "\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros.items()) + "\n")

# ----------------------------------------------------------------- the table
body = []
for r in rows:
    body.append(" & ".join([
        r["scale"], r["workload"], thin(r["exh_evals"]), r["hca_evals"],
        f"{float(r['eval_reduction']):.0f}" + r"$\times$", r["front"],
        "yes" if r["exact"] == "True" else "no",
        (thin(r["table_evaluator_calls"]) if r.get("table_evaluator_calls") else "---"),
        (f"{float(r['table_solver_seconds']):.1f}" if r.get("table_solver_seconds") else "---"),
        thin(r["factorised_entries"]),
        f"{float(r['ignore_screen_recall']):.3f}"]) + r" \\")
(T / "feedback.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{llrrrrcrrrr}\n\\toprule\n"
    r"scale & workload & \multicolumn{1}{c}{exh.\ evals} & \multicolumn{2}{c}{HCA-DSE} & "
    r"front & exact & \multicolumn{2}{c}{finite table} & factorised & ignored \\"
    "\n" + r"\cmidrule(lr){4-5}\cmidrule(lr){8-9}" + "\n"
    r" & & & evals & reduction & & & evals & solver\,[s] & entries & recall \\"
    "\n\\midrule\n" + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}\n")

# ----------------------------------------------------------------- the prose
prose = (
    r"\input{generated/refdefs}%" "\n"
    r"The retry term of Section~\ref{sec:feedback} is a single term whose support is the "
    r"entire decision vector: all \FbSupport{} decisions enter the latency function whose "
    r"fixed point it is. The factorised encoding therefore has no table of bounded "
    r"support for it --- we know of no decomposition of this fixed point --- and the only "
    r"table used by our implemented encodings that does represent it is indexed by the whole design space, \FbEntriesSthree{} "
    r"entries on S3 at one evaluation each. Among the two implemented encodings, only full-table SMT remains applicable; it "
    r"spends \FbTableCalls{} evaluator calls before the solver starts and "
    r"\FbTableSolver{}\,s inside it; the polynomial encoding cannot write the term down "
    r"at all. This comparison does not rule out nonlinear SMT with auxiliary variables, "
    r"external oracle constraints, or constraint programming with lazy evaluation."
    "\n\n"
    r"Partial-design pruning needs none of that. \RefFeedbackTab{} reports the "
    r"\FbRuns{} scale/workload combinations: the bounds of Proposition~\ref{prop:fp} "
    r"recover the exact Pareto front of the retry model in every run, with \FbEvalSthree{} "
    r"evaluations against \FbExhSthree{} on S3, a reduction of $\FbRedSthree\times$ "
    r"($\FbRedAll\times$ across all scales). A separate directed-interval audit checks all "
    r"live S1 prefixes and seeded adversarial samples on S2--S3; it finds no unsafe "
    r"feasibility or dominance prune after the numerical repair. This is an empirical "
    r"implementation audit, not formal verification. The fixed point itself converges in "
    r"\FbIterMean{} iterations on average and \FbIterMax{} at worst."
    "\n\n"
    r"The term is consequential but not dominant: screening with the closed-form model of "
    r"Section~\ref{sec:model} and re-evaluating its front under retries recovers "
    r"\FbIgnoreRecall{} of the retry front, so ignoring the feedback loses part of the "
    r"front on one workload and nothing on the others. The study therefore establishes "
    r"exactness for a term outside the two implemented compact encodings, not universal "
    r"superiority over exact solvers. The reported \FbRedSthree$\times$ is a reduction in "
    r"full evaluations, not a wall-clock speed-up over every solver-based approach."
)
(G / "e15.tex").write_text(prose + "\n")

print("macros:")
for k, v in macros.items():
    print("  \\%-20s %s" % (k, v))
print("wrote generated_numbers_e15.tex, generated/e15.tex, tables/feedback.tex")
