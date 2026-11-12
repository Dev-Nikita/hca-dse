"""E12 (first attempt, not used for results): direct polynomial QF_NRA encoding.

The design space is encoded as a polynomial real-arithmetic model in Z3: every decision
variable is a real-valued unknown restricted to its finite domain, tier utilisations,
service times and M/D/1 waiting terms are auxiliary unknowns tied to the decisions by
polynomial equalities, and all constants are the exact rationals of the binary64 model
parameters. No design point is enumerated and the Python evaluator is never called while
solving. The exact Pareto set is enumerated with the guided-improvement algorithm:
find any feasible design, strengthen it by requiring Pareto dominance until the
constraint system becomes unsatisfiable, record the resulting non-dominated vector, and
exclude everything it weakly dominates.

After solving, the designs returned by the solver are re-evaluated with the ordinary
evaluator only to compare their binary64 objective vectors with the exhaustive front;
those verification calls are reported separately and are not part of the method.
"""
import sys, os, csv, time
from fractions import Fraction
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import z3
from hcadse.model import make_space, WORKLOADS, POLICIES, WAN_B, WAN_PROP, WAN_E
from hcadse.evaluate import evaluate, MB_TO_MB
from hcadse.search import exhaustive
from hcadse.metrics import objset

Q = lambda v: z3.RealVal(str(Fraction(v)))


def build(space, wl):
    s = z3.Solver()
    dom = {}
    def choice(name, values):
        v = z3.Real(name)
        s.add(z3.Or([v == Q(x) for x in values]))
        return v
    ne = choice('n_e', space.n_e); ng = choice('n_g', space.n_g); rep = choice('rep', space.rep)
    # categorical choices: integer index in [0, k), attributes are if-then-else over constants
    class OneHot:
        """Categorical choice as exactly-one Booleans; keeps the model in QF_NRA."""
        def __init__(self, name, k):
            self.b = [z3.Bool(f'{name}_{j}') for j in range(k)]
            s.add(z3.PbEq([(b, 1) for b in self.b], 1))
        def __eq__(self, k):
            return self.b[k]
    def idx(name, k):
        return OneHot(name, k)
    ie = idx('edge_cls', len(space.edge_cls)); ig = idx('gw_cls', len(space.gw_cls))
    ic = idx('cloud_cls', len(space.cloud_cls)); il = idx('link_cls', len(space.link_cls))
    pol_names = list(space.policy); ip = idx('policy', len(pol_names))
    def attr(i, objs, f):
        e = Q(f(objs[-1]))
        for k in range(len(objs) - 2, -1, -1):
            e = z3.If(i == k, Q(f(objs[k])), e)
        return e
    Ce = attr(ie, space.edge_cls, lambda c: c.C); Cg = attr(ig, space.gw_cls, lambda c: c.C)
    Cc = attr(ic, space.cloud_cls, lambda c: c.C)
    # policy -> tiers of stage 1 and stage 3
    t1_edge = z3.Or([ip == k for k, p in enumerate(pol_names) if POLICIES[p][0] == 'edge'])
    t3_edge = z3.Or([ip == k for k, p in enumerate(pol_names) if POLICIES[p][1] == 'edge'])
    t3_cloud = z3.Not(t3_edge)
    cloud_first = z3.Or([ip == k for k, p in enumerate(pol_names) if p == 'cloud-first'])
    # structural validity (same predicate as the enumerative methods)
    s.add(ng <= ne, rep <= ne, z3.Implies(cloud_first, rep == 1))

    lam = Q(wl.Lambda); st = wl.stages
    w0, w1, w2 = Q(st[0].w), Q(st[1].w), Q(st[2].w)
    load_e = lam * (z3.If(t1_edge, w0 * rep, 0) + z3.If(t3_edge, w2, 0))
    load_g = lam * (z3.If(t1_edge, 0, w0 * rep) + w1)
    load_c = lam * z3.If(t3_cloud, w2, 0)
    rho_e, rho_g, rho_c = z3.Reals('rho_e rho_g rho_c')
    s.add(rho_e * ne * Ce == load_e, rho_g * ng * Cg == load_g, rho_c * Cc == load_c)
    rmax = Q(wl.rho_max)
    s.add(rho_e <= rmax, rho_g <= rmax, rho_c <= rmax)
    mem_e = z3.If(t1_edge, Q(st[0].mem) * rep, 0) + z3.If(t3_edge, Q(st[2].mem), 0)
    mem_g = z3.If(t1_edge, 0, Q(st[0].mem) * rep) + Q(st[1].mem)
    s.add(mem_e <= attr(ie, space.edge_cls, lambda c: c.M))
    s.add(mem_g <= attr(ig, space.gw_cls, lambda c: c.M))

    # stage service time and M/D/1 waiting term on the tier each stage runs on
    def stage_terms(w, on_edge, on_gw, name):
        svc = z3.If(on_edge, w / Ce, z3.If(on_gw, w / Cg, w / Cc))
        rho = z3.If(on_edge, rho_e, z3.If(on_gw, rho_g, rho_c))
        wait = z3.Real('wait_' + name)
        s.add(wait * 2 * (1 - rho) == svc * rho)
        return svc + wait
    L = (stage_terms(w0, t1_edge, z3.Not(t1_edge), 's1') +
         stage_terms(w1, z3.BoolVal(False), z3.BoolVal(True), 's2') +
         stage_terms(w2, t3_edge, z3.BoolVal(False), 's3'))
    B = attr(il, space.link_cls, lambda l: l.B); prop = attr(il, space.link_cls, lambda l: l.prop)
    le = attr(il, space.link_cls, lambda l: l.e)
    mbit = Q(MB_TO_MB)
    # hops (payload MB, access?) exactly as in evaluate.hops
    s0, s1, s2 = Q(st[0].s_in), Q(st[1].s_in), Q(st[2].s_in)
    sync = (rep - 1) * Q(wl.s_sync)
    acc_payload = s0 + z3.If(t1_edge, s1 + z3.If(rep > 1, sync, 0), 0) + z3.If(t3_cloud, 0, s2)
    n_acc_hops = 1 + z3.If(t1_edge, 1 + z3.If(rep > 1, 1, 0), 0) + z3.If(t3_cloud, 0, 1)
    wan_payload = z3.If(t3_cloud, s2, 0)
    L = L + acc_payload * mbit / B + n_acc_hops * prop + \
        z3.If(t3_cloud, s2 * mbit / Q(WAN_B) + Q(WAN_PROP), 0)
    s.add(L <= Q(wl.deadline))
    n_access = z3.If(t1_edge, ne, ng)
    s.add(acc_payload * lam * mbit <= n_access * B)
    T = Q(wl.horizon)
    def power(n, cls, rho, objs):
        pi = attr(cls, objs, lambda c: c.P_idle); pp = attr(cls, objs, lambda c: c.P_peak)
        return n * (pi + rho * (pp - pi)) * T
    E = power(ne, ie, rho_e, space.edge_cls) + power(ng, ig, rho_g, space.gw_cls) + \
        rho_c * attr(ic, space.cloud_cls, lambda c: c.P_peak) * T + \
        acc_payload * lam * le * T + wan_payload * lam * Q(WAN_E) * T
    s.add(E <= Q(wl.E_max))
    lc = attr(il, space.link_cls, lambda l: l.cost)
    C = ne * (attr(ie, space.edge_cls, lambda c: c.cost) + lc) + \
        ng * (attr(ig, space.gw_cls, lambda c: c.cost) + lc) + attr(ic, space.cloud_cls, lambda c: c.cost)
    s.add(C <= Q(wl.C_max))
    D = (acc_payload + wan_payload) * lam
    decode = dict(ne=ne, ng=ng, rep=rep, ie=ie, ig=ig, ic=ic, il=il, ip=ip, pol=pol_names)
    return s, (L, E, C, D), decode


