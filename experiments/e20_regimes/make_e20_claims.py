"""Macros, tables and prose for E20 (constraint regimes) and E21 (retry model
against the generic partial cost)."""
import csv, json, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
G = ROOT / "manuscript" / "generated"
T = ROOT / "manuscript" / "tables"
G.mkdir(parents=True, exist_ok=True)
T.mkdir(parents=True, exist_ok=True)
SCALES = ("S1", "S2", "S3")
WLS = ("telemetry", "control", "sensing")


def ran(vals, d=1):
    vals = list(vals)
    lo, hi = min(vals), max(vals)
    f = lambda v: f"{v:.{d}f}"
    return f(lo) if f(lo) == f(hi) else f(lo) + r"\text{--}" + f(hi)


def thin(n):
    return f"{int(n):,}".replace(",", "\\,")


# ---- E20 -------------------------------------------------------------------
rg = list(csv.DictReader((ROOT / "results" / "e20_regimes" / "regimes.csv").open()))
assert all(r["exact"] == "True" for r in rg)
cell = {(r["scale"], r["workload"], r["regime"], r["config"]): r for r in rg}
combos = sorted({(r["scale"], r["workload"], r["regime"]) for r in rg})
ev = lambda k, c: int(cell[k + (c,)]["evals"])
nd = lambda k, c: int(cell[k + (c,)]["nodes"])
rg_equal = sum(ev(k, "G2") == ev(k, "G1c") for k in combos)
rg_fewer = sum(ev(k, "G2") < ev(k, "G1c") for k in combos)
assert all(ev(k, "G2") <= ev(k, "G1c") for k in combos)
assert all(int(cell[k + ("G0",)]["front"]) > 0 for k in combos)
rg_fewer_max = max(ev(k, "G1c") - ev(k, "G2") for k in combos)

# ---- E21 -------------------------------------------------------------------
rt = list(csv.DictReader((ROOT / "results" / "e21_retry_bb" / "retry.csv").open()))
assert all(r["exact"] == "True" for r in rt)
adm = json.load((ROOT / "results" / "e21_retry_bb" / "admissible_S1.json").open())
assert all(a["violations"] == 0 for a in adm)
c2 = {(r["scale"], r["workload"], r["config"]): r for r in rt}
keys = [(s, w) for s in SCALES for w in WLS if (s, w, "R3") in c2]
e = lambda k, c: int(c2[k + (c,)]["evals"])
n = lambda k, c: int(c2[k + (c,)]["nodes"])
o = lambda k, c: float(c2[k + (c,)]["overhead_seconds"])
large = [k for k in keys if k[0] == "S3"]
assert all(e(k, "R3") <= e(k, "R1") for k in keys)
cross = []
for k in keys:
    dn, do = e(k, "R1") - e(k, "R3"), o(k, "R3") - o(k, "R1")
    if do > 0:
        cross.append(do / dn * 1e6)

# ---- E22: retry model variants (S2) ----------------------------------------
sens = {}
for d in sorted((ROOT / "results" / "e22_retry_sensitivity").glob("a*_q*")):
    a_, q_ = d.name[1:].split("_q")
    for f in sorted(d.glob("retry_*.csv")):
        for r in csv.DictReader(f.open()):
            assert r["exact"] == "True"
            sens[(float(a_), float(q_), r["workload"], r["config"])] = r
settings = sorted({(k[0], k[1]) for k in sens})
skeys = sorted({k[:3] for k in sens})
se = lambda k, c: int(sens[k + (c,)]["evals"])
assert all(se(k, "R3") <= se(k, "R1") for k in skeys)
fp_t = [float(c2[k + ("R1fp",)]["seconds"]) / float(c2[k + ("R3",)]["seconds"]) for k in keys]
fp_tl = [float(c2[k + ("R1fp",)]["seconds"]) / float(c2[k + ("R3",)]["seconds"]) for k in large]

