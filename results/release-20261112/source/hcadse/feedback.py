"""Soft-deadline retries: a load term that no compact solver encoding represents.

A request whose end-to-end latency exceeds a soft target is retried once by the
client, so retried requests re-enter the pipeline and raise the load that
produced them.  The effective arrival rate is therefore the solution of

    lam_eff = lam * (1 + q(lam_eff)),      q(lam) = exp(-tau / L(lam)),        (1)

where L(lam) is the mean end-to-end latency of the deployment at arrival rate
lam and tau = SOFT * deadline is the soft target.  The tail probability is the
exponential approximation P(L > tau) = exp(-tau / E[L]).

Two properties matter for the paper:

* The solution of (1) depends on every decision at once -- node counts, node
  classes, replication, placement and link class all enter L.  It is outside
  the two encodings implemented for the paper: neither their sum of tabulated
  small-support terms nor their polynomial QF_NRA formulation represents it.
  This is not a claim that every possible exact-solver formulation must fail.
* It still admits an admissible lower bound on partial designs.  G is monotone
  in lam and monotone in the model terms, so the least fixed point of the map
  built from term-wise optimistic values is below the least fixed point of
  every completion (Proposition 4 in the manuscript, proved by induction on the
  iterates and machine-checked exhaustively on S1).

Nothing here changes the model of the main results: this module is a separate
model variant used only by experiments/e15_feedback.
"""
from __future__ import annotations

import math
from typing import Dict, Tuple

from .evaluate import MB_TO_MB, Result, hops
from .model import POLICIES, WAN_B, WAN_E, WAN_PROP
from .numeric import deployment_cost_decimal, exceeds_decimal_limit

INF = float("inf")
SOFT = 0.5        # the soft target is SOFT * deadline
MAX_RETRY = 1.0   # at most one retry per request, so lam_eff <= 2 lam
ITERS = 1000
FP_RTOL = 1e-12
FP_ATOL = 1e-12


def _tiers(policy: str) -> Tuple[str, str, str]:
    t1, t3 = POLICIES[policy]
    return t1, "gw", t3


def _latency_at(x: dict, wl, lam: float):
    """Mean latency, utilisations and memory at arrival rate `lam`."""
    t1, t2, t3 = _tiers(x["policy"])
    per_node_C = {"edge": x["edge_cls"].C, "gw": x["gw_cls"].C, "cloud": x["cloud_cls"].C}
    cap = {"edge": x["n_e"] * per_node_C["edge"], "gw": x["n_g"] * per_node_C["gw"],
           "cloud": per_node_C["cloud"]}
    tiers = (t1, t2, t3)
    load = {"edge": 0.0, "gw": 0.0, "cloud": 0.0}
    mem = {"edge": 0.0, "gw": 0.0, "cloud": 0.0}
    for i, st in enumerate(wl.stages):
        mult = x["rep"] if i == 0 else 1
        load[tiers[i]] += lam * st.w * mult
        mem[tiers[i]] += st.mem * mult
    rho = {t: load[t] / cap[t] for t in load}
    L = 0.0
    for i, st in enumerate(wl.stages):
        t = tiers[i]
        s_time = st.w / per_node_C[t]
        L += s_time
        if rho[t] < 1.0:
            L += s_time * rho[t] / (2.0 * (1.0 - rho[t]))
        else:
            return INF, rho, mem
    lk = x["link_cls"]
    for payload, kind in hops(x, wl):
        if kind == "access":
            L += payload * MB_TO_MB / lk.B + lk.prop
        else:
            L += payload * MB_TO_MB / WAN_B + WAN_PROP
    return L, rho, mem


