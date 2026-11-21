# E20 and E21: protocol, fixed before the runs (21 Nov 2026)

Question. Does the bound of Section 4 save full evaluations, not only expanded
states, against the generic partial-cost bound (G1c) (a) when the constraints are
tighter or looser than in the main study, and (b) under the retry model, where
the generic bound cannot see the load amplification?

E20, constraint regimes (base model).
- Regimes: the deadline D, the cost budget C_max and the energy budget E_max of
  every workload are multiplied jointly by m in {0.8 (tight), 1.0 (baseline),
  1.25 (loose)}; rho_max and all other parameters are unchanged. No other value
  of m is run.
- Scales S1, S2, S3; workloads telemetry, control, sensing: 27 combinations.
- Configurations: G0 exhaustive; G1c generic partial cost with the same
  two-stage protocol and caching; G2 the bound of Section 4. Same order (O0),
  same pruning rules, same certified archive.
- Recorded: full evaluations, expanded states, bound calls, wall-clock (median of
  three), non-evaluation overhead, front size, front equality with G0.
- A regime with an empty feasible set is reported as such.

E21, retry model (Section 4.6).
- Scales S1, S2, S3; the three workloads: 9 combinations.
- Configurations, all with the retry evaluator and the retry-certified archive:
  R0 exhaustive; R1 generic partial cost (G1c) at the exogenous rate (the retry
  amplification is determined only by a complete design, so the generic bound
  sees it as zero); R2 the term-wise bound of Section 4.2 at the exogenous rate,
  without the fixed point; R3 the bound of Proposition 5 (the published E15
  configuration).
- Both R1 and R2 are admissible for the retry model because every term is
  non-decreasing in the rate and the effective rate is at least the exogenous one.
- Recorded as in E20.

Analysis, fixed in advance. Report counts per combination and the ranges of
G2/G1c (E20) and R3/R1, R3/R2 (E21) for full evaluations and expanded states.
Every exact configuration must return the exhaustive front. Results are reported
whatever their direction.
