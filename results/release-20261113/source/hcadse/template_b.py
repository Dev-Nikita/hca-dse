"""A second, structurally different architecture template (template B).

Template A (hcadse.model) is a chain of three stages over edge, gateway and cloud
tiers, with one categorical placement policy.  Template B differs in the three
places where the bounds of Section 4 do their work:

* the application is a fork-join graph of five stages,

      ingest -> filter -> { aggregate -> analytics ,  archive }

  and a request completes when both branches have completed, so end-to-end
  latency is a maximum over paths rather than a sum;
* every stage is placed by its own decision variable, so the load of a tier,
  and with it the waiting time of every stage on that tier, is determined
  jointly by up to five placement variables, its node count and its class;
* the tiers are edge, fog and cloud, with the access link between edge and fog
  a design variable and the fog-cloud WAN fixed.

The bound construction is the one of Section 4, applied term by term: every
term enters exactly once its support is assigned (Lemma 2) and as its minimum
over the reachable values otherwise (Lemma 1); the latency bound composes the
per-path term bounds through the same sum and maximum as the latency itself,
which preserves admissibility because both operators are non-decreasing in
every argument.  The generic partial cost uses the same composition with zero
for every undetermined term.

Only the standard library is used.
"""
from __future__ import annotations

import itertools
import math
import time
from fractions import Fraction
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

INF = float("inf")
TIERS = ("edge", "fog", "cloud")
RANK = {"edge": 0, "fog": 1, "cloud": 2}


@dataclass(frozen=True)
class Node:
    name: str
    C: float          # capacity [MIPS]
    P_idle: float     # [W]
    P_peak: float     # [W]
    cost: float       # normalised cost per node


@dataclass(frozen=True)
class Link:
    name: str
    B: float          # [Mb/s]
    prop: float       # [s]
    e: float          # [J/MB]
    cost: float       # per attached node


WAN_B, WAN_PROP, WAN_E = 400.0, 0.015, 0.05

EDGE = [Node("e-low", 1500.0, 3.0, 10.0, 0.8), Node("e-med", 4000.0, 6.0, 22.0, 1.9),
        Node("e-high", 9000.0, 11.0, 45.0, 4.1), Node("e-max", 16000.0, 18.0, 70.0, 7.0)]
FOG = [Node("f-low", 8000.0, 15.0, 55.0, 3.0), Node("f-med", 18000.0, 28.0, 110.0, 6.0),
       Node("f-high", 32000.0, 45.0, 180.0, 10.5)]
CLOUD = [Node("c-med", 50000.0, 0.0, 220.0, 7.0), Node("c-high", 120000.0, 0.0, 460.0, 15.0),
         Node("c-max", 250000.0, 0.0, 900.0, 28.0)]
LINKS = [Link("l-std", 100.0, 0.003, 0.12, 0.5), Link("l-fast", 1000.0, 0.001, 0.05, 1.2),
         Link("l-dedicated", 10000.0, 0.0005, 0.02, 3.0)]

# stages: name, allowed tiers
STAGES = (("ingest", ("edge", "fog")), ("filter", ("edge", "fog")),
          ("aggregate", ("fog", "cloud")), ("analytics", ("fog", "cloud")),
          ("archive", ("fog", "cloud")))
# precedence edges (source stage, destination stage); -1 is the device source
EDGES = ((-1, 0), (0, 1), (1, 2), (2, 3), (1, 4))
# the two paths after the fork share edges (-1,0), (0,1)
PREFIX = ((-1, 0), (0, 1))
BRANCHES = (((1, 2), (2, 3)), ((1, 4),))
PLACE = tuple("p_" + name for name, _ in STAGES)


@dataclass(frozen=True)
class Workload:
    name: str
    Lambda: float                 # system request rate [1/s]
    w: Tuple[float, ...]          # work per stage [MI]
    s_in: Tuple[float, ...]       # inbound payload per edge in EDGES order [MB]
    deadline: float               # [s]
    C_max: float
    E_max: float
    rho_max: float = 0.85
    horizon: float = 3600.0


