"""Directed Decimal intervals for numerically sound analytical pruning.

Inputs are the decimal quantities declared by the model.  Every arithmetic operation is
performed twice with outward rounding.  This is an implementation-level enclosure, not
a formal verification of Python's Decimal library.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext

from .model import POLICIES, WAN_B, WAN_E, WAN_PROP

PRECISION = 60
DINF = Decimal("Infinity")


def dec(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _op(rounding, operation):
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = rounding
        return operation()


@dataclass(frozen=True)
class Interval:
    lo: Decimal
    hi: Decimal

    @classmethod
    def point(cls, value):
        value = dec(value)
        return cls(value, value)

    def __add__(self, other):
        other = as_interval(other)
        return Interval(_op(ROUND_FLOOR, lambda: self.lo + other.lo),
                        _op(ROUND_CEILING, lambda: self.hi + other.hi))

    __radd__ = __add__

    def __sub__(self, other):
        other = as_interval(other)
        return Interval(_op(ROUND_FLOOR, lambda: self.lo - other.hi),
                        _op(ROUND_CEILING, lambda: self.hi - other.lo))

    def __mul__(self, other):
        other = as_interval(other)
        products_lo = [_op(ROUND_FLOOR, lambda a=a, b=b: a*b)
                       for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        products_hi = [_op(ROUND_CEILING, lambda a=a, b=b: a*b)
                       for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return Interval(min(products_lo), max(products_hi))

    __rmul__ = __mul__

    def __truediv__(self, other):
        other = as_interval(other)
        if other.lo <= 0 <= other.hi:
            return Interval(-DINF, DINF)
        quotients_lo = [_op(ROUND_FLOOR, lambda a=a, b=b: a/b)
                        for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        quotients_hi = [_op(ROUND_CEILING, lambda a=a, b=b: a/b)
                        for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return Interval(min(quotients_lo), max(quotients_hi))

    def __neg__(self):
        return Interval(-self.hi, -self.lo)

    def exp(self):
        return Interval(_op(ROUND_FLOOR, lambda: self.lo.exp()),
                        _op(ROUND_CEILING, lambda: self.hi.exp()))


def as_interval(value):
    return value if isinstance(value, Interval) else Interval.point(value)


def imin(values):
    values = list(values)
    return Interval(min(v.lo for v in values), min(v.hi for v in values))


def lower_float(value):
    if value == DINF:
        return float("inf")
    if value == -DINF:
        return -float("inf")
    result = float(value)
    if Decimal.from_float(result) > value:
        result = math.nextafter(result, -math.inf)
    return result


def _dom(space, partial, variable):
    return [partial[variable]] if variable in partial else space.domain(variable)


def _net(policy, replication, workload):
    t1, _ = POLICIES[policy]
    sizes = [Interval.point(stage.s_in) for stage in workload.stages]
    value = sizes[0] + sizes[2]
    if t1 == "edge":
        value += sizes[1] + Interval.point(replication-1) * workload.s_sync
    return value


def _communication(policy, replication, workload, bandwidth, propagation):
    t1, t3 = POLICIES[policy]
    sizes = [Interval.point(stage.s_in) for stage in workload.stages]
    value = sizes[0] * 8 / bandwidth + propagation
    if t1 == "edge":
        value += sizes[1] * 8 / bandwidth + propagation
        if replication > 1:
            value += Interval.point(replication-1) * workload.s_sync * 8 / bandwidth + propagation
    if t3 == "cloud":
        value += sizes[2] * 8 / WAN_B + WAN_PROP
    else:
        value += sizes[2] * 8 / bandwidth + propagation
    return value


def _queue_lower(partial, workload):
    if "policy" not in partial or "rep" not in partial:
        return Interval.point(0)
    t1, t3 = POLICIES[partial["policy"]]
    tiers = (t1, "gw", t3)
    arrival = Interval.point(workload.n_dev) * workload.rate
    total = Interval.point(0)
    for tier, requirements in (("edge", ("n_e", "edge_cls")),
                               ("gw", ("n_g", "gw_cls")),
                               ("cloud", ("cloud_cls",))):
        if any(name not in partial for name in requirements):
            continue
        indices = [i for i, assigned in enumerate(tiers) if assigned == tier]
        if not indices:
            continue
        cls = partial[requirements[-1]]
        count = partial[requirements[0]] if len(requirements) == 2 else 1
        load = Interval.point(0)
        for index in indices:
            multiplier = partial["rep"] if index == 0 else 1
            load += arrival * workload.stages[index].w * multiplier
        rho = load / (Interval.point(count) * cls.C)
        if rho.hi >= 1:
            return Interval(DINF, DINF)
        for index in indices:
            service = Interval.point(workload.stages[index].w) / cls.C
            total += service * rho / (Interval.point(2) * (Interval.point(1)-rho))
    return total


def _queue_lower_at(partial, workload, arrival):
    if "policy" not in partial or "rep" not in partial:
        return Interval.point(0)
    t1, t3 = POLICIES[partial["policy"]]
    tiers = (t1, "gw", t3)
    total = Interval.point(0)
    for tier, requirements in (("edge", ("n_e", "edge_cls")),
                               ("gw", ("n_g", "gw_cls")),
                               ("cloud", ("cloud_cls",))):
        if any(name not in partial for name in requirements):
            continue
        indices = [i for i, assigned in enumerate(tiers) if assigned == tier]
        if not indices:
            continue
        cls = partial[requirements[-1]]
        count = partial[requirements[0]] if len(requirements) == 2 else 1
        load = Interval.point(0)
        for index in indices:
            multiplier = partial["rep"] if index == 0 else 1
            load += Interval.point(arrival)*workload.stages[index].w*multiplier
        rho = load/(Interval.point(count)*cls.C)
        if rho.lo >= 1:
            return Interval(DINF, DINF)
        if rho.hi >= 1:
            return Interval(total.lo, DINF)
        for index in indices:
            service = Interval.point(workload.stages[index].w)/cls.C
            total += service*rho/(Interval.point(2)*(Interval.point(1)-rho))
    return total


def certified_lower_bounds(partial, space, workload):
    stages = workload.stages
    arrival = Interval.point(workload.n_dev) * workload.rate
    edge = _dom(space, partial, "edge_cls")
    gateway = _dom(space, partial, "gw_cls")
    cloud = _dom(space, partial, "cloud_cls")
    links = _dom(space, partial, "link_cls")
    ne = _dom(space, partial, "n_e")
    ng = _dom(space, partial, "n_g")
    rep = _dom(space, partial, "rep")
    policies = _dom(space, partial, "policy")
    capacities = {"edge": max(c.C for c in edge), "gw": max(c.C for c in gateway),
                  "cloud": max(c.C for c in cloud)}
    latency = Interval.point(0)
    for index, stage in enumerate(stages):
        options = set()
        for policy in policies:
            t1, t3 = POLICIES[policy]
            options.add(t1 if index == 0 else ("gw" if index == 1 else t3))
        latency += imin(Interval.point(stage.w) / capacities[tier] for tier in options)
    latency += _queue_lower(partial, workload)
    bandwidth = max(link.B for link in links)
    propagation = min(link.prop for link in links)
    latency += imin(_communication(policy, min(rep), workload, bandwidth, propagation)
                    for policy in policies)

    horizon = Interval.point(workload.horizon)
    energy = Interval.point(min(ne)) * min(c.P_idle for c in edge) * horizon
    energy += Interval.point(min(ng)) * min(c.P_idle for c in gateway) * horizon
    dynamic = {
        "edge": imin((Interval.point(c.P_peak)-c.P_idle)/c.C for c in edge),
        "gw": imin((Interval.point(c.P_peak)-c.P_idle)/c.C for c in gateway),
        "cloud": imin(Interval.point(c.P_peak)/c.C for c in cloud),
    }
    for index, stage in enumerate(stages):
        options = set()
        for policy in policies:
            t1, t3 = POLICIES[policy]
            options.add(t1 if index == 0 else ("gw" if index == 1 else t3))
        multiplier = min(rep) if index == 0 else 1
        energy += arrival * stage.w * multiplier * imin(dynamic[t] for t in options) * horizon
    network = imin(_net(policy, min(rep), workload) for policy in policies)
    energy += network * arrival * min(min(link.e for link in links), WAN_E) * horizon

    from .numeric import deployment_cost_decimal
    cost = deployment_cost_decimal(min(ne), min(c.cost for c in edge), min(ng),
                                   min(c.cost for c in gateway),
                                   min(link.cost for link in links),
                                   min(c.cost for c in cloud))
    volume = network * arrival
    return {"L": latency, "E": energy, "C": Interval.point(cost), "D": volume}


def certified_objectives(design, workload):
    t1, t3 = POLICIES[design["policy"]]
    tiers = (t1, "gw", t3)
    classes = {"edge": design["edge_cls"], "gw": design["gw_cls"],
               "cloud": design["cloud_cls"]}
    counts = {"edge": design["n_e"], "gw": design["n_g"], "cloud": 1}
    arrival = Interval.point(workload.n_dev) * workload.rate
    load = {tier: Interval.point(0) for tier in classes}
    for index, stage in enumerate(workload.stages):
        multiplier = design["rep"] if index == 0 else 1
        load[tiers[index]] += arrival * stage.w * multiplier
    rho = {tier: load[tier]/(Interval.point(counts[tier])*classes[tier].C)
           for tier in classes}
    latency = Interval.point(0)
    for index, stage in enumerate(workload.stages):
        tier = tiers[index]
        service = Interval.point(stage.w)/classes[tier].C
        if rho[tier].hi >= 1:
            latency = Interval(DINF, DINF)
            break
        latency += service + service*rho[tier]/(Interval.point(2)*(Interval.point(1)-rho[tier]))
    link = design["link_cls"]
    latency += _communication(design["policy"], design["rep"], workload, link.B, link.prop)
    horizon = Interval.point(workload.horizon)
    energy = Interval.point(design["n_e"]) * (
        classes["edge"].P_idle + rho["edge"]*(classes["edge"].P_peak-classes["edge"].P_idle)) * horizon
    energy += Interval.point(design["n_g"]) * (
        classes["gw"].P_idle + rho["gw"]*(classes["gw"].P_peak-classes["gw"].P_idle)) * horizon
    energy += rho["cloud"]*classes["cloud"].P_peak*horizon
    for payload, kind in _hops(design, workload):
        energy += Interval.point(payload)*arrival*(link.e if kind == "access" else WAN_E)*horizon
    from .numeric import deployment_cost_decimal
    cost = deployment_cost_decimal(design["n_e"], classes["edge"].cost,
                                   design["n_g"], classes["gw"].cost,
                                   link.cost, classes["cloud"].cost)
    network = sum((Interval.point(payload) for payload, _ in _hops(design, workload)),
                  Interval.point(0))*arrival
    return (latency, energy, Interval.point(cost), network)


def certified_feedback_lower_bounds(partial, space, workload, soft="0.5", iterations=1000):
    """Safe retry-model lower endpoints from finite monotone iteration below the root."""
    stages = workload.stages
    edge = _dom(space, partial, "edge_cls"); gateway = _dom(space, partial, "gw_cls")
    cloud = _dom(space, partial, "cloud_cls"); links = _dom(space, partial, "link_cls")
    ne = _dom(space, partial, "n_e"); ng = _dom(space, partial, "n_g")
    rep = _dom(space, partial, "rep"); policies = _dom(space, partial, "policy")
    capacities = {"edge": max(c.C for c in edge), "gw": max(c.C for c in gateway),
                  "cloud": max(c.C for c in cloud)}
    processing = Interval.point(0)
    for index, stage in enumerate(stages):
        options = set()
        for policy in policies:
            t1, t3 = POLICIES[policy]
            options.add(t1 if index == 0 else ("gw" if index == 1 else t3))
        processing += imin(Interval.point(stage.w)/capacities[tier] for tier in options)
    bandwidth = max(link.B for link in links)
    propagation = min(link.prop for link in links)
    communication = imin(_communication(policy, min(rep), workload, bandwidth, propagation)
                         for policy in policies)
    base_arrival = dec(workload.n_dev)*dec(workload.rate)
    tau = dec(soft)*dec(workload.deadline)
    arrival_lower = base_arrival
    latency = None
    for _ in range(iterations):
        queue = _queue_lower_at(partial, workload, arrival_lower)
        if queue.lo == DINF:
            infinite = Interval(DINF, DINF)
            return {name: infinite for name in ("L", "E", "C", "D")}
        latency = processing+queue+communication
        if latency.lo <= 0:
            retry_lower = Decimal(1)
        else:
            retry_lower = (-(Interval.point(tau)/latency)).exp().lo
        following = _op(ROUND_FLOOR, lambda: base_arrival*(Decimal(1)+retry_lower))
        if following <= arrival_lower:
            break
        arrival_lower = following
    queue = _queue_lower_at(partial, workload, arrival_lower)
    latency = processing+queue+communication
    horizon = Interval.point(workload.horizon)
    arrival = Interval.point(arrival_lower)
    energy = Interval.point(min(ne))*min(c.P_idle for c in edge)*horizon
    energy += Interval.point(min(ng))*min(c.P_idle for c in gateway)*horizon
    dynamic = {
        "edge": imin((Interval.point(c.P_peak)-c.P_idle)/c.C for c in edge),
        "gw": imin((Interval.point(c.P_peak)-c.P_idle)/c.C for c in gateway),
        "cloud": imin(Interval.point(c.P_peak)/c.C for c in cloud)}
    for index, stage in enumerate(stages):
        options = set()
        for policy in policies:
            t1, t3 = POLICIES[policy]
            options.add(t1 if index == 0 else ("gw" if index == 1 else t3))
        multiplier = min(rep) if index == 0 else 1
        energy += arrival*stage.w*multiplier*imin(dynamic[t] for t in options)*horizon
    network = imin(_net(policy, min(rep), workload) for policy in policies)
    energy += network*arrival*min(min(link.e for link in links), WAN_E)*horizon
    from .numeric import deployment_cost_decimal
    cost = deployment_cost_decimal(min(ne), min(c.cost for c in edge), min(ng),
                                   min(c.cost for c in gateway),
                                   min(link.cost for link in links),
                                   min(c.cost for c in cloud))
    return {"L": latency, "E": energy, "C": Interval.point(cost), "D": network*arrival}


def conservative_feedback_objectives(design, workload):
    """Certified retry objectives, or conservative infinities when no bracket is found."""
    bracket = certified_feedback_upper_bracket(design, workload)
    cost = certified_objectives(design, workload)[2]
    if bracket is None:
        unknown = Interval(Decimal(0), DINF)
        return (unknown, unknown, cost, unknown)
    _, upper, latency, rho = bracket
    classes = {"edge": design["edge_cls"], "gw": design["gw_cls"],
               "cloud": design["cloud_cls"]}
    horizon = Interval.point(workload.horizon)
    energy = Interval.point(design["n_e"])*(
        classes["edge"].P_idle+rho["edge"]*(classes["edge"].P_peak-classes["edge"].P_idle))*horizon
    energy += Interval.point(design["n_g"])*(
        classes["gw"].P_idle+rho["gw"]*(classes["gw"].P_peak-classes["gw"].P_idle))*horizon
    energy += rho["cloud"]*classes["cloud"].P_peak*horizon
    link = design["link_cls"]
    for payload, kind in _hops(design, workload):
        energy += Interval.point(payload)*Interval.point(upper)*(
            link.e if kind == "access" else WAN_E)*horizon
    network = sum((Interval.point(payload) for payload, _ in _hops(design, workload)),
                  Interval.point(0))*Interval.point(upper)
    return (Interval(Decimal(0), latency.hi), Interval(Decimal(0), energy.hi),
            cost, Interval(Decimal(0), network.hi))


def _feedback_full_at(design, workload, arrival):
    t1, t3 = POLICIES[design["policy"]]
    tiers = (t1, "gw", t3)
    classes = {"edge": design["edge_cls"], "gw": design["gw_cls"],
               "cloud": design["cloud_cls"]}
    counts = {"edge": design["n_e"], "gw": design["n_g"], "cloud": 1}
    load = {tier: Interval.point(0) for tier in classes}
    for index, stage in enumerate(workload.stages):
        multiplier = design["rep"] if index == 0 else 1
        load[tiers[index]] += Interval.point(arrival)*stage.w*multiplier
    rho = {tier: load[tier]/(Interval.point(counts[tier])*classes[tier].C)
           for tier in classes}
    if any(value.hi >= 1 for value in rho.values()):
        return None, rho
    latency = Interval.point(0)
    for index, stage in enumerate(workload.stages):
        tier = tiers[index]
        service = Interval.point(stage.w)/classes[tier].C
        latency += service+service*rho[tier]/(Interval.point(2)*(Interval.point(1)-rho[tier]))
    link = design["link_cls"]
    latency += _communication(design["policy"], design["rep"], workload, link.B, link.prop)
    return latency, rho


def certified_feedback_upper_bracket(design, workload, soft="0.5", iterations=1000):
    """Return ``(lower, upper, L(upper), rho(upper))`` with certified ``g(U)<=U``."""
    base_arrival = dec(workload.n_dev)*dec(workload.rate)
    tau = dec(soft)*dec(workload.deadline)
    lower = base_arrival
    for _ in range(iterations):
        latency, _ = _feedback_full_at(design, workload, lower)
        if latency is None:
            return None
        retry_lower = (-(Interval.point(tau)/latency)).exp().lo
        following = _op(ROUND_FLOOR, lambda: base_arrival*(Decimal(1)+retry_lower))
        if following <= lower:
            break
        lower = following
    scale = max(abs(lower), Decimal(1))
    delta = scale*Decimal("1e-50")
    ceiling = base_arrival*Decimal(2)
    for _ in range(52):
        candidate = lower+delta
        if candidate > ceiling:
            candidate = ceiling
        latency, rho = _feedback_full_at(design, workload, candidate)
        if latency is not None:
            retry = (-(Interval.point(tau)/latency)).exp()
            mapped = Interval.point(base_arrival)*(Interval.point(1)+retry)
            if mapped.hi <= candidate:
                return lower, candidate, latency, rho
        if candidate == ceiling:
            break
        delta *= 10
    return None


def _hops(design, workload):
    t1, t3 = POLICIES[design["policy"]]
    sizes = [stage.s_in for stage in workload.stages]
    hops = [(sizes[0], "access")]
    if t1 == "edge":
        hops.append((sizes[1], "access"))
        if design["rep"] > 1:
            hops.append(((design["rep"]-1)*workload.s_sync, "access"))
    hops.append((sizes[2], "wan" if t3 == "cloud" else "access"))
    return hops
