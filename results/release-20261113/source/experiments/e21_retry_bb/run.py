"""E21: the retry model of Section 4.6 against the generic partial cost
(protocol: experiments/e20_regimes/PROTOCOL.md, fixed before the runs).

All configurations use the retry evaluator and the retry-certified archive; they
differ only in the bound.

  R0  exhaustive enumeration (the oracle)
  R1  generic partial cost (G1c) at the exogenous rate: the retry amplification
      is determined only by a complete design, so the generic bound sees it as
      zero
  R2  the term-wise bound of Section 4.2 at the exogenous rate (no fixed point)
  R3  the bound of Proposition 5 (the configuration of Section 6.13)
  R1fp  R1 lifted through the fixed point of Proposition 5, certified like R3

R1 and R2 are admissible for the retry model: every term is non-decreasing in the
rate and the effective rate is at least the exogenous one.  ``--check`` verifies
this on every prefix and completion of S1.
"""
from __future__ import annotations

import argparse, csv, dataclasses, itertools, json, math, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "e17_generic_bb"))
sys.path.insert(0, str(HERE.parent / "e15_feedback"))

from bounders import CachedPartialCostBounder  # noqa: E402
from fb_driver import FbBounder  # noqa: E402
from hcadse import feedback  # noqa: E402
from hcadse import intervals as iv  # noqa: E402
from hcadse import search as search_mod  # noqa: E402
from hcadse.bounder import Bounder  # noqa: E402
from hcadse.metrics import objset  # noqa: E402
from hcadse.numeric import decimal_value  # noqa: E402
from hcadse.model import VAR_ORDER, WORKLOADS, make_space  # noqa: E402
from hcadse.search import exhaustive, hca_dse, structurally_valid  # noqa: E402


class R1(CachedPartialCostBounder):
    certified_objectives = staticmethod(feedback.certified_objectives)


class R2(Bounder):
    certified_objectives = staticmethod(feedback.certified_objectives)


class R1fp(R1):
    """The generic partial cost lifted through the fixed point of Proposition 5,
    certified like R3.  The proposal iterates the rate in binary64; the
    certification iterates it in directed-rounding decimal arithmetic from the
    exogenous rate, each iterate rounded down, with q = 0 while the certified
    partial-cost latency is zero, and evaluates the certified partial cost at the
    last iterate, which lies below the least fixed point of every completion."""

    def __init__(self, space, wl, use_queue_bound=True):
        super().__init__(space, wl, use_queue_bound=use_queue_bound)
        self._wl0 = wl
        self._rates = {}
        self._certified = {}

    def _at(self, rate):
        return dataclasses.replace(self._wl0, rate=rate / self._wl0.n_dev)

    def _rate(self, p):
        key = self._key(p)
        if key not in self._rates:
            lam0 = self._wl0.Lambda
            theta = feedback.SOFT * self._wl0.deadline
            lam = lam0
            for _ in range(feedback.ITERS):
                self.wl = self._at(lam)
                L = CachedPartialCostBounder._float_bounds(self, p)["L"]
                self.wl = self._wl0
                if not (L < float("inf")):
                    break
                q = math.exp(-theta / L) if L > 0 else 0.0
                nxt = lam0 * (1.0 + feedback.MAX_RETRY * q)
                done = abs(nxt - lam) <= feedback.FP_ATOL + feedback.FP_RTOL * max(lam, nxt)
                lam = min(lam, nxt) if done else nxt
                if done:
                    break
            self._rates[key] = max(lam0, lam * (1 - 1e-9))
        return self._rates[key]

    def fast_bounds(self, p):
        rate = self._rate(p)
        self.wl = self._at(rate)
        try:
            self._cache.pop(self._key(p), None)
            return super().fast_bounds(p)
        finally:
            self.wl = self._wl0

    def certify(self, p):
        key = self._key(p)
        if key in self._certified:
            self.calls += 1
            return self._certified[key]
        w0 = self._wl0
        n = iv.dec(w0.n_dev)
        base = n * iv.dec(w0.rate)
        soft, max_retry = iv._retry_parameters(None)
        tau = soft * iv.dec(w0.deadline)
        z = base
        try:
            for _ in range(feedback.ITERS):
                self.wl = dataclasses.replace(w0, rate=iv._op(iv.ROUND_FLOOR, lambda: z / n))
                lat = self._bounds(p)["L"]
                if lat.lo == iv.DINF:
                    break
                q = (iv.Decimal(0) if lat.lo <= 0
                     else (-(iv.Interval.point(tau) / lat)).exp().lo)
                nxt = iv._op(iv.ROUND_FLOOR, lambda: base * (iv.Decimal(1) + max_retry * q))
                if nxt <= z:
                    break
                z = nxt
            self.wl = dataclasses.replace(w0, rate=iv._op(iv.ROUND_FLOOR, lambda: z / n))
            out = self._wrap(p)
        finally:
            self.wl = w0
        self._certified[key] = out
        return out

    bounds = certify


CONFIGS = (("R1", R1), ("R1fp", R1fp), ("R2", R2), ("R3", FbBounder))


def timed(fn, repeats):
    walls, evals = [], []
    out = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn()
        walls.append(time.perf_counter() - t0)
        evals.append(out.t_eval)
    return out, statistics.median(walls), statistics.median(evals)