macros = {
    "RgRuns": str(len(combos)),
    "RgEqual": str(rg_equal),
    "RgFewer": str(rg_fewer),
    "RgFewerMax": str(rg_fewer_max),
    "RgStateFactor": ran(nd(k, "G1c") / nd(k, "G2") for k in combos),
    "RtRuns": str(len(keys)),
    "RtEvalFactor": ran((e(k, "R1") / e(k, "R3") for k in keys), 1),
    "RtEvalFactorLarge": ran((e(k, "R1") / e(k, "R3") for k in large), 1),
    "RtEvalGenericLarge": thin(min(e(k, "R1") for k in large)) + r"\text{--}"
                          + thin(max(e(k, "R1") for k in large)),
    "RtEvalOursLarge": ran((e(k, "R3") for k in large), 0),
    "RtTermEqual": str(sum(abs(e(k, "R2") - e(k, "R1")) <= 1 for k in keys)),
    "RtFpEqual": str(sum(abs(e(k, "R1fp") - e(k, "R3")) <= 1 for k in keys)),
    "RtStateFactor": ran(n(k, "R1fp") / n(k, "R3") for k in keys),
    "RtStateFactorGeneric": ran(n(k, "R1") / n(k, "R3") for k in keys),
    "RtChecks": thin(sum(a["checks"] for a in adm)),
    "RtPrefixes": thin(adm[0]["prefixes"]),
    "RtCross": (ran(cross, 0) if cross else ""),
    "RtCrossCount": str(len(cross)),
    "RtFpTimeFactor": ran(fp_t, 1),
    "RtFpTimeFactorLarge": ran(fp_tl, 1),
    "RtExcess": "%.0f" % (1e12 * max(a.get("max_relative_excess", 0.0) for a in adm)),
    "SnSettings": str(len(settings)),
    "SnRuns": str(len(skeys)),
    "SnEvalFactor": ran((se(k, "R1") / se(k, "R3") for k in skeys), 1),
    "SnFpEqual": str(sum(se(k, "R1fp") == se(k, "R3") for k in skeys)),
    "SnStateFactor": ran((int(sens[k + ("R1fp",)]["nodes"]) / int(sens[k + ("R3",)]["nodes"])
                          for k in skeys), 1),
}
assert all(k.isalpha() for k in macros)
(ROOT / "manuscript" / "generated_numbers_e20.tex").write_text(
    "\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros.items()) + "\n")

# ---- table: retry model ----------------------------------------------------
body = []
for k in keys:
    body.append(" & ".join([k[0], k[1], thin(e(k, "R0")), c2[k + ("R0",)]["front"],
                            thin(e(k, "R1")), thin(e(k, "R2")), thin(e(k, "R1fp")),
                            thin(e(k, "R3")), thin(n(k, "R1")), thin(n(k, "R1fp")),
                            thin(n(k, "R3"))]) + r" \\")
(T / "retry_bb.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{llrrrrrrrrr}\n\\toprule\n"
    r" & & & & \multicolumn{4}{c}{full evaluations} & \multicolumn{3}{c}{expanded states} \\"
    "\n" r"\cmidrule(lr){5-8}\cmidrule(lr){9-11}" "\n"
    r"scale & workload & valid & front & R1 & R2 & R1$^{\mathrm{fp}}$ & R3 & R1 & R1$^{\mathrm{fp}}$ & R3 \\"
    "\n\\midrule\n" + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}\n")

# ---- tables: retry runtimes and retry-model variants (supplement) -----------
tb = []
for k in keys:
    tb.append(" & ".join([k[0], k[1]] + ["%.2f" % float(c2[k + (c,)]["seconds"])
                                         for c in ("R0", "R1", "R2", "R1fp", "R3")]) + r" \\")
(T / "retry_times.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{llrrrrr}\n\\toprule\n"
    r"scale & workload & R0 & R1 & R2 & R1$^{\mathrm{fp}}$ & R3 \\"
    "\n\\midrule\n" + "\n".join(tb) + "\n\\bottomrule\n\\end{tabular}\n")
sb = []
for a_, q_ in settings:
    for w in WLS:
        k = (a_, q_, w)
        sb.append(" & ".join(["%g" % a_, "%g" % q_, w, sens[k + ("R0",)]["front"],
                              thin(se(k, "R1")), thin(se(k, "R1fp")), thin(se(k, "R3")),
                              "%.1f" % (se(k, "R1") / se(k, "R3"))]) + r" \\")
(T / "retry_sensitivity.tex").write_text(
    "\\scriptsize\n\\begin{tabular}{rrlrrrrr}\n\\toprule\n"
    r"$\alpha$ & $\bar q$ & workload & front & R1 & R1$^{\mathrm{fp}}$ & R3 & R1/R3 \\"
    "\n\\midrule\n" + "\n".join(sb) + "\n\\bottomrule\n\\end{tabular}\n")

# ---- table: regimes (supplement) -------------------------------------------
rb = []
for s in SCALES:
    for w in WLS:
        row = [s, w]
        for g in ("tight", "baseline", "loose"):
            k = (s, w, g)
            row += [cell[k + ("G0",)]["front"], thin(ev(k, "G1c")), thin(ev(k, "G2")),
                    "%.1f" % (nd(k, "G1c") / nd(k, "G2"))]
        rb.append(" & ".join(row) + r" \\")
(T / "regimes.tex").write_text(
    "\\scriptsize\n\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{ll" + "rrrr" * 3 + "}\n\\toprule\n"
    r" & & \multicolumn{4}{c}{tight ($m=0.8$)} & \multicolumn{4}{c}{baseline ($m=1$)} & \multicolumn{4}{c}{loose ($m=1.25$)} \\"
    "\n" r"\cmidrule(lr){3-6}\cmidrule(lr){7-10}\cmidrule(lr){11-14}" "\n"
    r"scale & workload & front & G1c & G2 & states & front & G1c & G2 & states & front & G1c & G2 & states \\"
    "\n\\midrule\n" + "\n".join(rb) + "\n\\bottomrule\n\\end{tabular}\n")

# ---- prose -----------------------------------------------------------------
e20 = (
    r"The equality of full evaluations is not an artefact of the constraint values. With "
    r"the deadline, the cost budget and the energy budget of every workload scaled jointly "
    r"by $0.8$ and by $1.25$, a protocol fixed before the runs (Supplementary Table~S16), "
    r"the proposed bound and the generic bound evaluate the same number of designs in "
    r"\RgEqual{} of \RgRuns{} scale/workload/regime combinations and the proposed bound at "
    r"most \RgFewerMax{} fewer in the other \RgFewer{}, while it expands "
    r"$\RgStateFactor\times$ fewer partial designs; every configuration returns the "
    r"exhaustive front. The three limits are scaled jointly, so this is a robustness "
    r"check, not a factorial study of the constraints. For objectives in closed form "
    r"the advantage over a generic branch-and-bound is therefore search-side in every "
    r"regime tested. "
    r"Section~\ref{sec:feedbackres} shows where it is not.")
e21 = (
    r"\input{generated/refdefs}%" "\n"
    r"Under the retry term the comparison with the generic branch-and-bound changes. The "
    r"effective rate $\Lambda^{\ast}$ is determined only by a complete design, so the "
    r"generic partial cost, which counts a term once its determinants are assigned, sees "
    r"every load-dependent quantity at the exogenous rate; this is admissible, because "
    r"every term is non-decreasing in the rate, but it ignores the amplification. "
    r"\RefRetryBBTab{} compares, under the protocol of Section~\ref{sec:bb} and with the "
    r"retry evaluator and archive throughout, the unlifted generic bound (R1), the "
    r"term-wise bound of Section~\ref{sec:method} without the fixed point (R2), the "
    r"generic bound lifted through the fixed point of Proposition~\ref{prop:fp} (R1$^{"
    r"\mathrm{fp}}$) and the bound of Proposition~\ref{prop:fp} (R3); R1$^{\mathrm{fp}}$ "
    r"and R3 iterate the rate with the same directed-rounding certification. Every "
    r"configuration returns the exhaustive front. Against the unlifted generic bound, R3 "
    r"needs $\RtEvalFactor\times$ fewer full evaluations, $\RtEvalFactorLarge\times$ on S3 "
    r"(\RtEvalOursLarge{} against \RtEvalGenericLarge{}), and R2 is no better than R1 "
    r"(equal to within one in \RtTermEqual{} of \RtRuns{} combinations). Lifting the "
    r"generic bound closes that gap: R1$^{\mathrm{fp}}$ matches R3 to within one evaluation "
    r"in \RtFpEqual{} of \RtRuns{} combinations. The saving in full evaluations is "
    r"therefore a property of the fixed-point lifting, which applies to any admissible "
    r"bound that is non-decreasing in the rate, not of the term-wise relaxation. What the "
    r"relaxation adds under identical certification is search-side again: "
    r"$\RtStateFactor\times$ fewer expanded states than R1$^{\mathrm{fp}}$, and, because "
    r"each certified bound now iterates a fixed point, $\RtFpTimeFactor\times$ less search "
    r"time ($\RtFpTimeFactorLarge\times$ on S3; R1$^{\mathrm{fp}}$ timed in a single run, "
    r"the others as the median of three, Supplementary Table~S17). "
    + (r"Against the unlifted R1, R3 has the higher non-evaluation overhead in "
       r"\RtCrossCount{} combinations and is the cheaper of the two above \RtCross{}\,$\mu$s "
       r"per evaluation under the linear cost model. " if cross else "")
    + r"The size of the gap does not hinge on the particular retry model: over "
    r"\SnSettings{} variants on S2 with soft-target fraction $\alpha\in\{0.25,0.5,0.75\}$ "
    r"and maximum retry share $\bar q\in\{0.5,1\}$, fixed before the runs, R1 needs "
    r"$\SnEvalFactor\times$ more full evaluations than R3, R1$^{\mathrm{fp}}$ equals R3 in "
    r"\SnFpEqual{} of \SnRuns{} combinations and R3 expands $\SnStateFactor\times$ fewer "
    r"states than R1$^{\mathrm{fp}}$ (Supplementary Table~S18). The variants keep the "
    r"exponential tail of Section~\ref{sec:feedback}; other retry laws are not tested. "
    r"R1, R2 and R1$^{\mathrm{fp}}$ are checked against the retry objectives of every "
    r"completion of every one of the \RtPrefixes{} prefixes of S1 per workload "
    r"(\RtChecks{} bound/design pairs); as for R3, the only excess is the evaluator's "
    r"fixed-point truncation, at most $\RtExcess\times10^{-12}$ in relative terms. These "
    r"runs used Python 3.12 on Linux/aarch64; the R3 evaluation counts equal those of "
    r"\RefFeedbackTab{}, obtained on macOS.")
(G / "e20.tex").write_text(e20 + "\n")
(G / "e21.tex").write_text(e21 + "\n")
print("macros:")
for k, v in macros.items():
    print("  \\%-22s %s" % (k, v))
