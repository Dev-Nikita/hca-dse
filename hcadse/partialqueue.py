"""A positive waiting bound for tiers whose determinants are not yet assigned.

Section 4.2 bounds the waiting contribution of an undetermined tier by zero,
which is admissible but weak: nothing positive enters the prefix bound until a
tier's node count, node class, replication and placement are all fixed.  The
construction here replaces that zero by a positive quantity.

For a tier t and a stage i placed on t, the waiting contribution is

    w_i(x) = s_i(x) * rho_t(x) / (2 (1 - rho_t(x))),

which is non-decreasing in s_i and in rho_t on [0,1).  Over the completions of a
partial design p, and for a fixed placement policy pi,

    s_i(x) >= w_i / C_t^max(p),      rho_t(x) >= load_t^min(p, pi) / cap_t^max(p),

because the load of a tier is non-decreasing in the replication factor and its
capacity is non-decreasing in node count and node class.  Substituting the two
lower bounds therefore gives a lower bound on w_i(x).  Summing over the stages
that pi places on the undetermined tiers and minimising over the placement
policies still reachable from p gives a lower bound on the waiting contribution
that Section 4.2 omits -- every completion has some reachable policy, so the
minimum is attained or exceeded.  Tiers that are already determined keep their
exact term from `intervals._queue_lower` and are skipped here, so the two
contributions never double count.

All arithmetic runs in the directed-rounding interval type of hcadse.intervals,
so the returned lower end is certified against binary64 and decimal rounding.
"""
from __future__ import annotations

from .intervals import DINF, Interval
from .model import POLICIES

TIER_REQUIREMENTS = (("edge", ("n_e", "edge_cls")),
                     ("gw", ("n_g", "gw_cls")),
                     ("cloud", ("cloud_cls",)))


def _dom(space, partial, variable):
    return [partial[variable]] if variable in partial else space.domain(variable)


def _determined(partial, requirements):
    return all(name in partial for name in requirements)


def positive_queue_lower(partial, space, workload) -> Interval:
    """Certified lower bound on the waiting contribution of the tiers that
    `intervals._queue_lower` leaves at zero for this partial design."""
    policy_known = "policy" in partial and "rep" in partial
    policies = _dom(space, partial, "policy")
    arrival = Interval.point(workload.n_dev) * workload.rate
    rep_min = min(_dom(space, partial, "rep"))

    best = None
    for policy in policies:
        t1, t3 = POLICIES[policy]
        tiers = (t1, "gw", t3)
        total = Interval.point(0)
        saturated = False
        for tier, requirements in TIER_REQUIREMENTS:
            # a determined tier already contributes its exact term
            if policy_known and _determined(partial, requirements):
                continue
            indices = [i for i, assigned in enumerate(tiers) if assigned == tier]
            if not indices:
                continue
            capacity_hi = (Interval.point(max(c.C for c in _dom(space, partial,
                                                                requirements[-1])))
                           * (max(_dom(space, partial, requirements[0]))
                              if len(requirements) == 2 else 1))
            service_capacity = Interval.point(max(c.C for c in _dom(space, partial,
                                                                    requirements[-1])))
            load_lo = Interval.point(0)
            for index in indices:
                multiplier = rep_min if index == 0 else 1
                load_lo += arrival * workload.stages[index].w * multiplier
            load_lo = Interval(load_lo.lo, load_lo.lo)
            rho_lo = load_lo / Interval(capacity_hi.hi, capacity_hi.hi)
            if rho_lo.lo >= 1:
                # every completion with this policy saturates the tier
                saturated = True
                break
            rho_lo = Interval(rho_lo.lo, rho_lo.lo)
            for index in indices:
                service = Interval.point(workload.stages[index].w) / service_capacity
                service = Interval(service.lo, service.lo)
                total += (service * rho_lo
                          / (Interval.point(2) * (Interval.point(1) - rho_lo)))
        candidate = Interval(DINF, DINF) if saturated else Interval(total.lo, total.lo)
        best = candidate if best is None else Interval(min(best.lo, candidate.lo),
                                                       min(best.hi, candidate.hi))
    return best if best is not None else Interval.point(0)
