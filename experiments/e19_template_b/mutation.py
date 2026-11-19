"""Mutation analysis of the template B search.

Each mutant changes one decision of the bound or of the search.  It is killed if
(a) the search front differs from the front of the independent reference
implementation (oracle.py) on scale B1 for the three workloads or for one of the
boundary workloads below, (b) the bound exceeds the exact objectives of a
completion of a sampled partial assignment, or (c) a pruning test decides a bound
that equals a limit or an archived vector exactly in the wrong direction.  The boundary workloads move a limit
onto, just above or just below the exact value of a front design, which is where
a tolerance or a non-strict comparison would change the outcome.
"""
from __future__ import annotations

import argparse, dataclasses, json, math, random, sys
from fractions import Fraction as Q
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hcadse import template_b as tb
import oracle as orc

SCALE = "B1"


def reference(wl):
    vecs = []
    for d in orc.designs(SCALE):
        if orc.valid(d):
            r = orc.objectives(d, wl)
            if r is not None and r[1]:
                vecs.append(tuple(r[0]))
    return orc.pareto(vecs)


def boundary_workloads():
    """Limits placed on the exact objective values of front designs."""
    out = {}
    up = lambda v: float(v) if Q(float(v)) >= v else math.nextafter(float(v), math.inf)
    down = lambda v: float(v) if Q(float(v)) < v else math.nextafter(float(v), -math.inf)
    for name, wl in tb.WORKLOADS.items():
        front = reference(wl)
        mid = front[len(front) // 2]
        L, E, C, _ = mid
        out[name + "/L>=front"] = dataclasses.replace(wl, deadline=up(L))
        out[name + "/L<front"] = dataclasses.replace(wl, deadline=down(L))
        out[name + "/E>=front"] = dataclasses.replace(wl, E_max=up(E))
        out[name + "/E<front"] = dataclasses.replace(wl, E_max=down(E))
        for j, v in enumerate(front[:: max(1, len(front) // 6)]):
            out[name + "/L<front%d" % j] = dataclasses.replace(wl, deadline=down(v[0]))
    return out


_TABLE = {}


def _completions(wl):
    key = id(wl)
    if key not in _TABLE:
        rows = []
        for d in orc.designs(SCALE):
            if orc.valid(d):
                r = orc.objectives(d, wl)
                if r is not None:
                    rows.append((orc.to_prod(d), r[0]))
        _TABLE[key] = rows
    return _TABLE[key]


def admissible(samples, seed=7):
    rng = random.Random(seed)
    bad = 0
    for wl in tb.WORKLOADS.values():
        rows = _completions(wl)
        sure = tb.Bounds(SCALE, wl, exact=True)
        for _ in range(samples):
            x, _ = rng.choice(rows)
            depth = rng.randrange(0, len(tb.ORDER))
            p = {v: x[v] for v in tb.ORDER[:depth]}
            lb = sure(p)
            for y, f in rows:
                if all(y[v] == p[v] for v in p) and any(lb[i] > f[i] for i in range(4)):
                    bad += 1
                    break
    return bad


def unit_checks():
    """Decisions on a bound that equals a limit or an archived vector exactly."""
    wl = tb.WORKLOADS["vision"]
    lim = (Q(wl.deadline), Q(wl.E_max), Q(wl.C_max), Q(0))
    a = (Q(1), Q(2), Q(3), Q(4))
    fails = []
    if tb._infeasible(lim, wl, Q):
        fails.append("a bound equal to every limit is pruned as infeasible")
    if tb._dominated(a, [a]):
        fails.append("a bound equal to an archived vector is pruned as dominated")
    if not tb._dominated((Q(1), Q(2), Q(3), Q(5)), [a]):
        fails.append("a strictly dominated bound is kept")
    return fails


def _close(a, b):
    return len(a) == len(b) and all(abs(float(u[i]) - float(v[i])) <= 1e-12 * max(1.0, abs(float(v[i])))
                                    for u, v in zip(a, b) for i in range(4))


_REF = {}


def run_fronts(workloads):
    """Workloads on which the search front differs from the reference front:
    exactly, and beyond binary64 rounding."""
    exact, beyond = [], []
    for name, wl in workloads.items():
        if name not in _REF:
            _REF[name] = reference(wl)
        ref = _REF[name]
        try:
            got = sorted(tb.search(SCALE, wl).front)
        except Exception as e:  # a crash also kills the mutant
            exact.append(name); beyond.append(name)
            continue
        if got != ref:
            exact.append(name)
            if not _close(got, ref):
                beyond.append(name)
    return exact, beyond


# --- mutants -----------------------------------------------------------------

def m_inflate_latency():
    f = tb.Bounds.__call__
    def g(self, p):
        L, E, C, D = f(self, p)
        return (L * self.R(1.02) if L != tb.INF else L, E, C, D)
    tb.Bounds.__call__ = g


def m_inflate_rho():
    f = tb.Bounds._determined_rho
    def g(self, p, tier):
        r = f(self, p, tier)
        return None if r is None else r * self.R(1.5)
    tb.Bounds._determined_rho = g


def m_service_min_capacity():
    """An unassigned stage bounded with the slowest instead of the fastest class."""
    f = tb.Bounds._stage
    def g(self, p, i):
        tiers = self._tiers(p, i)
        if len(tiers) == 1 and len(self._classes(p, tiers[0])) == 1:
            return f(self, p, i)
        if not self.relax:
            return self.R(0)
        return min(self.R(self.wl.w[i]) / self.R(min(c.C for c in self._classes(p, t)))
                   for t in tiers)
    tb.Bounds._stage = g


def m_access_energy_max():
    """Unassigned link: access energy bounded with the most expensive link."""
    f = tb.Bounds._edge_volume_energy
    def g(self, p, k):
        if "link" in p:
            return f(self, p, k)
        save = self.dom["link"]
        self.dom = dict(self.dom, link=[max(save, key=lambda l: l.e)])
        try:
            return f(self, p, k)
        finally:
            self.dom = dict(self.dom, link=save)
    tb.Bounds._edge_volume_energy = g


def m_no_certification():
    """Take every binary64 proposal without the exact confirmation."""
    tb._infeasible = lambda lb, wl, R: tb._propose_infeasible([float(v) for v in lb], wl)
    tb._dominated = lambda lb, archive: tb._propose_dominated(
        [float(v) for v in lb], [[float(v) for v in a] for a in archive])


def m_nonstrict_infeasible():
    tb._infeasible = lambda lb, wl, R: (lb[0] >= R(wl.deadline) or lb[2] >= R(wl.C_max)
                                        or lb[1] >= R(wl.E_max))


def m_nonstrict_dominance():
    tb._dominated = lambda lb, archive: any(all(a[i] <= lb[i] for i in range(4)) for a in archive)


def m_binary64_leaf():
    f = tb.evaluate
    tb.evaluate = lambda x, wl, exact=False: f(x, wl, exact=False)


MUTANTS = [
    ("latency bound inflated by 2%", m_inflate_latency),
    ("utilisation in the waiting term inflated by 50%", m_inflate_rho),
    ("unassigned stage bounded with the slowest class", m_service_min_capacity),
    ("unassigned link: access energy of the most expensive link", m_access_energy_max),
    ("binary64 proposal taken without exact confirmation", m_no_certification),
    ("infeasibility pruning with a non-strict comparison", m_nonstrict_infeasible),
    ("dominance pruning with a non-strict comparison", m_nonstrict_dominance),
    ("leaf feasibility and archive in binary64", m_binary64_leaf),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=150)
    ap.add_argument("--out", default="results/e19_template_b/mutation.json")
    a = ap.parse_args()
    import importlib
    base = dict(tb.WORKLOADS)
    bnd = boundary_workloads()
    allw = dict(base, **bnd)
    # the unmutated code must pass everything
    assert run_fronts(allw) == ([], []), "unmutated search fails a boundary workload"
    assert admissible(a.samples) == 0, "unmutated bound not admissible"
    assert unit_checks() == [], unit_checks()
    rows = []
    for name, mut in MUTANTS:
        importlib.reload(tb)
        mut()
        exact, beyond = run_fronts(allw)
        adm = admissible(a.samples)
        unit = unit_checks()
        rows.append(dict(mutant=name, front_failures=len(exact),
                         front_failures_beyond_rounding=len(beyond),
                         failing=beyond[:6] or exact[:6],
                         admissibility_violations=adm, unit_failures=unit,
                         killed_by_front=bool(exact),
                         killed=bool(exact) or adm > 0 or bool(unit)))
        print(json.dumps(rows[-1]), flush=True)
    importlib.reload(tb)
    res = dict(scale=SCALE, workloads=len(base), boundary_workloads=len(bnd),
               admissibility_samples=a.samples * len(base), mutants=rows,
               killed=sum(r["killed"] for r in rows),
               killed_by_front=sum(r["killed_by_front"] for r in rows), total=len(rows))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print("killed %d of %d (%d by a front)" % (res["killed"], res["total"], res["killed_by_front"]))


if __name__ == "__main__":
    main()