WORKLOADS = {
    "vision": Workload("vision", 30.0, (60.0, 90.0, 40.0, 260.0, 10.0),
                       (2.0, 1.2, 0.4, 0.1, 0.8), 0.9, 120.0, 4.0e6),
    "fusion": Workload("fusion", 120.0, (12.0, 25.0, 30.0, 70.0, 6.0),
                       (0.08, 0.06, 0.04, 0.01, 0.05), 0.35, 110.0, 3.5e6),
    "batch": Workload("batch", 8.0, (150.0, 200.0, 300.0, 900.0, 40.0),
                      (6.0, 4.0, 2.0, 0.5, 3.0), 3.0, 140.0, 5.0e6),
}

ORDER = ("n_e", "k_e", "n_f", "k_f") + PLACE + ("link", "k_c")

SCALES = {
    "B1": dict(n_e=(1, 2, 4), k_e=EDGE[:3], n_f=(1, 2), k_f=FOG[:2], link=LINKS[:2],
               k_c=CLOUD[:2]),
    "B2": dict(n_e=(1, 2, 4, 8), k_e=EDGE[:3], n_f=(1, 2, 3), k_f=FOG, link=LINKS,
               k_c=CLOUD),
    "B3": dict(n_e=(1, 2, 3, 4, 6, 8), k_e=EDGE, n_f=(1, 2, 3, 4), k_f=FOG, link=LINKS,
               k_c=CLOUD),
}


def domains(scale: str) -> Dict[str, Sequence]:
    d = dict(SCALES[scale])
    for var, (_, allowed) in zip(PLACE, STAGES):
        d[var] = allowed
    return d


def raw_size(scale: str) -> int:
    return math.prod(len(v) for v in domains(scale).values())


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------

def well_formed(x: dict) -> bool:
    """Data never moves back towards the devices along an edge: every assigned
    edge goes from a tier to the same or a higher tier."""
    for a, b in EDGES:
        if a < 0:
            continue
        pa, pb = x.get(PLACE[a]), x.get(PLACE[b])
        if pa is not None and pb is not None and RANK[pb] < RANK[pa]:
            return False
    return True


def tier_of(x: dict, i: int) -> str:
    return "edge" if i < 0 else x[PLACE[i]]


def hop(src: str, dst: str):
    """Links crossed between two tiers: list of ('access'|'wan')."""
    lo, hi = sorted((RANK[src], RANK[dst]))
    out = []
    if lo == 0 and hi >= 1:
        out.append("access")
    if lo <= 1 and hi == 2:
        out.append("wan")
    return out


def _count(x, tier):
    return {"edge": x["n_e"], "fog": x["n_f"], "cloud": 1}[tier]


def _cls(x, tier):
    return {"edge": x["k_e"], "fog": x["k_f"], "cloud": x["k_c"]}[tier]


# ---------------------------------------------------------------------------
# evaluator
# ---------------------------------------------------------------------------

