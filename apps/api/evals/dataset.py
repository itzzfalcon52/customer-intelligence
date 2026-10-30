"""Seeded synthetic B2B SaaS account data. Clearly synthetic: used only for evaluation."""

import csv
import io

import numpy as np

FEATURES = [
    "plan",
    "billing_cycle",
    "seats",
    "active_users_30d",
    "login_change_pct",
    "support_tickets_90d",
    "failed_payments_90d",
    "nps",
    "mrr",
]


def saas_accounts_csv(rows: int = 1200, seed: int = 7) -> str:
    rng = np.random.default_rng(seed)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["account_id", *FEATURES, "cancellation_reason", "churned"])
    for index in range(rows):
        plan = str(rng.choice(["Starter", "Growth", "Enterprise"], p=[0.5, 0.35, 0.15]))
        billing = str(rng.choice(["monthly", "annual"], p=[0.6, 0.4]))
        seats = int(rng.integers(3, 40) * {"Starter": 1, "Growth": 3, "Enterprise": 10}[plan])
        utilization = float(rng.beta(4, 2))
        active = max(0, round(seats * utilization))
        login_change = float(np.round(rng.normal(0, 25), 1))
        tickets = int(rng.poisson(2))
        failed = int(rng.choice([0, 0, 0, 0, 1, 2]))
        nps = "" if rng.random() < 0.18 else int(rng.integers(0, 11))
        mrr = float(np.round(seats * {"Starter": 12, "Growth": 25, "Enterprise": 40}[plan], 2))
        logit = (
            -1.2
            - 3.0 * (utilization - 0.6)
            - 0.03 * login_change
            + 0.25 * tickets
            + 0.8 * failed
            + (0.7 if billing == "monthly" else -0.6)
            + (0.0 if nps == "" else -0.12 * (int(nps) - 6))
        )
        churned = rng.random() < 1 / (1 + np.exp(-logit))
        # Recorded only after cancellation: a deliberate leakage trap for the evals.
        reason = (
            rng.choice(["price", "missing feature", "switched vendor", "budget cut"])
            if churned
            else ""
        )
        writer.writerow(
            [
                f"ACC-{index:05}",
                plan,
                billing,
                seats,
                active,
                login_change,
                tickets,
                failed,
                nps,
                mrr,
                reason,
                "Yes" if churned else "No",
            ]
        )
    return output.getvalue()