def check(scale="S1"):
    """Every certified lower end of R1, R1fp and R2 is at most the retry objective of
    every completion, on every prefix of the order.  As in the check of Proposition 5
    (experiments/e15_feedback/check_admissible.py), the evaluator stops its fixed-point
    iteration at a relative residual of 1e-12, below the exact least fixed point, so a
    relative excess up to 100 times that tolerance is allowed and the largest excess
    is recorded."""
    rows = []
    for wname, wl in WORKLOADS.items():
        space = make_space(scale)
        bds = {"R1": R1(space, wl), "R1fp": R1fp(space, wl), "R2": R2(space, wl)}
        prefixes = checks = 0
        excess = 0.0
        for depth in range(len(VAR_ORDER) + 1):
            head, rest = VAR_ORDER[:depth], list(VAR_ORDER[depth:])
            for combo in itertools.product(*[space.domain(v) for v in head]):
                p = dict(zip(head, combo))
                if not structurally_valid(p):
                    continue
                prefixes += 1
                lbs = {k: b.certify(p) for k, b in bds.items()}
                for tail in itertools.product(*[space.domain(v) for v in rest]):
                    x = dict(p); x.update(zip(rest, tail))
                    if not structurally_valid(x):
                        continue
                    f = feedback.evaluate(x, wl).objectives
                    for k, lb in lbs.items():
                        checks += 1
                        low = (lb["_intervals"][n].lo for n in ("L", "E", "C", "D"))
                        for i, v in enumerate(low):
                            if f[i] != float("inf"):
                                # cost is exact decimal on both sides (Section 4.4)
                                if i == 2:   # cost is exact decimal on both sides
                                    assert v <= decimal_value(f[i]), (k, wname, p, x, i, v)
                                    continue
                                fv = float(v)
                                if fv > f[i] and f[i] > 0:
                                    excess = max(excess, (fv - f[i]) / f[i])
                                assert fv <= f[i] * (1 + 100 * feedback.FP_RTOL) + 1e-12, (
                                    k, wname, p, x, i, v, f[i])
        rows.append(dict(scale=scale, workload=wname, prefixes=prefixes, checks=checks,
                         violations=0, max_relative_excess=excess))
        print(json.dumps(rows[-1]), flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="S1,S2,S3")
    ap.add_argument("--workloads", default=",".join(WORKLOADS))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--part", default=None)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--configs", default="R1,R1fp,R2,R3")
    ap.add_argument("--soft", type=float, default=None, help="retry model variant (E22)")
    ap.add_argument("--max-retry", type=float, default=None, help="retry model variant (E22)")
    ap.add_argument("--out", default="results/e21_retry_bb")
    a = ap.parse_args()
    if a.soft is not None:
        feedback.SOFT = a.soft
    if a.max_retry is not None:
        feedback.MAX_RETRY = a.max_retry
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.check:
        (out / "admissible_S1.json").write_text(json.dumps(check(), indent=1) + "\n")
        return
    if a.merge:
        rs = {s: i for i, s in enumerate(("S1", "S2", "S3"))}
        ws = {w: i for i, w in enumerate(WORKLOADS)}
        cs = {"R0": 0, "R1": 1, "R1fp": 2, "R2": 3, "R3": 4}
        rows, seen = [], set()
        for f in sorted(out.glob("retry_*.csv")):
            for r in csv.DictReader(f.open()):
                key = (r["scale"], r["workload"], r["config"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
        rows.sort(key=lambda r: (rs[r["scale"]], ws[r["workload"]], cs[r["config"]]))
        with (out / "retry.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print("merged", len(rows), "rows")
        return
    rows = []
    original_eval, original_bounder = search_mod.evaluate, search_mod.Bounder
    try:
        search_mod.evaluate = feedback.evaluate
        for scale in a.scales.split(","):
            space = make_space(scale)
            for wname in a.workloads.split(","):
                wl = WORKLOADS[wname]
                ex, wall, et = timed(lambda: exhaustive(space, wl), 1)
                ref = objset(ex.front)
                base = dict(scale=scale, workload=wname)
                rows.append(dict(base, config="R0", evals=ex.n_evaluated, nodes=ex.n_evaluated,
                                 bound_calls=0, seconds=round(wall, 4),
                                 overhead_seconds=round(wall - et, 4), front=len(ref),
                                 exact=True))
                print(json.dumps(rows[-1]), flush=True)
                for cname, bounder in CONFIGS:
                    if cname not in a.configs.split(","):
                        continue
                    search_mod.Bounder = bounder
                    try:
                        st, wall, et = timed(lambda: hca_dse(space, wl), a.repeats)
                    finally:
                        search_mod.Bounder = original_bounder
                    same = objset(st.front) == ref
                    rows.append(dict(base, config=cname, evals=st.n_evaluated, nodes=st.n_nodes,
                                     bound_calls=st.n_bound_calls, seconds=round(wall, 4),
                                     overhead_seconds=round(wall - et, 4),
                                     front=len(objset(st.front)), exact=bool(same)))
                    print(json.dumps(rows[-1]), flush=True)
                    assert same, ("front differs", scale, wname, cname)
    finally:
        search_mod.evaluate, search_mod.Bounder = original_eval, original_bounder
    name = "retry.csv" if a.part is None else "retry_%s.csv" % a.part
    with (out / name).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", out / name)


if __name__ == "__main__":
    main()
