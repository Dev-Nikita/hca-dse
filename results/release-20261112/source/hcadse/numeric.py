"""Exact decimal policy for configured monetary quantities.

Costs and budgets are decimal input data.  Computing them through binary64 can turn an
inclusive equality such as 60 <= 60 into 60.00000000000001 > 60.  We therefore perform
monetary sums and feasibility comparisons in Decimal constructed from the source-facing
decimal strings.  The public objective remains a float for compatibility.
"""
from decimal import Decimal


def decimal_value(value) -> Decimal:
    return Decimal(str(value))


def deployment_cost_decimal(n_e, edge_cost, n_g, gateway_cost, link_cost,
                            cloud_cost) -> Decimal:
    link = decimal_value(link_cost)
    return (Decimal(n_e) * (decimal_value(edge_cost) + link) +
            Decimal(n_g) * (decimal_value(gateway_cost) + link) +
            decimal_value(cloud_cost))


def exceeds_decimal_limit(value: Decimal, limit) -> bool:
    return value > decimal_value(limit)
