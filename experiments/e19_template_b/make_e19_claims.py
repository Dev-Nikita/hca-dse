"""Generate the macros, table and prose of the second-template study (E19)."""
import csv, json, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
R = ROOT / "results" / "e19_template_b"
G = ROOT / "manuscript" / "generated"
T = ROOT / "manuscript" / "tables"
G.mkdir(parents=True, exist_ok=True)
T.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader((R / "matrix.csv").open()))
checks = {f.stem.split("_")[1]: json.load(f.open()) for f in sorted(R.glob("check_B*.json"))}
check = [row for rows_ in checks.values() for row in rows_]
assert all(r["admissibility_violations"] == 0 and r["ordering_violations"] == 0 for r in check)
cells = {}
for r in rows:
    cells.setdefault((r["scale"], r["workload"]), {})[r["config"]] = r
# independent reference implementation and mutation analysis
oracle = [r for f in sorted(R.glob("oracle_*.json")) for r in json.load(f.open())]
assert oracle and all(r.get("feasibility_mismatches", 0) == 0 and r.get("objective_mismatches", 0) == 0
                      and r.get("search_front_equal", True) and r.get("generic_front_equal", True)
                      and r.get("stored_front_equal", True) and r.get("other_orders_equal", True)
                      for r in oracle), "the reference implementation disagrees"
full = [r for r in oracle if "search_front_equal" in r and "compared" in r
        and r["compared"] == r["structurally_valid"]]
sample = [r for r in oracle if "compared" in r and r["compared"] < r["structurally_valid"]]
front_only = {(r["scale"], r["workload"]) for r in oracle if "stored_front_equal" in r}
mut = json.load((R / "mutation.json").open())
assert mut["killed"] == mut["total"], "a mutant survived"


def collapsed(front):
    """Front points that another front point dominates once both are rounded to
    binary64, and the largest relative advantage that keeps them on the exact front."""
    fl = [tuple(float(v) for v in r) for r in front]
    n, adv = 0, 0.0
    for i, a in enumerate(front):
        for j, b in enumerate(front):
            if i != j and ((fl[j] != fl[i] and all(fl[j][k] <= fl[i][k] for k in range(4)))
                           or (fl[j] == fl[i] and j < i)):
                n += 1
                adv = max([adv] + [float((b[k] - a[k]) / a[k]) for k in range(4)
                                   if a[k] < b[k] and a[k] != 0])
                break
    return n, adv


from fractions import Fraction  # noqa: E402
sub = {}
for f in sorted((R / "reference").glob("*.json")):
    front = [tuple(Fraction(v) for v in r) for r in json.load(f.open())]
    sub[tuple(f.stem.split("_"))] = (collapsed(front), len(front))
worst = max(sub, key=lambda k: sub[k][0][0])
sub_adv = max(v[0][1] for v in sub.values())
import math  # noqa: E402
keys = sorted(cells, key=lambda k: (k[0], ["vision", "fusion", "batch"].index(k[1])))
assert all(r["exact"] == "True" for r in rows), "a configuration missed the front"


def ran(vals, d=0):
    vals = list(vals)
    lo, hi = min(vals), max(vals)
    f = lambda v: f"{v:.{d}f}"
    return f(lo) if f(lo) == f(hi) else f(lo) + r"\text{--}" + f(hi)


def thin(n):
    return f"{int(n):,}".replace(",", "\\,")


def ranthin(vals):
    vals = [int(v) for v in vals]
    lo, hi = min(vals), max(vals)
    return thin(lo) if lo == hi else thin(lo) + r"\text{--}" + thin(hi)


large = [k for k in keys if k[0] == "B3"]
ev = lambda c, k: int(cells[k][c]["evals"])
nd = lambda c, k: int(cells[k][c]["nodes"])
oh = lambda c, k: float(cells[k][c]["overhead_seconds"])
equal = sum(ev("G2", k) == ev("G1", k) for k in keys)
fewer = sum(ev("G2", k) < ev("G1", k) for k in keys)
more = sum(ev("G2", k) > ev("G1", k) for k in keys)
assert more == 0, "the bound needed more evaluations than the partial cost"

breakeven = []
for k in keys:
    dn = ev("G0", k) - ev("G2", k)
    do = oh("G2", k) - oh("G0", k)
    breakeven.append(do / dn * 1e6 if dn > 0 else float("nan"))
