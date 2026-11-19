"""E12 (factorised linear encoding): compact exact symbolic baseline in QF_LRA.

Every decision is a one-hot group of Booleans. Each quantity of the model is a sum of
terms, and each term depends on a small subset of the decisions (its support). A term is
encoded as a table over its support only -- for example the edge utilisation depends on
node count, node class, replication factor and placement policy, not on link, gateway or
cloud choices -- so the encoding grows with the product of each term's support domains
rather than with the size of the design space. All table entries are exact rationals
computed from the model's closed-form terms; no design point is enumerated and the
full-design evaluator is never called while solving. Objectives and constraints become
linear in the Booleans, and the exact Pareto set is enumerated with the guided-improvement
algorithm (see the docstring of e12_symbolic_polynomial.py).

Designs returned by the solver are re-evaluated with the ordinary evaluator only to
compare their binary64 objective vectors with the exhaustive front; those verification
calls are reported separately.
"""
import sys, os, csv, time, itertools
from fractions import Fraction as Fr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import z3
from hcadse.model import make_space, WORKLOADS, POLICIES, WAN_B, WAN_PROP, WAN_E
from hcadse.evaluate import evaluate, MB_TO_MB
from hcadse.search import exhaustive
from hcadse.metrics import objset

def F(value):
    """Exact rational interpretation of source-facing decimal model constants."""
    return value if isinstance(value, Fr) else Fr(str(value))
R = lambda q: z3.RealVal(f"{q.numerator}/{q.denominator}")


class Choice:
    def __init__(self, s, name, values):
        self.values = values
        self.b = [z3.Bool(f'{name}_{j}') for j in range(len(values))]
        s.add(z3.PbEq([(b, 1) for b in self.b], 1))