def evaluate(x: dict, wl: Workload, exact=False):
    """Objectives (L, E, C, D) and feasibility of a complete design.

    With ``exact=True`` every quantity is computed in rational arithmetic from the
    binary64 parameters (every operation of the model is rational), so the result
    is the exact value of the model; the search uses it for the archive.
    """
    R = Fraction if exact else float
    lam = R(wl.Lambda)
    load = {t: R(0) for t in TIERS}
    for i in range(len(STAGES)):
        load[x[PLACE[i]]] += lam * R(wl.w[i])
    rho = {t: load[t] / (R(_count(x, t)) * R(_cls(x, t).C)) for t in TIERS}
    used = {x[p] for p in PLACE}
    if any(rho[t] >= 1 for t in used):
        return (INF, INF, INF, INF), False
    stage_t = []
    for i in range(len(STAGES)):
        t = x[PLACE[i]]
        service = R(wl.w[i]) / R(_cls(x, t).C)
        stage_t.append(service + service * rho[t] / (2 * (1 - rho[t])))
    link = x["link"]

    def edge_lat(k):
        a, b = EDGES[k]
        total = R(0)
        for kind in hop(tier_of(x, a), tier_of(x, b)):
            if kind == "access":
                total += 8 * R(wl.s_in[k]) / R(link.B) + R(link.prop)
            else:
                total += 8 * R(wl.s_in[k]) / R(WAN_B) + R(WAN_PROP)
        return total

    idx = {e: k for k, e in enumerate(EDGES)}
    pre = sum((edge_lat(idx[e]) for e in PREFIX), R(0)) + stage_t[0] + stage_t[1]
    L = pre + max(sum((edge_lat(idx[e]) + stage_t[e[1]] for e in path), R(0))
                  for path in BRANCHES)

    T = R(wl.horizon)
    E = R(0)
    for t in ("edge", "fog"):
        c = _cls(x, t)
        E += R(_count(x, t)) * (R(c.P_idle) + rho[t] * (R(c.P_peak) - R(c.P_idle))) * T
    E += rho["cloud"] * R(x["k_c"].P_peak) * T
    D = R(0)
    for k, (a, b) in enumerate(EDGES):
        for kind in hop(tier_of(x, a), tier_of(x, b)):
            E += R(wl.s_in[k]) * lam * R(link.e if kind == "access" else WAN_E) * T
            D += R(wl.s_in[k]) * lam
    C = (R(x["n_e"]) * (R(x["k_e"].cost) + R(link.cost))
         + R(x["n_f"]) * (R(x["k_f"].cost) + R(link.cost)) + R(x["k_c"].cost))
    feasible = (all(rho[t] <= R(wl.rho_max) for t in used) and L <= R(wl.deadline)
                and C <= R(wl.C_max) and E <= R(wl.E_max))
    return (L, E, C, D), feasible


# ---------------------------------------------------------------------------
# bounds
# ---------------------------------------------------------------------------

