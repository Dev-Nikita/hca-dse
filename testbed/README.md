# Containerised testbed

Requires Docker. From the repository root:

```bash
python3 testbed/select_designs.py           # 36 architectures (Pareto, dominated, boundary)
python3 testbed/run_testbed.py --repeats 3  # 40-60 min, appends to results/e9_testbed.csv
python3 testbed/analyze.py                  # error and rank-agreement summaries
```

A run can be interrupted; `run_testbed.py` appends to its CSV and skips completed
(design, repeat) pairs.

Each edge, gateway and cloud node is a separate container with one CPU, matching the
single-server stage of the model. A stage performs CPU work equal to w/C, payloads are
sent over the network, and `tc netem` applies the delay and bandwidth of the link class;
the WAN link to the cloud is 20 ms / 200 Mbit/s. Only configurations that fit on one
host (at most 4 edge, 2 gateway and 1 cloud node) are covered.

The node and load-generator binaries are built from `cmd/` by the `Dockerfile`.
