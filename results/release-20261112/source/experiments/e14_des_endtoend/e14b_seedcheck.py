"""Seed robustness of the S3 end-to-end result.

S3 was run with one seed per design.  This script re-simulates, with five seeds,
every design that the single-seed simulated front does not dominate by more than
a relative margin eps -- the set that could plausibly change front membership
under simulation noise -- and recomputes the simulated reference front and the
two-level recall from the five-seed medians.  Designs outside that set are
dominated by more than eps and are left at their single-seed value; the check is
therefore conditional on eps, which is reported.

It also reports the magnitude of the noise itself: the per-design relative
spread of the simulated mean latency over the five seeds.
"""
import argparse, json, statistics, sys
import numpy as np
from hcadse.model import make_space, WORKLOADS
from hcadse.simulate import simulate
from margin import nondominated_mask, dominated_by_front

N_REQ, WARMUP = 3000, 400
SEEDS = (0, 1, 2, 3, 4)


def rebuild(space, named):
    out = {}
    for k, v in named.items():
        for o in space.domain(k):
            if getattr(o, "name", o) == v:
                out[k] = o
                break
        else:
            raise KeyError((k, v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--out", default="out/seedcheck.json")
    a = ap.parse_args()
    rows = []
    for path in a.runs:
        d = json.load(open(path))
        sp, wl = make_space(d["scale"]), WORKLOADS[d["workload"]]
        dump = d["_dump"]
        des = np.array([r["des"] for r in dump], float)
        an = np.array([r["analytic"] for r in dump], float)
        ok = np.all(np.isfinite(des), axis=1) & np.all(np.isfinite(an), axis=1)
        idx = np.where(ok)[0]
        des, an = des[ok], an[ok]
        front0 = nondominated_mask(des)
        cand = ~dominated_by_front(des, des[front0], a.eps)
        cand |= front0
        n = int(cand.sum())
        print("%s %s: %d feasible, front0 %d, candidates at eps=%.2f: %d (%d sims)"
              % (d["scale"], d["workload"], len(des), int(front0.sum()), a.eps, n,
                 n * len(SEEDS)), flush=True)
        if a.count_only:
            continue
        # --- five seeds on the candidate set ---------------------------------
        des5 = des.copy()
        spread = []
        for j in np.where(cand)[0]:
            x = rebuild(sp, dump[idx[j]]["design"])
            means = [simulate(x, wl, n_req=N_REQ, warmup=WARMUP, seed=s)["mean"]
                     for s in SEEDS]
            des5[j, 0] = statistics.median(means)
            spread.append((max(means) - min(means)) / max(statistics.median(means), 1e-12))
        front5 = nondominated_mask(des5)
        # --- the two-level protocol, recomputed from the same values ---------
        anf = nondominated_mask(an)
        sel = np.where(anf)[0]
        two0 = np.zeros(len(des), bool); two0[sel] = nondominated_mask(des[sel])
        two5 = np.zeros(len(des), bool); two5[sel] = nondominated_mask(des5[sel])
        rec0 = int((two0 & front0).sum()) / max(int(front0.sum()), 1)
        rec5 = int((two5 & front5).sum()) / max(int(front5.sum()), 1)
        rows.append(dict(scale=d["scale"], workload=d["workload"], eps=a.eps,
                         candidates=n, sims=n * len(SEEDS),
                         front0=int(front0.sum()), front5=int(front5.sum()),
                         front_stable=int((front0 & front5).sum()),
                         twolevel_recall_1seed=rec0, twolevel_recall_5seed=rec5,
                         spread_median=statistics.median(spread),
                         spread_p90=float(np.percentile(spread, 90)),
                         spread_max=max(spread)))
        print(json.dumps(rows[-1], indent=1), flush=True)
    if rows:
        json.dump(rows, open(a.out, "w"), indent=2)


if __name__ == "__main__":
    main()
