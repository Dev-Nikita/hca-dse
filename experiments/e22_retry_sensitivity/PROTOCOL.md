# E22: sensitivity of the retry comparison, protocol fixed before the runs (21 Nov 2026)

Question. Does the evaluation-count gap between the unlifted generic bound (R1) and
the lifted bounds (R1fp, R3) of E21 depend on the particular retry model?

- Retry model variants: soft-target fraction alpha in {0.25, 0.5, 0.75} and maximum
  retry share q_max in {0.5, 1.0} (q = q_max * exp(-theta/L), theta = alpha * D): six
  settings, one of which (0.5, 1.0) is the model of the paper. Each keeps q continuous,
  non-decreasing and bounded, as Proposition 5 requires; the evaluator, every bound and
  the certified archive use the same setting.
- Scale S2, workloads telemetry, control, sensing: 18 combinations.
- Configurations of E21: R0 exhaustive, R1, R1fp (certified), R3. One run each:
  evaluation and state counts are deterministic; times are not reported.
- Reported: full evaluations and expanded states per configuration, front size,
  front equality with R0, and the ranges of R1/R3 and R1fp/R3 for evaluations.
- Results are reported whatever their direction.

Also fixed before the runs: R1fp of E21 is re-run with the certified fixed point
(directed-rounding decimal iteration, as R3) in place of the binary64 iteration.