class Bounds:
    """Term-wise bounds over a partial assignment.

    ``relax=True`` gives the bound of this paper: an undetermined term enters as
    its minimum over the reachable values.  ``relax=False`` gives the generic
    assignment-monotone partial cost: an undetermined term enters as zero.  In
    both, a term whose support is assigned enters exactly, and the latency terms
    are composed through the same sum and maximum as the latency itself.
    ``queue=False`` drops the waiting term everywhere (the ablation of Table 6).
    ``exact=True`` computes the bound in rational arithmetic.
    """

    def __init__(self, scale: str, wl: Workload, relax=True, queue=True, exact=False):
        self.dom, self.wl, self.relax, self.queue = domains(scale), wl, relax, queue
        self.R = Fraction if exact else float
        self.calls = 0

    def _d(self, p, var):
        return [p[var]] if var in p else list(self.dom[var])

    def _tiers(self, p, i):
        if i < 0:
            return ["edge"]
        return self._d(p, PLACE[i])

    def _classes(self, p, tier):
        return self._d(p, {"edge": "k_e", "fog": "k_f", "cloud": "k_c"}[tier])

    def _counts(self, p, tier):
        return [1] if tier == "cloud" else self._d(p, {"edge": "n_e", "fog": "n_f"}[tier])

    def _determined_rho(self, p, tier):
        """Utilisation of a tier if its load and capacity are determined, else None."""
        R = self.R
        for var, (_, allowed) in zip(PLACE, STAGES):
            if tier in allowed and var not in p:
                return None
        cls = self._classes(p, tier)
        cnt = self._counts(p, tier)
        if len(cls) != 1 or len(cnt) != 1:
            return None
        load = sum((R(self.wl.Lambda) * R(self.wl.w[i]) for i in range(len(STAGES))
                    if p.get(PLACE[i]) == tier), R(0))
        return load / (R(cnt[0]) * R(cls[0].C))

    def _stage(self, p, i):
        """Lower bound on the time spent in stage i (service plus waiting)."""
        R, wl = self.R, self.wl
        tiers = self._tiers(p, i)
        if len(tiers) == 1 and len(self._classes(p, tiers[0])) == 1:
            t = tiers[0]
            service = R(wl.w[i]) / R(self._classes(p, t)[0].C)
            if self.queue:
                rho = self._determined_rho(p, t)
                if rho is not None:
                    if rho >= 1:
                        return INF
                    service += service * rho / (2 * (1 - rho))
            return service
        if not self.relax:
            return R(0)
        return min(R(wl.w[i]) / R(max(c.C for c in self._classes(p, t))) for t in tiers)

    def _edge_lat(self, p, k):
        R, wl = self.R, self.wl
        a, b = EDGES[k]
        determined = (len(self._tiers(p, a)) == 1 and len(self._tiers(p, b)) == 1
                      and "link" in p)
        if not determined and not self.relax:
            return R(0)
        best = INF
        for ta in self._tiers(p, a):
            for tb in self._tiers(p, b):
                if RANK[tb] < RANK[ta]:
                    continue
                for link in self._d(p, "link"):
                    v = R(0)
                    for kind in hop(ta, tb):
                        v += (8 * R(wl.s_in[k]) / R(link.B) + R(link.prop) if kind == "access"
                              else 8 * R(wl.s_in[k]) / R(WAN_B) + R(WAN_PROP))
                    best = min(best, v)
        return best

    def _edge_volume_energy(self, p, k):
        R, wl = self.R, self.wl
        a, b = EDGES[k]
        determined = (len(self._tiers(p, a)) == 1 and len(self._tiers(p, b)) == 1
                      and "link" in p)
        if not determined and not self.relax:
            return R(0), R(0)
        vol, en = INF, INF
        e_acc = R(min(l.e for l in self._d(p, "link")))
        for ta in self._tiers(p, a):
            for tb in self._tiers(p, b):
                if RANK[tb] < RANK[ta]:
                    continue
                kinds = hop(ta, tb)
                vol = min(vol, len(kinds) * R(wl.s_in[k]) * R(wl.Lambda))
                en = min(en, sum((e_acc if kd == "access" else R(WAN_E) for kd in kinds), R(0))
                         * R(wl.s_in[k]) * R(wl.Lambda) * R(wl.horizon))
        return vol, en

    def __call__(self, p: dict):
        self.calls += 1
        R, wl = self.R, self.wl
        st = [self._stage(p, i) for i in range(len(STAGES))]
        if any(v == INF for v in st):
            return (INF, INF, INF, INF)
        idx = {e: k for k, e in enumerate(EDGES)}
        el = [self._edge_lat(p, k) for k in range(len(EDGES))]
        pre = sum((el[idx[e]] for e in PREFIX), R(0)) + st[0] + st[1]
        L = pre + max(sum((el[idx[e]] + st[e[1]] for e in path), R(0)) for path in BRANCHES)

        T = R(wl.horizon)
        E = R(0)
        # idle energy: exact once count and class are assigned
        for tier, n, k in (("edge", "n_e", "k_e"), ("fog", "n_f", "k_f")):
            if (n in p and k in p) or self.relax:
                E += R(min(self._d(p, n))) * R(min(c.P_idle for c in self._d(p, k))) * T
        # dynamic energy: rho * (P_peak - P_idle) * N * T = Lambda w (P_peak-P_idle)/C * T
        for i in range(len(STAGES)):
            tiers = self._tiers(p, i)
            determined = len(tiers) == 1 and len(self._classes(p, tiers[0])) == 1
            if not determined and not self.relax:
                continue
            ratio = min((R(c.P_peak) if t == "cloud" else R(c.P_peak) - R(c.P_idle)) / R(c.C)
                        for t in tiers for c in self._classes(p, t))
            E += R(wl.Lambda) * R(wl.w[i]) * ratio * T
        D = R(0)
        for k in range(len(EDGES)):
            v, e = self._edge_volume_energy(p, k)
            D += v
            E += e
        # cost: exact once count, class and link are assigned
        C = R(0)
        for n, k in (("n_e", "k_e"), ("n_f", "k_f")):
            if (n in p and k in p and "link" in p) or self.relax:
                C += R(min(self._d(p, n))) * (R(min(c.cost for c in self._d(p, k)))
                                               + R(min(l.cost for l in self._d(p, "link"))))
            elif n in p and k in p:
                C += R(p[n]) * R(p[k].cost)
        if "k_c" in p or self.relax:
            C += R(min(c.cost for c in self._d(p, "k_c")))
        return (L, E, C, D)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------
