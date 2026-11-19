# E14 — end-to-end search with the discrete-event simulator as the leaf evaluator

Run 24 Oct 2026. Scales S1–S3, three workloads, simulator configured as in the
reported timing measurement (`n_req=3000`, `warmup=400`). S1 and S2 use the
median of five seeds per design, S3 a single seed. Latency comes from the
simulator; energy, cost and network volume stay analytical, because the
simulator reports latency only. Feasibility uses the simulated latency for the
deadline and the analytical model for every other constraint.

Three protocols, same ground truth:

* **EXH-DES** — every structurally valid design simulated. The reference front.
* **TWO-LEVEL** — exact search on the analytical model, then the surviving
  front re-evaluated with the simulator. This is the workflow the manuscript
  already recommends in its discussion, now measured.
* **INLINE** — the simulator inside the search loop, pruning still driven by
  the analytical bounds. No guarantee holds here; the point is to measure what
  it costs and what it loses.

## 1. Measured cost, not a projection

| scale | workload | EXH-DES sims | EXH-DES time | two-level sims | speed-up | recall |
|---|---|---:|---:|---:|---:|---:|
| S1 | telemetry | 5 400 | 7.2 min | 85 | 73× | 1.000 |
| S1 | control | 5 400 | 7.7 min | 90 | 70× | 0.944 |
| S1 | sensing | 5 400 | 5.1 min | 55 | 79× | 0.667 |
| S2 | telemetry | 19 440 | 28.3 min | 135 | 167× | 0.960 |
| S2 | control | 19 440 | 30.0 min | 125 | 209× | 0.913 |
| S2 | sensing | 19 440 | 20.2 min | 80 | 214× | 0.722 |
| S3 | telemetry | 34 560 | 56.9 min | 31 | 1 460× | 1.000 |
| S3 | control | 34 560 | 56.8 min | 27 | 1 757× | 0.885 |
| S3 | sensing | 34 560 | 45.0 min | 27 | 1 533× | 0.714 |

The manuscript reports a projected speed-up of up to 775× and states that an
end-to-end simulator search was never executed. It now has been: the measured
wall-clock ratio at S3 is **1 460–1 757×**, obtained by running both sides on
the same machine. The projection was conservative.

## 2. The simulator inside the loop is worse, not better

| scale | two-level recall | inline recall | two-level sims | inline sims |
|---|---:|---:|---:|---:|
| S1 | 0.667–1.000 | 0.667–0.824 | 55–90 | 100–220 |
| S2 | 0.722–0.960 | 0.500–0.680 | 80–135 | 120–440 |
| S3 | 0.714–1.000 | 0.429–0.760 | 27–31 | 26–277 |

Inline recall is lower on every one of the nine runs, median 0.667 against
0.913, and it costs more simulator calls on six of nine. The reason is
structural: the archive then holds simulated vectors while the bounds are
computed from the analytical model, so dominance pruning compares quantities
that do not belong to the same objective. This is the first direct measurement
of the condition the manuscript states but never tested — that carrying the
certificate to another evaluator requires bounds admissible for that evaluator.

## 3. A screening margin converts the loss into a dial

Each design in the exhaustive sweep was recorded with both its analytical and
its simulated objective vector, so the following sweep required no further
simulation. The margin keeps every design that the analytical front fails to
dominate once the front is inflated by eps.

| scale | workload | eps | simulator calls | recall of the DES front |
|---|---|---:|---:|---:|
| S3 | telemetry | 0.00 | 31 | 1.000 |
| S3 | control | 0.00 | 29 | 0.962 |
| S3 | control | 0.01 | 1 765 | 1.000 |
| S3 | sensing | 0.00 | 27 | 0.714 |
| S3 | sensing | 0.10 | 1 119 | 0.905 |
| S3 | sensing | 0.20 | 1 572 | 1.000 |
| S2 | sensing | 0.20 | 389 | 1.000 |

At S3 a 20 % margin recovers the complete simulator front on all three
workloads at 1 572–3 419 calls against 34 560 — still a 10–22× reduction, and
with nothing lost. At eps = 0 the reduction is 1 100–1 280× and the recall is
workload-dependent. That is an engineering dial with both endpoints measured.

## 4. What this does not show

* The margin carries **no guarantee**. Recall 1.000 at eps = 0.20 is an
  observation on three workloads at one scale, not a theorem. Nothing here
  proves a margin that suffices in general.
* S3 used **one seed per design**. The seed-robustness check (E14b,
  `e14b_seedcheck.py`, `seedcheck.csv`) re-simulated with five seeds every design
  that the single-seed simulated front does not dominate by more than 5%
  (1018-1831 designs per workload, 5090-9155 further simulator runs) and
  recomputed the front from the medians. Every member of the single-seed front
  (21-26 designs) stays non-dominated, the five-seed front gains at most one
  member, and the screening recall, recomputed identically under both regimes,
  moves by at most 0.032 (sensing 0.714 -> 0.682; control and telemetry
  unchanged). Designs more than 5% behind the front were left at their
  single-seed value, so the check is conditional on that margin. Per-design
  spread over the five seeds: median 0.05-3.2% of the design's median latency,
  ninetieth percentile 0.5-38.8% -- the tail is the near-saturation designs,
  which is why medians over seeds are used everywhere.
* Only **latency** is simulated. Energy, cost and network volume remain
  analytical in every protocol, so "the simulator's front" means the front
  under a simulated latency and an analytical everything-else.
* The margin sweep screens with analytical objectives over the set of designs
  that are feasible under the **simulated** deadline. A deployed screening
  stage would also decide feasibility analytically; the small set of designs
  where the two disagree is not separated here.
* One architecture template, as before. Nothing in these runs speaks to
  transfer to another topology.

## 5. Reproduction

```
experiments/e14_des_endtoend/des_driver.py --scale S3 --workload telemetry \
    --seeds 0 --out results/e14_des_endtoend/S3_telemetry.json
experiments/e14_des_endtoend/margin.py results/e14_des_endtoend/dumps/*.json
experiments/e14_des_endtoend/e14b_seedcheck.py results/e14_des_endtoend/S3_*.json \
    --eps 0.05 --out results/e14_des_endtoend/seedcheck.json
experiments/e14_des_endtoend/make_e14_claims.py .
```

Raw per-run records are in `results/e14_des_endtoend/`; the full per-design
dumps, each holding both objective vectors for every feasible design, are the
gzipped files under `dumps/`.
