# Sample datasets

Four synthetic files for trying ADA without uploading anything of your own.
They are generated, not real business data, so they carry no privacy or
licensing baggage — use them freely in demos, issues and tests.

Each one is shaped to exercise a different part of the analysis.

| File | Rows | Shape | What it shows |
|---|---|---|---|
| `saas-subscriptions.csv` | 216 | Monthly MRR by plan and region | A deliberate revenue drop in April 2025 that anomaly detection finds, and a forecast that beats no-change |
| `support-tickets.csv` | 2,400 | Operational tickets by team and priority | A dataset with no money column, and a forecast honest enough to say it is no better than assuming no change |
| `ecommerce-orders.csv` | 4,000 | Orders by category and channel | Returns as negative rows, so totals and shares have to cope with mixed signs |
| `customer-orders.csv` | 2,899 | Repeat-customer ecommerce orders | Customer-level RFM segments, including loyal, new, at-risk, and inactive behaviour |

## Things worth trying

**`saas-subscriptions.csv`**
- The anomaly radar should flag **April 2025**. The drop is real and planted.
- Ask: *"which plan grew fastest?"* and *"MRR by region"*
- The forecast reports MASE 0.40 — comfortably better than assuming no change.

**`support-tickets.csv`**
- ADA picks `Resolution Hours` as the metric because there is no revenue column.
- The forecast reports MASE above 1 and says so. That refusal is the point.
- Ask: *"average resolution hours by team"* and *"how many tickets?"*

**`ecommerce-orders.csv`**
- About 7% of rows are returns, carrying negative units and revenue.
- Ask: *"top 5 categories by revenue"* and *"which channel declined most?"*

**`customer-orders.csv`**
- Open **Customer segments**; the four RFM fields are detected automatically.
- Compare segment size and value, then download the customer-level result.
- The `Generation Persona` column is ground truth for explaining how this synthetic sample was shaped; the RFM labels are still calculated independently.

## Regenerating

These files are committed so they can be downloaded straight from GitHub. The
customer-orders sample can be reproduced with
`python tools/generate_customer_orders.py`; the other three predate that script
and remain committed as their version of record. `demo_data.py` shows the same
fixed-seed approach used by the built-in demo.
