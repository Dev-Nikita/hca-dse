import sys, os, csv, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.size": 8, "figure.dpi": 200, "savefig.bbox": "tight"})
R = lambda f: list(csv.DictReader(open(f)))

# F1 funnel
d = [r for r in R("results/e1_pruning.csv")]
fig, ax = plt.subplots(figsize=(5, 2.6))
scales = ["S1", "S2", "S3", "S4"]; wls = ["telemetry", "control", "sensing"]
xs, labels = [], []
for i, s in enumerate(scales):
    for j, w in enumerate(wls):
        r = [q for q in d if q["scale"] == s and q["workload"] == w][0]
        x = i * 4 + j
        ax.bar(x, int(r["raw"]), color="#d9d9d9")
        ax.bar(x, int(r["raw"]) - int(r["pruned_struct"]), color="#9ecae1")
        ax.bar(x, int(r["raw"]) - int(r["pruned_struct"]) - int(r["pruned_bound"]), color="#4292c6")
        ax.bar(x, int(r["evals"]), color="#08519c")
        xs.append(x); labels.append(f"{s}\n{w[:4]}")
ax.set_yscale("log"); ax.set_xticks(xs); ax.set_xticklabels(labels, fontsize=5)
ax.set_ylabel("architectures (log)")
ax.legend(["raw space", "after structural", "after feasibility bounds", "fully evaluated"],
          fontsize=5, ncol=2)
fig.savefig("figures/fig1_funnel.png"); plt.close(fig)

# F2 cost crossover
d = R("results/e2_costsweep.csv")
fig, ax = plt.subplots(figsize=(4, 2.6))
for s in ("S2", "S3"):
    for w in wls:
        sub = sorted([r for r in d if r["scale"] == s and r["workload"] == w],
                     key=lambda r: float(r["C_E"]))
        ax.plot([float(r["C_E"]) for r in sub], [float(r["speedup"]) for r in sub],
                marker="o", ms=2, label=f"{s}/{w}")
ax.axvline(19.5e-3, ls="--", c="k", lw=0.8); ax.text(2.1e-2, 1.5, "DES evaluator\n19.5 ms", fontsize=5)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("evaluator cost $C_E$ [s]")
ax.set_ylabel("speedup vs exhaustive"); ax.axhline(1, c="grey", lw=0.5)
ax.legend(fontsize=5, ncol=2); fig.savefig("figures/fig2_cost_crossover.png"); plt.close(fig)

# F3 scalability
d = R("results/e5_scalability.csv")
fig, ax = plt.subplots(figsize=(4, 2.6))
for w in wls:
    sub = sorted([r for r in d if r["workload"] == w], key=lambda r: int(r["raw"]))
    ax.plot([int(r["raw"]) for r in sub], [int(r["nodes"]) for r in sub], marker="o", ms=3, label=f"{w}: partial states")
    ax.plot([int(r["raw"]) for r in sub], [int(r["evals"]) for r in sub], marker="s", ms=3, ls="--", label=f"{w}: full evaluations")
ax.plot([int(r["raw"]) for r in sub], [int(r["raw"]) for r in sub], c="k", lw=0.8, label="exhaustive")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("raw design space $|\\mathcal{X}|$"); ax.set_ylabel("count")
ax.legend(fontsize=5); fig.savefig("figures/fig3_scalability.png"); plt.close(fig)

# F4 HV vs budget
d = R("results/e3_baselines.csv")
fig, axes = plt.subplots(1, 3, figsize=(6.5, 2.2), sharey=True)
for ax, w in zip(axes, wls):
    for m, c in (("nsga2", "#08519c"), ("random", "#bdbdbd")):
        bs = sorted({int(r["budget"]) for r in d if r["method"] == m and r["seed"]})
        data = [[float(r["hv_ratio"]) for r in d if r["scale"] == "S3" and r["workload"] == w
                 and r["method"] == m and int(r["budget"]) == b] for b in bs]
        ax.boxplot(data, positions=range(len(bs)), widths=0.5,
                   patch_artist=True, boxprops=dict(facecolor=c, lw=0.5),
                   medianprops=dict(color="k", lw=0.8), flierprops=dict(ms=1))
        ax.set_xticks(range(len(bs))); ax.set_xticklabels(bs, fontsize=6)
    h = [r for r in d if r["scale"] == "S3" and r["workload"] == w and r["method"] == "HCA-DSE"][0]
    ax.axhline(1.0, c="crimson", lw=1.0)
    ax.set_title(f"{w} (HCA-DSE: {h['n_eval']} evals, HV=1.0)", fontsize=6)
    ax.set_xlabel("evaluation budget")
axes[0].set_ylabel("HV ratio vs exhaustive")
fig.savefig("figures/fig4_hv_budget.png"); plt.close(fig)

# F5 ablation
d = R("results/e4_ablation.csv")
fig, ax = plt.subplots(figsize=(4.2, 2.4))
vs = ["structural-only", "struct+feasibility", "struct+dominance", "HCA-full"]
for i, w in enumerate(wls):
    ys = [int([r for r in d if r["scale"] == "S3" and r["workload"] == w and r["variant"] == v][0]["evals"]) for v in vs]
    ax.bar([j + i * 0.27 for j in range(len(vs))], ys, width=0.26, label=w)
ax.set_yscale("log"); ax.set_xticks([j + 0.27 for j in range(len(vs))])
ax.set_xticklabels(vs, fontsize=5.5); ax.set_ylabel("full evaluations (S3)")
ax.legend(fontsize=6); fig.savefig("figures/fig5_ablation.png"); plt.close(fig)

# F6 analytical vs simulation
d = R("results/e6_simvalidation.csv")
fig, ax = plt.subplots(figsize=(3.2, 3.0))
for w, m in zip(wls, "osv"):
    sub = [r for r in d if r["workload"] == w]
    ax.scatter([float(r["L_sim"]) * 1e3 for r in sub], [float(r["L_analytical"]) * 1e3 for r in sub],
               s=8, marker=m, label=w)
lim = [1, 2000]; ax.plot(lim, lim, "k--", lw=0.8)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("simulated mean latency [ms]"); ax.set_ylabel("analytical latency [ms]")
ax.legend(fontsize=6); fig.savefig("figures/fig6_model_vs_sim.png"); plt.close(fig)
print("figures written:", os.listdir("figures"))