def build(space, wl):
    s = z3.Solver()
    V = dict(n_e=Choice(s, 'n_e', space.n_e), edge_cls=Choice(s, 'ce', space.edge_cls),
             n_g=Choice(s, 'n_g', space.n_g), gw_cls=Choice(s, 'cg', space.gw_cls),
             rep=Choice(s, 'rep', space.rep), policy=Choice(s, 'pol', list(space.policy)),
             link_cls=Choice(s, 'lk', space.link_cls), cloud_cls=Choice(s, 'cc', space.cloud_cls))
    entries = [0]

    def table(support, fn):
        """sum over the support's joint domain of If(assignment, fn(values), 0)."""
        terms = []
        for combo in itertools.product(*[range(len(V[v].values)) for v in support]):
            vals = {v: V[v].values[j] for v, j in zip(support, combo)}
            q = fn(**vals)
            if q is None:
                continue
            entries[0] += 1
            if q != 0:
                terms.append(z3.If(z3.And([V[v].b[j] for v, j in zip(support, combo)]), R(q), R(Fr(0))))
        return z3.Sum(terms) if terms else R(Fr(0))

    def forbid(support, pred):
        for combo in itertools.product(*[range(len(V[v].values)) for v in support]):
            vals = {v: V[v].values[j] for v, j in zip(support, combo)}
            if pred(**vals):
                s.add(z3.Not(z3.And([V[v].b[j] for v, j in zip(support, combo)])))

    # structural validity, as in the enumerative methods
    forbid(['n_g', 'n_e'], lambda n_g, n_e: n_g > n_e)
    forbid(['rep', 'n_e'], lambda rep, n_e: rep > n_e)
    forbid(['rep', 'policy'], lambda rep, policy: policy == 'cloud-first' and rep > 1)

    st = wl.stages; lam = F(wl.Lambda); T = F(wl.horizon); rmax = F(wl.rho_max)
    t1 = lambda p: POLICIES[p][0]; t3 = lambda p: POLICIES[p][1]
    def load(tier, rep, policy):
        l = F(0)
        if t1(policy) == tier: l += lam * F(st[0].w) * rep
        if tier == 'gw': l += lam * F(st[1].w)
        if t3(policy) == tier: l += lam * F(st[2].w)
        return l
    rho_e = lambda n_e, edge_cls, rep, policy: load('edge', rep, policy) / (n_e * F(edge_cls.C))
    rho_g = lambda n_g, gw_cls, rep, policy: load('gw', rep, policy) / (n_g * F(gw_cls.C))
    rho_c = lambda cloud_cls, policy: load('cloud', 1, policy) / F(cloud_cls.C)
    # utilisation limits (feasibility)
    forbid(['n_e', 'edge_cls', 'rep', 'policy'], lambda **k: rho_e(**k) > rmax)
    forbid(['n_g', 'gw_cls', 'rep', 'policy'], lambda **k: rho_g(**k) > rmax)
    forbid(['cloud_cls', 'policy'], lambda **k: rho_c(**k) > rmax)
    # memory limits
    def mem(tier, rep, policy):
        m = F(0)
        if t1(policy) == tier: m += F(st[0].mem) * rep
        if tier == 'gw': m += F(st[1].mem)
        if t3(policy) == tier: m += F(st[2].mem)
        return m
    forbid(['edge_cls', 'rep', 'policy'], lambda edge_cls, rep, policy: mem('edge', rep, policy) > F(edge_cls.M))
    forbid(['gw_cls', 'rep', 'policy'], lambda gw_cls, rep, policy: mem('gw', rep, policy) > F(gw_cls.M))

    # latency: service time + M/D/1 waiting per stage, on the tier the stage runs on
    def stage_latency(w, rho, C):
        svc = F(w) / F(C)
        return svc + svc * rho / (2 * (1 - rho))
    def edge_part(n_e, edge_cls, rep, policy):
        r = rho_e(n_e, edge_cls, rep, policy); L = F(0)
        if r > rmax: return None
        if t1(policy) == 'edge': L += stage_latency(st[0].w, r, edge_cls.C)
        if t3(policy) == 'edge': L += stage_latency(st[2].w, r, edge_cls.C)
        return L
    def gw_part(n_g, gw_cls, rep, policy):
        r = rho_g(n_g, gw_cls, rep, policy)
        if r > rmax: return None
        L = stage_latency(st[1].w, r, gw_cls.C)
        if t1(policy) == 'gw': L += stage_latency(st[0].w, r, gw_cls.C)
        return L
    def cloud_part(cloud_cls, policy):
        r = rho_c(cloud_cls, policy)
        if r > rmax: return None
        return stage_latency(st[2].w, r, cloud_cls.C) if t3(policy) == 'cloud' else F(0)
    def acc_payload(rep, policy):
        p = F(st[0].s_in)
        if t1(policy) == 'edge':
            p += F(st[1].s_in)
            if rep > 1: p += (rep - 1) * F(wl.s_sync)
        if t3(policy) != 'cloud': p += F(st[2].s_in)
        return p
    def n_acc_hops(rep, policy):
        return 1 + ((1 + (1 if rep > 1 else 0)) if t1(policy) == 'edge' else 0) + (0 if t3(policy) == 'cloud' else 1)
    def net_latency(rep, policy, link_cls):
        L = acc_payload(rep, policy) * F(MB_TO_MB) / F(link_cls.B) + n_acc_hops(rep, policy) * F(link_cls.prop)
        if t3(policy) == 'cloud': L += F(st[2].s_in) * F(MB_TO_MB) / F(WAN_B) + F(WAN_PROP)
        return L
    Lat = (table(['n_e', 'edge_cls', 'rep', 'policy'], edge_part) +
           table(['n_g', 'gw_cls', 'rep', 'policy'], gw_part) +
           table(['cloud_cls', 'policy'], cloud_part) +
           table(['rep', 'policy', 'link_cls'], net_latency))
    s.add(Lat <= R(F(wl.deadline)))
    # access bandwidth
    forbid(['rep', 'policy', 'link_cls', 'n_e', 'n_g'],
           lambda rep, policy, link_cls, n_e, n_g: acc_payload(rep, policy) * lam * F(MB_TO_MB) >
           (n_e if t1(policy) == 'edge' else n_g) * F(link_cls.B))
    # energy over the horizon
    def e_edge(n_e, edge_cls, rep, policy):
        r = rho_e(n_e, edge_cls, rep, policy)
        return None if r > rmax else n_e * (F(edge_cls.P_idle) + r * (F(edge_cls.P_peak) - F(edge_cls.P_idle))) * T
    def e_gw(n_g, gw_cls, rep, policy):
        r = rho_g(n_g, gw_cls, rep, policy)
        return None if r > rmax else n_g * (F(gw_cls.P_idle) + r * (F(gw_cls.P_peak) - F(gw_cls.P_idle))) * T
    def e_cloud(cloud_cls, policy):
        r = rho_c(cloud_cls, policy)
        return None if r > rmax else r * F(cloud_cls.P_peak) * T
    def e_net(rep, policy, link_cls):
        e = acc_payload(rep, policy) * lam * F(link_cls.e) * T
        if t3(policy) == 'cloud': e += F(st[2].s_in) * lam * F(WAN_E) * T
        return e
    En = (table(['n_e', 'edge_cls', 'rep', 'policy'], e_edge) + table(['n_g', 'gw_cls', 'rep', 'policy'], e_gw) +
          table(['cloud_cls', 'policy'], e_cloud) + table(['rep', 'policy', 'link_cls'], e_net))
    s.add(En <= R(F(wl.E_max)))
    Cost = (table(['n_e', 'edge_cls'], lambda n_e, edge_cls: n_e * F(edge_cls.cost)) +
            table(['n_g', 'gw_cls'], lambda n_g, gw_cls: n_g * F(gw_cls.cost)) +
            table(['n_e', 'n_g', 'link_cls'], lambda n_e, n_g, link_cls: (n_e + n_g) * F(link_cls.cost)) +
            table(['cloud_cls'], lambda cloud_cls: F(cloud_cls.cost)))
    s.add(Cost <= R(F(wl.C_max)))
    Vol = table(['rep', 'policy'], lambda rep, policy: (acc_payload(rep, policy) +
                (F(st[2].s_in) if t3(policy) == 'cloud' else F(0))) * lam)
    return s, (Lat, En, Cost, Vol), V, entries[0]


