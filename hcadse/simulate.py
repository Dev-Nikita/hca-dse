"""Seeded FCFS discrete-event evaluator with per-tier servers and fork/join replicas.

Propagation is scheduled as an arrival event, not as a reservation of a future
server slot. Service is deterministic; arrivals are Poisson. This evaluator is
separate from the analytical model and has no admissibility guarantee.
"""
from collections import deque
import heapq
import itertools
import math
import random
from .model import POLICIES, WAN_B, WAN_PROP


def simulate(x, wl, n_req=4000, warmup=400, seed=0):
    if n_req <= warmup or warmup < 0:
        raise ValueError("require 0 <= warmup < n_req")
    rng = random.Random(seed)
    t1, t3 = POLICIES[x['policy']]
    cls = {'edge': x['edge_cls'], 'gw': x['gw_cls'], 'cloud': x['cloud_cls']}
    capacities = {'edge': x['n_e'], 'gw': x['n_g'], 'cloud': 1,
                  'access': x['n_e'] if t1 == 'edge' else x['n_g'], 'wan': 1}
    free = dict(capacities)
    queues = {k: deque() for k in capacities}
    lk = x['link_cls']; st = wl.stages
    # resource, deterministic service duration, propagation, number of jobs
    def link(kind, size):
        return (kind, 8 * size / (lk.B if kind == 'access' else WAN_B),
                lk.prop if kind == 'access' else WAN_PROP, 1)
    route = [link('access', st[0].s_in), (t1, st[0].w / cls[t1].C, 0, x['rep'])]
    if t1 == 'edge':
        route.append(link('access', st[1].s_in))
        if x['rep'] > 1:
            route.append(link('access', (x['rep'] - 1) * wl.s_sync))
    route.extend([('gw', st[1].w / cls['gw'].C, 0, 1),
                  link('wan' if t3 == 'cloud' else 'access', st[2].s_in),
                  (t3, st[2].w / cls[t3].C, 0, 1)])
    events = []; serial = itertools.count(); arrivals = []; waiting = {}; done = {}
    def event(t, kind, i, step):
        heapq.heappush(events, (t, next(serial), kind, i, step))
    def enter(t, i, step):
        if step == len(route):
            done[i] = t - arrivals[i]
            return
        _, _, prop, copies = route[step]
        waiting[i, step] = copies
        for _ in range(copies):
            event(t + prop, 'arrive', i, step)
    t = 0.0
    for i in range(n_req):
        t += rng.expovariate(wl.Lambda); arrivals.append(t); enter(t, i, 0)
    while events:
        now, _, kind, i, step = heapq.heappop(events)
        if now > 4 * n_req / wl.Lambda:
            return dict(mean=math.inf, p50=math.inf, p95=math.inf, completed=len(done))
        resource, service, _, _ = route[step]
        if kind == 'arrive':
            if free[resource]:
                free[resource] -= 1; event(now + service, 'finish', i, step)
            else:
                queues[resource].append((i, step))
        else:
            if queues[resource]:
                j, k = queues[resource].popleft()
                event(now + route[k][1], 'finish', j, k)
            else:
                free[resource] += 1
            waiting[i, step] -= 1
            if waiting[i, step] == 0:
                enter(now, i, step + 1)
    values = [done[i] for i in range(warmup, n_req)]
    ordered = sorted(values)
    return dict(mean=sum(values)/len(values), p50=ordered[len(values)//2],
                p95=ordered[int(.95*(len(values)-1))], completed=len(values))
