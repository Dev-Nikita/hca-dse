"""E18: what the analytical screen costs an engineer, not a Pareto metric.

Section 6.12 reports how much of the simulated Pareto front an analytical screen
recovers.  Recall does not say whether a *decision* got worse: a lost front point
may be indistinguishable from a retained one, or it may be the only design that
meets a deadline.  This script asks the decision question on the stored archive,
with no further simulation.

A decision scenario is "minimise objective j subject to a cap on objective k".
The caps are quantiles of the archive's own distribution, so they are feasible by
construction and need no hand-chosen numbers.  For every scenario we compare

  * the best value over the whole simulated archive, and
  * the best value over the designs the sealed prospective screen selected
    (audit/results/h6/manifests, copied to <out>/selections), scored with the same
    hybrid objectives (simulated latency, analytical energy, cost and volume),

and report the relative regret, whether the screen retained any admissible
design at all (coverage), and whether it found the archive's own optimum.

The archive is every DES-feasible design of the stored sweep, including designs the
analytical model rejects as infeasible; the screen can never select those, so they
count against it. The scenario grid follows the single rule in SCENARIOS below.
"""
from __future__ import annotations

import argparse, csv, gzip, json, shutil, statistics, sys
from pathlib import Path

import numpy as np

NAMES = ("latency", "energy", "cost", "volume")
# pre-registered grid: (objective to minimise, objective capped, quantile of the cap)
SCENARIOS = [(j, k, q)
             for j in range(4)
             for k, q in [((0 if j != 0 else 2), 0.10),
                          ((0 if j != 0 else 2), 0.25),
                          ((0 if j != 0 else 2), 0.50)]]


def design_id(design):
    return json.dumps(design, sort_keys=True, separators=(",", ":"))


def load(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    d = json.load(opener(path))
    rows = d if isinstance(d, list) else d["_dump"]
    ids = [design_id(r["design"]) for r in rows]
    des = np.array([r["des"] for r in rows], float)
    assert np.all(np.isfinite(des)), "archive must hold DES-feasible designs only"
    return ids, des


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dumps", nargs="+")
    ap.add_argument("--selections", default="audit/results/h6/manifests")
    ap.add_argument("--eps", default="0.00,0.10,0.20")
    ap.add_argument("--out", default="results/e18_decision_regret")
    a = ap.parse_args()
    out = Path(a.out); (out / "selections").mkdir(parents=True, exist_ok=True)

    rows, detail = [], []
    for path in sorted(a.dumps):
        stem = Path(path).name.split(".")[0]
        scale, workload = stem.split("_", 1)
        manifest_path = Path(a.selections) / (stem + ".json")
        manifest = json.loads(manifest_path.read_text())
        shutil.copyfile(manifest_path, out / "selections" / manifest_path.name)
        ids, des = load(path)
        for key in a.eps.split(","):
            selected = set(manifest["selections"][key]["ids"])
            kept = np.array([i in selected for i in ids])
            regrets, misses, exact_hits = [], 0, 0
            for j, k, q in SCENARIOS:
                cap = float(np.quantile(des[:, k], q))
                adm_all = des[:, k] <= cap
                adm_kept = adm_all & kept
                best_all = float(des[adm_all, j].min())
                if not adm_kept.any():
                    misses += 1
                    detail.append(dict(scale=scale, workload=workload, eps=float(key),
                                       minimise=NAMES[j], capped=NAMES[k], quantile=q,
                                       best_archive=best_all, best_screened="",
                                       regret="", coverage_miss=True))
                    continue
                best_kept = float(des[adm_kept, j].min())
                r = (best_kept - best_all) / abs(best_all) if best_all else 0.0
                regrets.append(r)
                exact_hits += int(r <= 1e-12)
                detail.append(dict(scale=scale, workload=workload, eps=float(key),
                                   minimise=NAMES[j], capped=NAMES[k], quantile=q,
                                   best_archive=best_all, best_screened=best_kept,
                                   regret=r, coverage_miss=False))
            n = len(regrets)
            rows.append(dict(
                scale=scale, workload=workload, eps=float(key),
                scenarios=len(SCENARIOS), kept=int(kept.sum()),
                selected=len(selected), archive=len(des),
                coverage_misses=misses, optimum_found=exact_hits,
                regret_median=(statistics.median(regrets) if n else ""),
                regret_p90=(float(np.percentile(regrets, 90)) if n else ""),
                regret_max=(max(regrets) if n else "")))
            print(json.dumps(rows[-1]), flush=True)

    for name, data in (("decision_regret.csv", rows), ("scenarios.csv", detail)):
        with (out / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]))
            w.writeheader(); w.writerows(data)
    print("wrote", out / "decision_regret.csv")


if __name__ == "__main__":
    main()