def fixed_point(L_of_lam, lam0: float, tau: float,
                rtol: float = FP_RTOL, atol: float = FP_ATOL):
    """Least fixed point of lam -> lam0 (1 + exp(-tau / L(lam))), from below.

    `L_of_lam` must be non-decreasing wherever finite.  The iterates start at
    lam0 and increase monotonically inside [lam0, (1 + MAX_RETRY) lam0]; the
    latency need only remain finite along this sequence and at its limit, not
    at every unused point of the enclosing interval.  Iteration stops
    when the fixed-point residual is at most ``atol + rtol * |lam|``.  Returns
    (lam_eff, L, iterations), with L recomputed at the returned rate, and
    (inf, inf, k) when an iterate reaches an unstable (infinite-latency) region.
    """
    lam = lam0
    for k in range(1, ITERS + 1):
        L = L_of_lam(lam)
        if not (L < INF):
            return INF, INF, k
        q = math.exp(-tau / L) if L > 0 else 1.0
        nxt = lam0 * (1.0 + MAX_RETRY * q)
        residual = abs(nxt - lam)
        if residual <= atol + rtol * max(abs(lam), abs(nxt)):
            # Use the upper of the two rounded iterates.  Exact arithmetic is
            # monotone from below; this choice avoids returning a numerically
            # optimistic rate when the final update rounds down by one ulp.
            root = max(lam, nxt)
            L_root = L_of_lam(root)
            if not (L_root < INF):
                return INF, INF, k
            return root, L_root, k
        lam = nxt
    raise RuntimeError("retry fixed point did not converge")


def evaluate(x: dict, wl) -> Result:
    """The evaluator of Section 3 with the retry fixed point (1) in the loop."""
    tau = SOFT * wl.deadline
    lam_eff, L, _ = fixed_point(lambda l: _latency_at(x, wl, l)[0], wl.Lambda, tau)
    if not (L < INF):
        _, rho, mem = _latency_at(x, wl, wl.Lambda)
        return Result((INF, INF, INF, INF), False, rho, ("deadline",))
    _, rho, mem = _latency_at(x, wl, lam_eff)

    viol = []
    for t in ("edge", "gw", "cloud"):
        if rho[t] > wl.rho_max:
            viol.append("rho_" + t)
    if mem["edge"] > x["edge_cls"].M:
        viol.append("mem_edge")
    if mem["gw"] > x["gw_cls"].M:
        viol.append("mem_gw")
    if L > wl.deadline:
        viol.append("deadline")

    lk = x["link_cls"]
    t1 = _tiers(x["policy"])[0]
    access_MB = sum(p for p, k in hops(x, wl) if k == "access")
    if access_MB * lam_eff * MB_TO_MB > (x["n_e"] if t1 == "edge" else x["n_g"]) * lk.B:
        viol.append("bandwidth")

    T = wl.horizon
    E = x["n_e"] * (x["edge_cls"].P_idle + rho["edge"] *
                    (x["edge_cls"].P_peak - x["edge_cls"].P_idle)) * T
    E += x["n_g"] * (x["gw_cls"].P_idle + rho["gw"] *
                     (x["gw_cls"].P_peak - x["gw_cls"].P_idle)) * T
    E += rho["cloud"] * x["cloud_cls"].P_peak * T
    net_MB = 0.0
    for payload, kind in hops(x, wl):
        e = lk.e if kind == "access" else WAN_E
        E += payload * lam_eff * e * T
        net_MB += payload
    if E > wl.E_max:
        viol.append("energy")

    C_exact = deployment_cost_decimal(
        x["n_e"], x["edge_cls"].cost, x["n_g"], x["gw_cls"].cost,
        lk.cost, x["cloud_cls"].cost)
    C = float(C_exact)
    if exceeds_decimal_limit(C_exact, wl.C_max):
        viol.append("cost")

    D = net_MB * lam_eff
    return Result((L, E, C, D), not viol, rho, tuple(viol))


# ---------------------------------------------------------------------------
# admissible bounds for the retry model (Proposition 4)
# ---------------------------------------------------------------------------

def _dom(space, partial, var):
    return [partial[var]] if var in partial else space.domain(var)


def _queue_bound_at(partial, wl, lam: float) -> float:
    """Exact queueing delay at rate `lam` of every tier whose load and capacity
    the assigned variables already determine; 0 (optimistic) for the others."""
    if "policy" not in partial or "rep" not in partial:
        return 0.0
    t1, t3 = POLICIES[partial["policy"]]
    tiers = (t1, "gw", t3)
    rep = partial["rep"]
    total = 0.0
    for tier, need in (("edge", ("n_e", "edge_cls")), ("gw", ("n_g", "gw_cls")),
                       ("cloud", ("cloud_cls",))):
        if any(k not in partial for k in need):
            continue
        idx = [i for i, t in enumerate(tiers) if t == tier]
        if not idx:
            continue
        cls = partial[need[-1]]
        n = partial[need[0]] if len(need) == 2 else 1
        load = sum(lam * wl.stages[i].w * (rep if i == 0 else 1) for i in idx)
        rho = load / (n * cls.C)
        if rho >= 1.0:
            return INF
        for i in idx:
            total += (wl.stages[i].w / cls.C) * rho / (2.0 * (1.0 - rho))
    return total


