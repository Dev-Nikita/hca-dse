"""High-fidelity (analytical) evaluation of a complete architecture (Stage 4)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple
from .model import Workload, POLICIES, WAN_B, WAN_PROP, WAN_E
from .numeric import deployment_cost_decimal, exceeds_decimal_limit

INF = float("inf")
MB_TO_MB = 8.0  # MB -> Mb


@dataclass
class Result:
    objectives: Tuple[float, float, float, float]  # latency, energy, cost, net volume
    feasible: bool
    rho: Dict[str, float]
    violations: Tuple[str, ...]


def _tiers(policy: str) -> Tuple[str, str, str]:
    t1, t3 = POLICIES[policy]
    return t1, "gw", t3


def hops(x: dict, wl: Workload) -> List[Tuple[float, str]]:
    """Communication hops as (payload MB per request, link kind)."""
    t1, _, t3 = _tiers(x["policy"])
    s = [st.s_in for st in wl.stages]
    h: List[Tuple[float, str]] = [(s[0], "access")]          # device -> stage-1 tier
    if t1 == "edge":
        h.append((s[1], "access"))                            # edge -> gateway
        if x["rep"] > 1:
            h.append(((x["rep"] - 1) * wl.s_sync, "access"))  # replica synchronisation
    if t3 == "cloud":
        h.append((s[2], "wan"))
    else:
        h.append((s[2], "access"))                            # gateway -> edge analytics
    return h


def evaluate(x: dict, wl: Workload) -> Result:
    """Full evaluation: the 'expensive' design-point evaluation of the pipeline."""
    t1, t2, t3 = _tiers(x["policy"])
    Ce, Cg, Cc = x["edge_cls"].C, x["gw_cls"].C, x["cloud_cls"].C
    cap = {"edge": x["n_e"] * Ce, "gw": x["n_g"] * Cg, "cloud": Cc}
    per_node_C = {"edge": Ce, "gw": Cg, "cloud": Cc}
    load = {"edge": 0.0, "gw": 0.0, "cloud": 0.0}
    mem = {"edge": 0.0, "gw": 0.0, "cloud": 0.0}
    lam = wl.Lambda
    tiers = (t1, t2, t3)
    for i, st in enumerate(wl.stages):
        mult = x["rep"] if i == 0 else 1
        load[tiers[i]] += lam * st.w * mult
        mem[tiers[i]] += st.mem * mult
    rho = {t: load[t] / cap[t] for t in load}

    viol: List[str] = []
    for t in ("edge", "gw", "cloud"):
        if rho[t] > wl.rho_max:
            viol.append(f"rho_{t}")
    if mem["edge"] > x["edge_cls"].M:
        viol.append("mem_edge")
    if mem["gw"] > x["gw_cls"].M:
        viol.append("mem_gw")

    # ---- latency -----------------------------------------------------------
    L = 0.0
    for i, st in enumerate(wl.stages):
        t = tiers[i]
        s_time = st.w / per_node_C[t]
        L += s_time
        if rho[t] < 1.0:
            # Pollaczek-Khinchine with deterministic service (M/D/1):
            # W = s * rho / (2 (1 - rho)). Stage execution times are
            # deterministic, so M/M/1 would overestimate waiting by 2x.
            L += s_time * rho[t] / (2.0 * (1.0 - rho[t]))
        else:
            L = INF
    lk = x["link_cls"]
    net_MB = 0.0
    for payload, kind in hops(x, wl):
        if kind == "access":
            L += payload * MB_TO_MB / lk.B + lk.prop
        else:
            L += payload * MB_TO_MB / WAN_B + WAN_PROP
        net_MB += payload
    if L > wl.deadline:
        viol.append("deadline")

    # ---- bandwidth ---------------------------------------------------------
    access_Mb = sum(p for p, k in hops(x, wl) if k == "access") * lam * MB_TO_MB
    n_access = x["n_e"] if t1 == "edge" else x["n_g"]
    if access_Mb > n_access * lk.B:
        viol.append("bandwidth")

    # ---- energy ------------------------------------------------------------
    T = wl.horizon
    E = x["n_e"] * (x["edge_cls"].P_idle + rho["edge"] *
                    (x["edge_cls"].P_peak - x["edge_cls"].P_idle)) * T
    E += x["n_g"] * (x["gw_cls"].P_idle + rho["gw"] *
                     (x["gw_cls"].P_peak - x["gw_cls"].P_idle)) * T
    E += rho["cloud"] * x["cloud_cls"].P_peak * T
    for payload, kind in hops(x, wl):
        e = lk.e if kind == "access" else WAN_E
        E += payload * lam * e * T
    if E > wl.E_max:
        viol.append("energy")

    # ---- cost --------------------------------------------------------------
    C_exact = deployment_cost_decimal(
        x["n_e"], x["edge_cls"].cost, x["n_g"], x["gw_cls"].cost,
        lk.cost, x["cloud_cls"].cost)
    C = float(C_exact)
    if exceeds_decimal_limit(C_exact, wl.C_max):
        viol.append("cost")

    D = net_MB * lam  # MB/s

    return Result((L, E, C, D), not viol, rho, tuple(viol))
