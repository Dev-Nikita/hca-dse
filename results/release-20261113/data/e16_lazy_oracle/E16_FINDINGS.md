# E16 — lazy external-oracle SMT

Run 25 October 2026 with `z3-solver==5.1.0.0` from the project virtual
environment. The solver contains only finite decision domains and structural
constraints. Each satisfying complete assignment is sent to the evaluator and
then blocked by a no-good clause. A 20 s wall-time limit is applied separately
to each model/scale/workload combination; an incomplete archive is never called
exact.

## Result

- S1 completes for all workloads and both analytical/retry evaluators: 1080
  evaluator calls and 1081 solver checks, with exact front equality.
- S2 completes for all workloads and both evaluators: 3888 evaluator calls and
  3889 solver checks, with exact front equality.
- All six S3 runs time out. The analytical evaluator reaches 9490--9902 oracle
  calls; the retry evaluator reaches 8307--8806. None receives an UNSAT
  certificate, so no S3 archive is reported as exact.

The baseline avoids an up-front objective table but does not avoid evaluations:
with a black-box oracle, a no-good clause safely excludes only the architecture
already evaluated. Excluding an unseen region requires additional sound
structure. HCA-DSE supplies that structure through admissible partial-design
bounds; the compact factorised SMT encoding supplies it by representing the
entire evaluator symbolically.

## Interpretation boundary

This result does not establish that every lazy SMT, nonlinear SMT, CP-SAT or MIP
formulation must behave this way. It establishes the cost of one reproducible
external-oracle baseline with no model-specific cuts. Stronger exact encodings
remain an open comparison.

Raw measurements are in `results/e16_lazy_oracle.csv`; implementation is
`experiments/e16_lazy_oracle.py`.