#
# Two-stage pruning, as for template A: a binary64 bound proposes, and a prune is
# taken only if the same bound computed in rational arithmetic confirms it against
# the exact objective vectors of the archived designs.  Every pruning decision is
# therefore exact in the model; binary64 rounding can only cost a missed prune.

PROPOSE = 1e-9   # the binary64 proposal is lenient by this relative tolerance


def _infeasible(lb, wl, R):
    return lb[0] > R(wl.deadline) or lb[2] > R(wl.C_max) or lb[1] > R(wl.E_max)


def _propose_infeasible(lb, wl):
    near = lambda v, lim: v > lim * (1 - PROPOSE)
    return near(lb[0], wl.deadline) or near(lb[2], wl.C_max) or near(lb[1], wl.E_max)


def _dominated(lb, archive):
    """Some archived vector strictly dominates lb."""
    for a in archive:
        if all(a[i] <= lb[i] for i in range(4)) and any(a[i] < lb[i] for i in range(4)):
            return True
    return False


def _propose_dominated(lb, archive):
    """Some archived vector nearly dominates lb (a superset of the exact test)."""
    for a in archive:
        if all(a[i] <= lb[i] * (1 + PROPOSE) for i in range(4)):
            return True
    return False


def nondominated(vectors):
    vs = sorted(set(vectors))
    out = []
    for v in vs:
        if not any(all(u[i] <= v[i] for i in range(4)) and u != v for u in vs):
            out.append(v)
    return out


@dataclass
class Stats:
    evals: int = 0
    nodes: int = 0
    bound_calls: int = 0
    certifications: int = 0
    t_eval: float = 0.0
    front: tuple = ()


def exhaustive(scale: str, wl: Workload, exact=False) -> Stats:
    """Evaluate every well-formed design.  With ``exact=True`` feasibility and
    objectives are computed in rational arithmetic and the front is the exact one
    (the reference for correctness); otherwise binary64 (the reference for time)."""
    dom = domains(scale)
    s = Stats()
    feas = []
    for combo in itertools.product(*[dom[v] for v in ORDER]):
        x = dict(zip(ORDER, combo))
        if not well_formed(x):
            continue
        s.evals += 1
        t0 = time.perf_counter()
        f, ok = evaluate(x, wl, exact=exact)
        s.t_eval += time.perf_counter() - t0
        if ok:
            feas.append(f)
    s.nodes = s.evals
    s.front = tuple(nondominated(feas))
    return s


def search(scale: str, wl: Workload, relax=True, queue=True, order=ORDER) -> Stats:
    dom = domains(scale)
    fast = Bounds(scale, wl, relax=relax, queue=queue)
    sure = Bounds(scale, wl, relax=relax, queue=queue, exact=True)
    s = Stats()
    archive_f: List[tuple] = []   # binary64 objectives, for proposals
    archive_q: List[tuple] = []   # exact objectives, for certification
    feas: List[tuple] = []

    def rec(depth, p):
        s.nodes += 1
        if depth == len(order):
            s.evals += 1
            t0 = time.perf_counter()
            f, _ = evaluate(p, wl)
            s.t_eval += time.perf_counter() - t0
            # feasibility, the archive and the returned front use the exact values
            fq, ok = evaluate(p, wl, exact=True)
            if ok:
                feas.append(fq)
                archive_f.append(f)
                archive_q.append(fq)
            return
        var = order[depth]
        for val in dom[var]:
            q = dict(p)
            q[var] = val
            if not well_formed(q):
                continue
            lb = fast(q)
            if _propose_infeasible(lb, wl) or (archive_f and _propose_dominated(lb, archive_f)):
                s.certifications += 1
                lq = sure(q)
                if _infeasible(lq, wl, Fraction) or (archive_q and _dominated(lq, archive_q)):
                    continue
            rec(depth + 1, q)

    rec(0, {})
    s.bound_calls = fast.calls
    s.front = tuple(nondominated(feas))
    return s