always = all(b <= 0 for b in breakeven)

macros = {
    "TbRuns": str(len(keys)),
    "TbRaw": ranthin(int(cells[k]["G0"]["raw"]) for k in keys),
    "TbValidLarge": thin(ev("G0", large[0])),
    "TbFrontLarge": ranthin(int(cells[k]["G0"]["front"]) for k in large),
    "TbEvalLarge": ranthin(ev("G2", k) for k in large),
    "TbReductionLarge": ran((ev("G0", k) / ev("G2", k) for k in large), 0),
    "TbEqual": str(equal),
    "TbFewer": str(fewer),
    "TbStateFactor": ran((nd("G1", k) / nd("G2", k) for k in keys), 1),
    "TbStateFactorLarge": ran((nd("G1", k) / nd("G2", k) for k in large), 1),
    "TbTimeFactor": ran((oh("G1", k) / oh("G2", k) for k in keys), 1),
    "TbZeroedFactor": ran((ev("G2m", k) / ev("G2", k) for k in keys), 1),
    "TbCheckScales": " and ".join(sorted(checks)),
    "TbCheckPrefixes": thin(sum(rows_[0]["prefixes"] for rows_ in checks.values())),
    "TbChecks": thin(sum(c["checks"] for c in check)),
    "TbBreakEven": ("" if always else ran((b for b in breakeven if b > 0), 0)),
    "TbOracleFull": thin(sum(r["compared"] for r in full)),
    "TbOracleDesigns": thin(sum({r["scale"]: r["compared"] for r in full}.values())),
    "TbOracleFullScales": " and ".join(sorted({r["scale"] for r in full})),
    "TbOracleSample": thin(sample[0]["compared"]) if sample else "0",
    "TbOracleSampleScale": " and ".join(sorted({r["scale"] for r in sample})),
    "TbOrders": str(full[0]["other_orders"]),
    "TbMutants": str(mut["total"]),
    "TbMutKilled": str(mut["killed"]),
    "TbMutFront": str(mut["killed_by_front"]),
    "TbMutBoundary": str(mut["boundary_workloads"]),
    "TbMutSamples": thin(mut["admissibility_samples"]),
    "TbSubUlpMax": str(sub[worst][0][0]),
    "TbSubUlpOf": str(sub[worst][1]),
    "TbSubUlpAdv": "10^{%d}" % math.ceil(math.log10(sub_adv)) if sub_adv > 0 else "0",
}
assert len(front_only) + len({(r["scale"], r["workload"]) for r in full}) == len(keys), \
    "not every combination has its front checked against the reference implementation"
