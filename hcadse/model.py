"""Formal model of the heterogeneous edge-cloud CPS design space (Gate 1)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import itertools

# ----------------------------------------------------------------------------
# Resource classes
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeClass:
    name: str
    C: float      # compute capacity [MIPS]
    M: float      # memory [MB]
    P_idle: float # idle power [W]
    P_peak: float # peak power [W]
    cost: float   # normalized deployment+runtime cost units per node

@dataclass(frozen=True)
class LinkClass:
    name: str
    B: float      # bandwidth [Mb/s]
    prop: float   # propagation delay [s]
    e: float      # energy per transferred MB [J/MB]
    cost: float   # cost units per attached node

# WAN (gateway->cloud) is fixed infrastructure, not a design variable
WAN_B = 200.0      # Mb/s
WAN_PROP = 0.020   # s
WAN_E = 0.06       # J/MB

EDGE_CLASSES = [
    NodeClass("edge-low",  C=2000.0,  M=2048.0,  P_idle=4.0,  P_peak=12.0, cost=1.0),
    NodeClass("edge-med",  C=6000.0,  M=8192.0,  P_idle=8.0,  P_peak=30.0, cost=2.4),
    NodeClass("edge-high", C=15000.0, M=16384.0, P_idle=15.0, P_peak=65.0, cost=5.2),
]
GW_CLASSES = [
    NodeClass("gw-low",  C=4000.0,  M=4096.0,  P_idle=6.0,  P_peak=20.0, cost=1.8),
    NodeClass("gw-high", C=12000.0, M=16384.0, P_idle=12.0, P_peak=48.0, cost=4.0),
]
CLOUD_CLASSES = [
    NodeClass("cloud-med",  C=40000.0,  M=131072.0, P_idle=0.0, P_peak=180.0, cost=6.0),
    NodeClass("cloud-high", C=100000.0, M=262144.0, P_idle=0.0, P_peak=380.0, cost=12.0),
]
LINK_CLASSES = [
    LinkClass("constrained", B=10.0,   prop=0.004, e=0.30, cost=0.2),
    LinkClass("standard",    B=100.0,  prop=0.002, e=0.12, cost=0.6),
    LinkClass("fast",        B=1000.0, prop=0.001, e=0.05, cost=1.4),
]

# Placement policies: tier of stage 1 (pre-processing) and stage 3 (analytics).
# Stage 2 (aggregation) is always executed on gateways.
POLICIES = {
    "edge-first":  ("edge", "edge"),
    "balanced":    ("edge", "cloud"),
    "cloud-first": ("gw",   "cloud"),
}

# ----------------------------------------------------------------------------
# Workload
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Stage:
    name: str
    w: float      # computational work per request [MI]
    mem: float    # resident memory [MB]
    s_in: float   # payload arriving at this stage [MB]

@dataclass(frozen=True)
class Workload:
    name: str
    n_dev: int
    rate: float             # per-device request rate [1/s]
    stages: Tuple[Stage, Stage, Stage]
    deadline: float         # end-to-end deadline [s]
    s_sync: float           # per-request replica synchronisation payload [MB]
    horizon: float = 3600.0 # energy accounting horizon [s]
    C_max: float = 60.0     # cost budget [units]
    E_max: float = 4.0e6    # energy budget [J]
    rho_max: float = 0.85   # max admissible utilisation

    @property
    def Lambda(self) -> float:
        return self.n_dev * self.rate

WORKLOADS = {
    "telemetry": Workload(
        name="telemetry", n_dev=200, rate=2.0,
        stages=(Stage("preprocess", 8.0, 64.0, 0.02),
                Stage("aggregate",  4.0, 48.0, 0.01),
                Stage("analytics", 20.0, 256.0, 0.01)),
        deadline=0.120, s_sync=0.004),
    "control": Workload(
        name="control", n_dev=60, rate=10.0,
        stages=(Stage("preprocess", 5.0, 48.0, 0.005),
                Stage("aggregate",  3.0, 32.0, 0.004),
                Stage("analytics",  9.0, 96.0, 0.003)),
        deadline=0.030, s_sync=0.002),
    "sensing": Workload(
        name="sensing", n_dev=40, rate=1.5,
        stages=(Stage("preprocess", 120.0, 512.0, 1.20),
                Stage("aggregate",   30.0, 256.0, 0.35),
                Stage("analytics",  260.0, 2048.0, 0.30)),
        deadline=0.900, s_sync=0.10, C_max=90.0),
}

# ----------------------------------------------------------------------------
# Design space
# ----------------------------------------------------------------------------

# Canonical traversal order: the determinants of tier utilisation (node counts, node
# classes, replication factor and placement policy) are assigned before the remaining
# variables, so that the contention-dependent waiting term becomes exactly computable on
# incomplete designs (Lemma "exactness on determined terms").
VAR_ORDER = ["n_e", "edge_cls", "n_g", "gw_cls", "rep", "policy", "link_cls", "cloud_cls"]

# Alternative order used only as a comparison point in the order ablation: the utilisation
# determinants `rep` and `policy` are assigned last, so the waiting term stays relaxed to
# zero on every incomplete design.
ORDER_DETERMINANTS_LAST = ["n_e", "edge_cls", "n_g", "gw_cls", "link_cls", "cloud_cls",
                           "rep", "policy"]

@dataclass
class DesignSpace:
    """Cartesian design space; variables are explored in VAR_ORDER."""
    n_e: List[int]
    edge_cls: List[NodeClass]
    n_g: List[int]
    gw_cls: List[NodeClass]
    link_cls: List[LinkClass]
    cloud_cls: List[NodeClass]
    rep: List[int]
    policy: List[str]

    def domain(self, var: str) -> List:
        return getattr(self, var)

    @property
    def size(self) -> int:
        n = 1
        for v in VAR_ORDER:
            n *= len(self.domain(v))
        return n

    def enumerate(self):
        for combo in itertools.product(*[self.domain(v) for v in VAR_ORDER]):
            yield dict(zip(VAR_ORDER, combo))


def make_space(scale: str) -> DesignSpace:
    """Four design-space scales S1..S4."""
    if scale == "S1":
        return DesignSpace([2, 4, 8], EDGE_CLASSES, [1, 2], GW_CLASSES,
                           LINK_CLASSES, CLOUD_CLASSES, [1, 2], list(POLICIES))
    if scale == "S2":
        return DesignSpace([2, 3, 4, 6, 8, 12], EDGE_CLASSES, [1, 2, 4], GW_CLASSES,
                           LINK_CLASSES, CLOUD_CLASSES, [1, 2, 3], list(POLICIES))
    if scale == "S3":
        return DesignSpace(list(range(2, 26)), EDGE_CLASSES, [1, 2, 4, 6, 8], GW_CLASSES,
                           LINK_CLASSES, CLOUD_CLASSES, [1, 2, 3, 4], list(POLICIES))
    if scale == "S4":
        return DesignSpace(list(range(2, 82)), EDGE_CLASSES, [1, 2, 3, 4, 6, 8, 12, 16],
                           GW_CLASSES, LINK_CLASSES, CLOUD_CLASSES, [1, 2, 3, 4, 5],
                           list(POLICIES))
    raise ValueError(scale)
