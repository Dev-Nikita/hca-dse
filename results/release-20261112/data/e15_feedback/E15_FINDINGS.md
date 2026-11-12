# E15 — exactness under a term the compact solver encodings do not express

Run 25 Oct 2026. The question the earlier rounds left open: the factorised SMT
encoding (E12) recovers the same screening front with **no** evaluator call, so
where is partial-design pruning actually necessary? The answer the paper gave
was a claim about preconditions. This experiment turns it into a measurement.

## 1. The term

Soft-deadline retries (`hcadse/feedback.py`). A request whose latency exceeds
`tau = 0.5 * deadline` is retried once, so retried requests raise the load that
produced them, and the effective arrival rate is the least solution of

    lam* = lam * (1 + exp(-tau / L(lam*)))

with `L` the mean latency of the deployment at that rate. Every load-dependent
quantity is then evaluated at `lam*`.

Two properties:

* **Support.** `lam*` depends on all eight decisions at once, because `L` does.
  The factorised encoding needs each term tabulated over a small support; the
  only table that represents this term is indexed by the whole design space
  (1 296 / 5 832 / 51 840 entries on S1/S2/S3), one evaluation per entry. We
  know of no decomposition into terms of bounded support. The polynomial
  encoding cannot express it either: it is a fixed point of a map built from
  `exp(.)`.
* **Bounds still work.** `G` is monotone in `lam` and monotone in the model
  terms, so the least fixed point of the map built from term-wise optimistic
  values is below the least fixed point of every completion (Proposition 4 in
  the manuscript). The bound of Section 4.2 is reused unchanged.

## 2. Results

| scale | exhaustive evals | HCA-DSE evals | reduction | exact front | finite-table evals | factorised entries |
|---|---:|---:|---:|:--:|---:|---:|
| S1 | 1 080 | 15–25 | 43–72x | yes | 1 080 | 1 296 |
| S2 | 3 888 | 25–41 | 95–156x | yes | 3 888 | 5 832 |
| S3 | 34 560 | 46–52 | 665–751x | yes | — | 51 840 |

All nine runs reproduce the exact Pareto front of the retry model. The
finite-table Z3 baseline is exact too, but it evaluates every design first and
then spends 0.5–22.7 s in the solver; the compact encoding, which was the real
competitor, has no formulation here at all.

Admissibility is machine-checked: on S1 every one of 1 939 prefixes against
every completion (29 160 prefix/completion pairs across the three workloads),
and 169 prefixes with 58 320 pairs on S2. The fixed-point iteration converges
in 5.4–8.7 iterations on average, 345 at worst.

## 3. What this does not show

* It does not prove that no factorisation of the retry term exists, only that
  we know of none. A different feedback model may well be factorisable.
* The retry rule is a modelling choice (one retry, exponential tail, soft
  target at half the deadline), standard rather than measured on the testbed.
* The term is consequential but not dominant: screening with the closed-form
  model and re-evaluating its front under retries still recovers 0.850–1.000 of
  the retry front. The study is about representability, not about the size of
  the feedback effect.
* Proposition 4 needs a monotone map. A non-monotone feedback model would need
  a different argument.

## 4. Reproduction

```
experiments/e15_feedback/fb_driver.py --scales S1,S2,S3 --table-scales S1,S2 \
    --out results/e15_feedback
experiments/e15_feedback/check_admissible.py --scale S1 --depth-max 8 \
    --out results/e15_feedback/admissible_S1.json
experiments/e15_feedback/check_admissible.py --scale S2 --depth-max 4 \
    --out results/e15_feedback/admissible_S2.json
experiments/e15_feedback/make_e15_claims.py .
```
