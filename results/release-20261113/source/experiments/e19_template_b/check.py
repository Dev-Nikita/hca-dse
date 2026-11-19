"""E19 machine check on scale B1 of template B.

For every structurally valid prefix and every completion of it: the bound of
Section 4 and the generic partial cost never exceed the evaluated objectives
(admissibility), and the bound is never below the partial cost (the ordering
Proposition 4 needs).  Bounds and objectives are computed in rational
arithmetic, so the comparisons are exact and no tolerance is used.  Unstable
completions have infinite objectives and are skipped as values, not as
prefixes.
"""
from __future__ import annotations

import argparse, itertools, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hcadse import template_b as tb



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="B1")
    ap.add_argument("--out", default="results/e19_template_b/check_B1.json")
    a = ap.parse_args()
    dom = tb.domains(a.scale)
    rows = []
    for wname, wl in tb.WORKLOADS.items():
        ours = tb.Bounds(a.scale, wl, exact=True)
        gen = tb.Bounds(a.scale, wl, relax=False, exact=True)
        designs = []
        for combo in itertools.product(*[dom[v] for v in tb.ORDER]):
            x = dict(zip(tb.ORDER, combo))
            if tb.well_formed(x):
                designs.append((x, tb.evaluate(x, wl, exact=True)[0]))
        prefixes = checks = violations = order_violations = 0
        for depth in range(1, len(tb.ORDER) + 1):
            groups = {}
            for x, f in designs:
                key = tuple(id(x[v]) if not isinstance(x[v], (int, str)) else x[v]
                            for v in tb.ORDER[:depth])
                groups.setdefault(key, []).append((x, f))
            for members in groups.values():
                p = {v: members[0][0][v] for v in tb.ORDER[:depth]}
                lo, lg = ours(p), gen(p)
                prefixes += 1
                if lo[0] != tb.INF:
                    order_violations += sum(lg[i] > lo[i] for i in range(4))
                for x, f in members:
                    if f[0] == tb.INF:
                        continue
                    checks += 1
                    for b in (lo, lg):
                        violations += sum(b[i] > f[i] for i in range(4))
        rows.append(dict(scale=a.scale, workload=wname, prefixes=prefixes, checks=checks,
                         admissibility_violations=violations,
                         ordering_violations=order_violations))
        print(json.dumps(rows[-1]), flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rows, indent=1) + "\n")
    assert all(r["admissibility_violations"] == 0 and r["ordering_violations"] == 0
               for r in rows), "check failed"


if __name__ == "__main__":
    main()