def design_of(m, V):
    return {k: c.values[next(j for j, b in enumerate(c.b) if z3.is_true(m.eval(b, model_completion=True)))]
            for k, c in V.items()}


def pareto_gia(space, wl):
    t0 = time.perf_counter()
    s, Fx, V, n_entries = build(space, wl)
    t_build = time.perf_counter() - t0
    front, checks = [], 0
    while True:
        checks += 1
        if s.check() != z3.sat:
            break
        m = s.model(); v = [m.eval(f, model_completion=True) for f in Fx]; x = design_of(m, V)
        while True:
            s.push()
            s.add(z3.And([f <= vi for f, vi in zip(Fx, v)]), z3.Or([f < vi for f, vi in zip(Fx, v)]))
            checks += 1
            ok = s.check() == z3.sat
            if ok:
                m = s.model(); v = [m.eval(f, model_completion=True) for f in Fx]; x = design_of(m, V)
            s.pop()
            if not ok:
                break
        front.append((x, v))
        s.add(z3.Or([f < vi for f, vi in zip(Fx, v)]))
    return front, checks, n_entries, t_build, time.perf_counter() - t0


if __name__ == '__main__':
    scales = sys.argv[1:] or ['S1', 'S2', 'S3']
    rows = []
    for scale in scales:
        space = make_space(scale)
        for name, wl in WORKLOADS.items():
            front, checks, n_entries, t_build, t = pareto_gia(space, wl)
            ref = exhaustive(space, wl)
            verify = [evaluate(x, wl) for x, _ in front]      # verification only
            got = objset([(x, r.objectives) for (x, _), r in zip(front, verify)])
            exact = got == objset(ref.front) and all(r.feasible for r in verify)
            row = dict(scale=scale, workload=name, method='smt-factorised', raw=space.size,
                       full_evaluator_calls=0, table_entries=n_entries, solver_checks=checks,
                       pareto=len(front), build_s=round(t_build, 3), total_s=round(t, 3),
                       verification_calls=len(front), exact=exact)
            rows.append(row); print(row, flush=True)
    out = 'results/e12_symbolic.csv' if scales == ['S1', 'S2', 'S3'] else f'results/e12_symbolic_{"_".join(scales)}.csv'
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, list(rows[0])); w.writeheader(); w.writerows(rows)
    print('written', out)
