"""Generate the deterministic customer-orders sample used by the RFM demo.

The data is synthetic. Customer behaviour is deliberately varied so the
dashboard has recent, loyal, lapsing, and low-value customers to distinguish.
Run this file from the repository root to reproduce the committed CSV.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT = Path(__file__).resolve().parents[1] / "samples" / "customer-orders.csv"
END_DATE = pd.Timestamp("2025-12-30")

# These are data-generation personas, not the final RFM labels. The RFM engine
# derives its labels independently from the resulting customer percentiles.
PERSONAS = {
    "frequent_recent": (52, (3, 35), (12, 20), (1.25, 2.00), 420),
    "steady_repeat": (58, (35, 120), (9, 16), (0.85, 1.35), 400),
    "growing": (55, (2, 50), (3, 7), (0.75, 1.25), 180),
    "first_purchase": (35, (1, 30), (1, 1), (0.70, 1.20), 1),
    "lapsed_high_value": (50, (190, 360), (8, 15), (1.10, 1.80), 420),
    "inactive_low_value": (45, (280, 620), (1, 3), (0.45, 0.85), 220),
    "cooling": (35, (100, 230), (4, 8), (0.65, 1.05), 300),
}

PRODUCTS = np.array(["Starter Kit", "Everyday Set", "Premium Set", "Refill Pack"])
PRICES = np.array([48.0, 92.0, 185.0, 32.0])
CATEGORIES = np.array(["Starter", "Core", "Premium", "Consumables"])
REGIONS = np.array(["Hong Kong", "Kowloon", "New Territories", "International"])
CHANNELS = np.array(["Website", "Marketplace", "Mobile App"])


def make_customer_orders(seed: int = 2026) -> pd.DataFrame:
    """Return reproducible order-level ecommerce data with repeat customers."""

    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    customer_number = 0
    order_number = 100_000

    for persona, (count, recency, frequency, spend, history_days) in PERSONAS.items():
        for _ in range(count):
            customer_number += 1
            customer_id = f"CUS-{customer_number:04d}"
            region = str(rng.choice(REGIONS, p=[0.30, 0.27, 0.31, 0.12]))
            last_purchase = END_DATE - timedelta(days=int(rng.integers(recency[0], recency[1] + 1)))
            order_count = int(rng.integers(frequency[0], frequency[1] + 1))
            value_multiplier = float(rng.uniform(spend[0], spend[1]))

            if order_count == 1:
                dates = [last_purchase]
            else:
                offsets = rng.integers(1, history_days + 1, size=order_count - 1)
                dates = sorted([last_purchase, *(last_purchase - pd.to_timedelta(offsets, unit="D"))])

            for order_date in dates:
                order_number += 1
                product_index = int(rng.choice(len(PRODUCTS), p=[0.25, 0.38, 0.16, 0.21]))
                units = int(rng.integers(1, 5))
                revenue = PRICES[product_index] * units * value_multiplier * rng.normal(1.0, 0.08)
                rows.append(
                    {
                        "Order Date": order_date.date().isoformat(),
                        "Order ID": f"ORD-{order_number}",
                        "Customer ID": customer_id,
                        "Product": PRODUCTS[product_index],
                        "Category": CATEGORIES[product_index],
                        "Region": region,
                        "Channel": str(rng.choice(CHANNELS, p=[0.51, 0.29, 0.20])),
                        "Units": units,
                        "Revenue": round(float(revenue), 2),
                        "Generation Persona": persona,
                    }
                )

                # A small return rate exercises negative-value handling without
                # making the sample's main business story about data cleaning.
                if rng.random() < 0.045:
                    order_number += 1
                    rows.append(
                        {
                            "Order Date": (order_date + timedelta(days=7)).date().isoformat(),
                            "Order ID": f"RET-{order_number}",
                            "Customer ID": customer_id,
                            "Product": PRODUCTS[product_index],
                            "Category": CATEGORIES[product_index],
                            "Region": region,
                            "Channel": "Return",
                            "Units": -1,
                            "Revenue": round(float(-revenue / units), 2),
                            "Generation Persona": persona,
                        }
                    )

    return pd.DataFrame(rows).sort_values(["Order Date", "Order ID"], ignore_index=True)


if __name__ == "__main__":
    data = make_customer_orders()
    data.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(data):,} rows for {data['Customer ID'].nunique():,} customers to {OUTPUT}")