def design_of(m, d, space):
    val = lambda e: m.eval(e, model_completion=True)
    pick = lambda oh: next(j for j, b in enumerate(oh.b) if z3.is_true(val(b)))
    return dict(n_e=int(val(d['ne']).as_fraction()), edge_cls=space.edge_cls[pick(d['ie'])],
                n_g=int(val(d['ng']).as_fraction()), gw_cls=space.gw_cls[pick(d['ig'])],
                rep=int(val(d['rep']).as_fraction()), policy=d['pol'][pick(d['ip'])],
                link_cls=space.link_cls[pick(d['il'])],
                cloud_cls=space.cloud_cls[pick(d['ic'])])


def pareto_gia(space, wl):
    s, F, d = build(space, wl)
    front, checks = [], 0
    t0 = time.perf_counter()
    while True:
        checks += 1
        if s.check() != z3.sat:
            break
        m = s.model(); v = [m.eval(f, model_completion=True) for f in F]; x = design_of(m, d, space)
        while True:  # strengthen until no dominating design exists
            s.push()
            s.add(z3.And([f <= vi for f, vi in zip(F, v)]), z3.Or([f < vi for f, vi in zip(F, v)]))
            checks += 1
            if s.check() == z3.sat:
                m = s.model(); v = [m.eval(f, model_completion=True) for f in F]; x = design_of(m, d, space)
                s.pop()
            else:
                s.pop(); break
        front.append((x, v)); print('  front point', len(front), 'checks', checks, round(time.perf_counter()-t0,1), flush=True)
        s.add(z3.Or([f < vi for f, vi in zip(F, v)]))
    return front, checks, time.perf_counter() - t0


if __name__ == '__main__':
    scales = sys.argv[1:] or ['S1', 'S2', 'S3']
    rows = []
    for scale in scales:
        space = make_space(scale)
        for name, wl in WORKLOADS.items():
            front, checks, t = pareto_gia(space, wl)
            ref = exhaustive(space, wl)
            verify = [evaluate(x, wl) for x, _ in front]      # verification only
            got = objset([(x, r.objectives) for (x, _), r in zip(front, verify)])
            exact = got == objset(ref.front) and all(r.feasible for r in verify)
            row = dict(scale=scale, workload=name, method='z3-compact', full_evaluator_calls=0,
                       solver_checks=checks, pareto=len(front), runtime=round(t, 3),
                       verification_calls=len(front), exact=exact)
            rows.append(row); print(row, flush=True)
    out = 'results/e12_symbolic_polynomial.csv' if len(scales) == 3 else f'results/e12_symbolic_polynomial_{"_".join(scales)}.csv'
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, list(rows[0])); w.writeheader(); w.writerows(rows)
    print('written', out)