bad = [k for k in macros if not k.isalpha()]
assert not bad, bad
(ROOT / "manuscript" / "generated_numbers_e19.tex").write_text(
    "\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros.items()) + "\n")

body = []
for k in keys:
    c = cells[k]
    body.append(" & ".join([
        k[0], k[1], thin(c["G0"]["evals"]), c["G0"]["front"],
        thin(c["G1"]["evals"]), thin(c["G2m"]["evals"]), thin(c["G2"]["evals"]),
        thin(c["G1"]["nodes"]), thin(c["G2"]["nodes"]),
        "%.2f" % float(c["G1"]["overhead_seconds"]), "%.2f" % float(c["G2"]["overhead_seconds"]),
    ]) + r" \\")
(T / "template_b.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{llrrrrrrrrr}\n\\toprule\n"
    r" & & & & \multicolumn{3}{c}{full evaluations} & \multicolumn{2}{c}{expanded states}"
    r" & \multicolumn{2}{c}{search time [s]} \\" "\n"
    r"\cmidrule(lr){5-7}\cmidrule(lr){8-9}\cmidrule(lr){10-11}" "\n"
    r"scale & workload & valid & front & G1 & G2$^{-}$ & G2 & G1 & G2 & G1 & G2 \\"
    "\n\\midrule\n" + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}\n")

if always:
    be = (r"Against exhaustive enumeration the search has the lower non-evaluation overhead in "
          r"every combination, so under the linear cost model it is cheaper at every evaluator "
          r"cost; this reflects the cost of generating and checking every design in this "
          r"implementation of enumeration, not a property of the template.")
else:
    be = (r"Against exhaustive enumeration the linear cost model of Section~\ref{sec:bb} "
          r"places the break-even at \TbBreakEven{}\,$\mu$s per evaluation.")

prose = (
    r"\input{generated/refdefs}%" "\n"
    r"Everything reported so far concerns one template, and the bounds of "
    r"Section~\ref{sec:method} were written for it. To test whether the construction, "
    r"rather than the particular bounds, carries over, we instantiated the same "
    r"bound-construction principles for a second template that differs where the bounds "
    r"do their work; the formulas and their implementation are new, the rules that "
    r"generate them are not. Template B places five "
    r"stages --- ingest, filter, aggregate, analytics and archive --- on edge, fog and cloud "
    r"tiers, with one placement variable per stage instead of a single policy, so that the "
    r"load of a tier and with it the waiting time of every stage placed there is jointly "
    r"determined by up to five placement variables, the node count and the node class. The "
    r"application forks after the filter stage, and a request completes when both "
    r"branches have completed, so latency is a maximum over paths rather than a sum. The "
    r"bounds follow the recipe of Lemmas~\ref{lem:relax}--\ref{lem:compose}: every term "
    r"enters exactly once its support is assigned and as its reachable minimum otherwise, "
    r"and the latency bound composes the per-path bounds through the same sum and maximum "
    r"as the latency itself. The generic partial cost uses the same composition with zero "
    r"for undetermined terms. The template, its bounds and all parameters are specified "
    r"in the supplementary material and implemented in the release "
    r"(\texttt{hcadse/template\_b.py}); it shares only the pruning rules of "
    r"Section~\ref{sec:method} with the template-A code. Its numerical policy is exact "
    r"rather than interval-based: every operation of the template-B model is rational, so "
    r"a binary64 bound proposes a prune and the same bound, recomputed in rational "
    r"arithmetic from the binary64 parameters, confirms it against the exactly computed "
    r"objectives of the archived designs. Every pruning decision is therefore exact in the "
    r"model; rounding can only cost a missed prune."
    "\n\n"
    r"\RefTemplateBTab{} reports \TbRuns{} scale/workload combinations over spaces of "
    r"\TbRaw{} raw designs. In rational arithmetic, and so without tolerance, the bound "
    r"is admissible on every one of \TbCheckPrefixes{} prefixes of \TbCheckScales{} against "
    r"every completion (\TbChecks{} checks over three workloads), and it dominates the "
    r"partial cost on all of them. Every configuration returns the "
    r"exhaustive front, which is itself computed in rational arithmetic. A separate "
    r"reference implementation, written from the specification and sharing only the "
    r"parameter values with the production code, agrees with the production evaluator on "
    r"feasibility and on all four objectives, exactly, for all \TbOracleDesigns{} designs of "
    r"\TbOracleFullScales{} under each of the three workloads (\TbOracleFull{} "
    r"design--workload evaluations) and for a random sample of \TbOracleSample{} designs per "
    r"workload of \TbOracleSampleScale{}, and it reproduces the front of every "
    r"combination, also under \TbOrders{} other variable orders. A mutation analysis of "
    r"\TbMutants{} single changes to the bounds and to the pruning decisions kills all "
    r"\TbMutKilled{}, \TbMutFront{} of them through a changed front (supplementary "
    r"material). Because the front is exact it retains points that improve on another "
    r"front point only below binary64 resolution --- up to \TbSubUlpMax{} of "
    r"\TbSubUlpOf{}, by less than $\TbSubUlpAdv$ relative --- and the front sizes "
    r"reported count them. On B3 the search evaluates \TbEvalLarge{} of \TbValidLarge{} "
    r"structurally valid designs, a $\TbReductionLarge\times$ reduction, while the fronts "
    r"hold \TbFrontLarge{} points. Against the generic partial cost the outcome of "
    r"template A recurs: " + (r"the same number of full evaluations in all \TbRuns{} "
    r"combinations" if fewer == 0 else r"the same number of full evaluations in \TbEqual{} "
    r"of \TbRuns{} combinations and fewer in \TbFewer{}") +
    r", never more, as Proposition~\ref{prop:mono} requires, with $\TbStateFactor\times$ fewer expanded states "
    r"($\TbStateFactorLarge\times$ on B3) and $\TbTimeFactor\times$ less search time. "
    r"Relaxing the waiting term to zero costs $\TbZeroedFactor\times$ more full "
    r"evaluations, so contention again accounts for most of what the bounds avoid. " + be
    + "\n\n"
    r"The study shows that the construction transfers to a template with a different "
    r"stage graph, per-stage placement and a non-additive latency, and that writing the "
    r"bounds for it is mechanical once each term's support is known. It does not show "
    r"that every architecture admits useful bounds: templates whose objectives are not "
    r"monotone compositions of terms with identifiable supports would need a new "
    r"argument, and template B is analytical only, without a simulator or testbed of its own."
)
(G / "e19.tex").write_text(prose + "\n")
print("macros:")
for k, v in macros.items():
    print("  \\%-20s %s" % (k, v))

# ---- parameter tables for the supplement, generated from the model itself ----
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hcadse import template_b as tb  # noqa: E402

def fmt(v):
    return ("%g" % v)

lines = []
for tier, classes in (("edge", tb.EDGE), ("fog", tb.FOG), ("cloud", tb.CLOUD)):
    for c in classes:
        lines.append(" & ".join([tier, c.name, fmt(c.C), fmt(c.P_idle), fmt(c.P_peak),
                                 fmt(c.cost)]) + r" \\")
links = [" & ".join([l.name, fmt(l.B), fmt(l.prop), fmt(l.e), fmt(l.cost)]) + r" \\"
         for l in tb.LINKS]
(T / "template_b_classes.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{llrrrr}\n\\toprule\n"
    r"tier & class & $C$ [MIPS] & $P^{\mathrm{idle}}$ [W] & $P^{\mathrm{peak}}$ [W] & cost \\"
    "\n\\midrule\n" + "\n".join(lines) + "\n\\midrule\n"
    r"link & & $B$ [Mb/s] & $\tau^{\mathrm{prop}}$ [s] & $e$ [J/MB] & cost \\" "\n\\midrule\n"
    + "\n".join(" & ".join([l.name, ""] + [fmt(l.B), fmt(l.prop), fmt(l.e), fmt(l.cost)])
                + r" \\" for l in tb.LINKS)
    + "\n" + " & ".join(["WAN (fixed)", "", fmt(tb.WAN_B), fmt(tb.WAN_PROP), fmt(tb.WAN_E), "--"])
    + r" \\" + "\n\\bottomrule\n\\end{tabular}\n")

wl_lines = []
for w in tb.WORKLOADS.values():
    wl_lines.append(" & ".join([w.name, fmt(w.Lambda), ", ".join(fmt(v) for v in w.w),
                                ", ".join(fmt(v) for v in w.s_in), fmt(w.deadline),
                                fmt(w.C_max), "%.1e" % w.E_max]) + r" \\")
(T / "template_b_workloads.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{lrllrrr}\n\\toprule\n"
    r"workload & $\Lambda$ [1/s] & $w_i$ [MI] & $s_e$ [MB] & $D$ [s] & $C^{\max}$ & $E^{\max}$ [J] \\"
    "\n\\midrule\n" + "\n".join(wl_lines) + "\n\\bottomrule\n\\end{tabular}\n")

sc_lines = []
for name, d in tb.SCALES.items():
    sc_lines.append(" & ".join([
        name, ", ".join(str(v) for v in d["n_e"]), ", ".join(c.name for c in d["k_e"]),
        ", ".join(str(v) for v in d["n_f"]), ", ".join(c.name for c in d["k_f"]),
        ", ".join(l.name for l in d["link"]), ", ".join(c.name for c in d["k_c"]),
        thin(tb.raw_size(name))]) + r" \\")
(T / "template_b_scales.tex").write_text(
    "\\scriptsize\n\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{l>{\\raggedright\\arraybackslash}p{1.4cm}"
    ">{\\raggedright\\arraybackslash}p{2.4cm}>{\\raggedright\\arraybackslash}p{1.1cm}"
    ">{\\raggedright\\arraybackslash}p{2.0cm}>{\\raggedright\\arraybackslash}p{2.4cm}"
    ">{\\raggedright\\arraybackslash}p{2.0cm}r}\n\\toprule\n"
    r"scale & $n_e$ & edge class & $n_f$ & fog class & link & cloud class & raw \\"
    "\n\\midrule\n" + "\n".join(sc_lines) + "\n\\bottomrule\n\\end{tabular}\n")