def lower_bounds(partial: dict, space, wl) -> Dict[str, float]:
    """Term-wise optimistic bounds under the retry model.

    Each term is replaced by its minimum over the still-reachable domains, as in
    Section 4.2, which gives a latency function L_lb(lam) <= L_x(lam) that is
    non-decreasing in lam for every completion x of `partial`.  The least fixed
    point of the map built from L_lb is then at or below the least fixed point of
    every completion, and every load-dependent term is evaluated at it.
    """
    from .bounds import _comm_latency_lb, _net_MB_lb
    st = wl.stages
    tau = SOFT * wl.deadline
    edge_d = _dom(space, partial, "edge_cls"); gw_d = _dom(space, partial, "gw_cls")
    cl_d = _dom(space, partial, "cloud_cls"); lk_d = _dom(space, partial, "link_cls")
    ne_d = _dom(space, partial, "n_e"); ng_d = _dom(space, partial, "n_g")
    rep_d = _dom(space, partial, "rep"); pol_d = _dom(space, partial, "policy")

    tier_C = {"edge": max(c.C for c in edge_d), "gw": max(c.C for c in gw_d),
              "cloud": max(c.C for c in cl_d)}
    B_max = max(l.B for l in lk_d); prop_min = min(l.prop for l in lk_d)
    e_min = min(l.e for l in lk_d)

    proc = 0.0
    for i, s in enumerate(st):
        opts = set()
        for p in pol_d:
            t1, t3 = POLICIES[p]
            opts.add(t1 if i == 0 else ("gw" if i == 1 else t3))
        proc += min(s.w / tier_C[t] for t in opts)
    comm = min(_comm_latency_lb(p, rep_d, wl, B_max, prop_min) for p in pol_d)

    def L_lb(lam):
        q = _queue_bound_at(partial, wl, lam)
        return INF if not (q < INF) else proc + q + comm

    lam_eff, L, _ = fixed_point(L_lb, wl.Lambda, tau)
    if not (L < INF):
        return {"L": INF, "E": INF, "C": INF, "D": INF}

    T = wl.horizon
    E = min(ne_d) * min(c.P_idle for c in edge_d) * T
    E += min(ng_d) * min(c.P_idle for c in gw_d) * T
    dyn = {"edge": min((c.P_peak - c.P_idle) / c.C for c in edge_d),
           "gw": min((c.P_peak - c.P_idle) / c.C for c in gw_d),
           "cloud": min(c.P_peak / c.C for c in cl_d)}
    for i, s in enumerate(st):
        opts = set()
        for p in pol_d:
            t1, t3 = POLICIES[p]
            opts.add(t1 if i == 0 else ("gw" if i == 1 else t3))
        mult = min(rep_d) if i == 0 else 1
        E += lam_eff * s.w * mult * min(dyn[t] for t in opts) * T
    net_lb = min(_net_MB_lb(p, rep_d, wl) for p in pol_d)
    E += net_lb * lam_eff * min(e_min, WAN_E) * T

    C_exact = deployment_cost_decimal(
        min(ne_d), min(c.cost for c in edge_d), min(ng_d),
        min(c.cost for c in gw_d), min(l.cost for l in lk_d),
        min(c.cost for c in cl_d))
    C = float(C_exact)

    return {"L": L, "E": E, "C": C, "C_exact": C_exact, "D": net_lb * lam_eff}


# Preserve the pre-interval implementation for audit diagnostics.
legacy_lower_bounds = lower_bounds


def lower_bounds(partial: dict, space, wl) -> Dict[str, float]:
    """Interval-safe lower bounds for the retry model."""
    from .intervals import certified_feedback_lower_bounds, lower_float
    certified = certified_feedback_lower_bounds(partial, space, wl, soft=str(SOFT),
                                                iterations=ITERS)
    return {"L": lower_float(certified["L"].lo),
            "E": lower_float(certified["E"].lo),
            "C": lower_float(certified["C"].lo),
            "C_exact": certified["C"].lo,
            "D": lower_float(certified["D"].lo),
            "_intervals": certified}


def certified_objectives(design, workload):
    from .intervals import conservative_feedback_objectives
    return conservative_feedback_objectives(design, workload)
