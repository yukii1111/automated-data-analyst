"""Deterministic monthly cohort-retention analysis for transaction data."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


class CohortCalculationError(ValueError):
    """Raised when the selected columns cannot produce a cohort table."""


@dataclass(frozen=True)
class CohortQualityReport:
    """Counts explaining which source rows reached the cohort calculation."""

    input_rows: int
    rows_used: int
    dropped_rows: int
    missing_customer_rows: int
    invalid_date_rows: int
    invalid_monetary_rows: int
    missing_order_id_rows: int


@dataclass(frozen=True)
class CohortResult:
    """Monthly customer counts and retention rates by acquisition cohort."""

    counts: pd.DataFrame
    retention: pd.DataFrame
    cohort_sizes: pd.Series
    observation_end: pd.Timestamp
    customer_column: str
    date_column: str
    monetary_column: str | None
    order_column: str | None
    quality: CohortQualityReport


@dataclass(frozen=True)
class CohortInsight:
    """One decision-friendly cohort signal with its calculation exposed."""

    title: str
    value: str
    statement: str
    calculation: str
    tone: str = "neutral"


def weighted_retention(result: CohortResult, month: int) -> float | None:
    """Return size-weighted retention for cohorts old enough to observe a month."""

    if month < 0 or month not in result.counts.columns:
        return None
    observed = result.counts[month].notna()
    if not observed.any():
        return None
    eligible_sizes = result.cohort_sizes.loc[observed]
    denominator = int(eligible_sizes.sum())
    if denominator == 0:
        return None
    return float(result.counts.loc[observed, month].sum() / denominator)


def build_cohort_insights(
    result: CohortResult, *, minimum_cohort_size: int = 5
) -> tuple[CohortInsight, ...]:
    """Summarize scale and retention without promoting tiny cohorts as winners."""

    insights: list[CohortInsight] = []
    total_customers = int(result.cohort_sizes.sum())
    largest_month = result.cohort_sizes.idxmax()
    largest_size = int(result.cohort_sizes.loc[largest_month])
    insights.append(
        CohortInsight(
            title="Largest acquisition cohort",
            value=f"{largest_size:,}",
            statement=(
                f"{largest_month:%b %Y} acquired {largest_size:,} customers, "
                f"{largest_size / total_customers:.1%} of all acquired customers."
            ),
            calculation="Largest Month 0 cohort size ÷ total acquired customers",
        )
    )

    month_one = weighted_retention(result, 1)
    if month_one is not None:
        observed = result.counts[1].notna()
        retained = int(result.counts.loc[observed, 1].sum())
        eligible = int(result.cohort_sizes.loc[observed].sum())
        insights.append(
            CohortInsight(
                title="Month 1 retention baseline",
                value=f"{month_one:.1%}",
                statement=(
                    f"{retained:,} of {eligible:,} customers returned one month after "
                    "their first purchase."
                ),
                calculation="Month 1 returning customers ÷ eligible acquired customers",
            )
        )

        reliable = observed & result.cohort_sizes.ge(minimum_cohort_size)
        reliable_months = result.cohort_sizes.index[reliable]
        if len(reliable_months) >= 2:
            latest_month = reliable_months.max()
            earlier_months = reliable_months[reliable_months != latest_month]
            latest_size = int(result.cohort_sizes.loc[latest_month])
            latest_retained = int(result.counts.loc[latest_month, 1])
            latest_rate = latest_retained / latest_size
            prior_size = int(result.cohort_sizes.loc[earlier_months].sum())
            prior_retained = int(result.counts.loc[earlier_months, 1].sum())
            prior_rate = prior_retained / prior_size
            difference = (latest_rate - prior_rate) * 100
            direction = "above" if difference >= 0 else "below"
            insights.append(
                CohortInsight(
                    title="Latest reliable cohort",
                    value=f"{difference:+.1f} pp",
                    statement=(
                        f"{latest_month:%b %Y} retained {latest_retained:,} of "
                        f"{latest_size:,} customers at Month 1 ({latest_rate:.1%}), "
                        f"{abs(difference):.1f} points {direction} the earlier reliable-cohort baseline."
                    ),
                    calculation=(
                        f"Latest Month 1 rate − weighted prior rate; cohorts require n ≥ "
                        f"{minimum_cohort_size}"
                    ),
                    tone="positive" if difference >= 0 else "negative",
                )
            )

    if 3 in result.retention.columns:
        reliable_three = result.retention[3].notna() & result.cohort_sizes.ge(
            minimum_cohort_size
        )
        if reliable_three.any():
            rates = result.retention.loc[reliable_three, 3]
            best_month = rates.idxmax()
            best_size = int(result.cohort_sizes.loc[best_month])
            best_retained = int(result.counts.loc[best_month, 3])
            best_rate = float(rates.loc[best_month])
            insights.append(
                CohortInsight(
                    title="Strongest Month 3 cohort",
                    value=f"{best_rate:.1%}",
                    statement=(
                        f"{best_month:%b %Y} had {best_retained:,} of {best_size:,} customers "
                        "purchase again in Month 3."
                    ),
                    calculation=(
                        f"Highest observed Month 3 rate among cohorts with n ≥ "
                        f"{minimum_cohort_size}"
                    ),
                    tone="positive",
                )
            )

    return tuple(insights)


def _require_columns(
    dataframe: pd.DataFrame,
    *,
    customer_column: str,
    date_column: str,
    monetary_column: str | None,
    order_column: str | None,
) -> None:
    selected = [customer_column, date_column]
    selected.extend(column for column in (monetary_column, order_column) if column is not None)
    missing = [column for column in selected if column not in dataframe.columns]
    if missing:
        raise CohortCalculationError(f"Selected cohort columns are missing: {', '.join(missing)}")
    if len(set(selected)) != len(selected):
        raise CohortCalculationError("Each cohort role must use a different column.")


def _month_distance(later: pd.Series, earlier: pd.Series) -> pd.Series:
    return (later.dt.year - earlier.dt.year) * 12 + later.dt.month - earlier.dt.month


def calculate_cohort_retention(
    dataframe: pd.DataFrame,
    *,
    customer_column: str,
    date_column: str,
    monetary_column: str | None = None,
    order_column: str | None = None,
) -> CohortResult:
    """Calculate monthly logo retention from valid positive purchase activity.

    A customer's cohort is the month of their first valid purchase. Each later
    month counts that customer at most once. When monetary value is supplied,
    returns are excluded; with an order identifier, line items are netted at
    order level before deciding whether the order is a purchase.
    """

    _require_columns(
        dataframe,
        customer_column=customer_column,
        date_column=date_column,
        monetary_column=monetary_column,
        order_column=order_column,
    )
    if dataframe.empty:
        raise CohortCalculationError("Cohort analysis needs at least one transaction row.")

    selected = [customer_column, date_column]
    selected.extend(column for column in (monetary_column, order_column) if column is not None)
    working = dataframe.loc[:, selected].copy()
    working["_customer"] = working[customer_column].astype("string").str.strip()
    working["_customer"] = working["_customer"].mask(working["_customer"].eq(""))
    parsed_dates = pd.to_datetime(working[date_column], errors="coerce", utc=True)
    working["_date"] = parsed_dates.dt.tz_convert(None)

    missing_customer = working["_customer"].isna()
    invalid_date = working["_date"].isna()
    invalid_monetary = pd.Series(False, index=working.index)
    if monetary_column is not None:
        working["_monetary"] = pd.to_numeric(working[monetary_column], errors="coerce")
        working["_monetary"] = working["_monetary"].replace([np.inf, -np.inf], np.nan)
        invalid_monetary = working["_monetary"].isna()

    usable = ~(missing_customer | invalid_date | invalid_monetary)
    transactions = working.loc[usable].copy()
    if transactions.empty:
        raise CohortCalculationError("No rows have a valid customer, date, and monetary value.")

    missing_order_id_rows = 0
    if order_column is not None:
        order_ids = transactions[order_column].astype("string").str.strip()
        missing_order_ids = order_ids.isna() | order_ids.eq("")
        missing_order_id_rows = int(missing_order_ids.sum())
        fallback_ids = pd.Series(
            [f"row:{index}" for index in transactions.index],
            index=transactions.index,
            dtype="string",
        )
        transactions["_order"] = ("id:" + order_ids).where(
            ~missing_order_ids, fallback_ids
        )
        aggregation: dict[str, tuple[str, str]] = {"_date": ("_date", "max")}
        if monetary_column is not None:
            aggregation["_order_value"] = ("_monetary", "sum")
        activity = transactions.groupby(
            ["_customer", "_order"], as_index=False, sort=False
        ).agg(**aggregation)
        if monetary_column is not None:
            activity = activity.loc[activity["_order_value"] > 0]
    else:
        activity = transactions
        if monetary_column is not None:
            activity = activity.loc[activity["_monetary"] > 0]

    if activity.empty:
        raise CohortCalculationError("No positive purchases remain after returns are removed.")

    activity = activity.loc[:, ["_customer", "_date"]].copy()
    activity["Activity month"] = activity["_date"].dt.to_period("M").dt.to_timestamp()
    activity = activity.drop_duplicates(["_customer", "Activity month"])
    first_purchase = activity.groupby("_customer")["Activity month"].min().rename("Cohort month")
    activity = activity.join(first_purchase, on="_customer")
    activity["Cohort index"] = _month_distance(
        activity["Activity month"], activity["Cohort month"]
    ).astype(int)

    observed_counts = (
        activity.groupby(["Cohort month", "Cohort index"])["_customer"]
        .nunique()
        .unstack()
    )
    # A returns-only month still proves the dataset was observed through that
    # month. It extends the measurement window without counting as retention.
    observation_end = transactions["_date"].max().to_period("M").to_timestamp()
    maximum_age = int(
        (observation_end.year - observed_counts.index.min().year) * 12
        + observation_end.month
        - observed_counts.index.min().month
    )
    counts = observed_counts.reindex(columns=range(maximum_age + 1))
    for cohort_month in counts.index:
        observable_age = int(
            (observation_end.year - cohort_month.year) * 12
            + observation_end.month
            - cohort_month.month
        )
        counts.loc[cohort_month, :observable_age] = counts.loc[
            cohort_month, :observable_age
        ].fillna(0)
    counts = counts.astype("Int64")
    counts.index.name = "Cohort month"
    counts.columns.name = "Months since first purchase"
    cohort_sizes = counts[0].astype("int64").rename("Cohort size")
    retention = counts.div(cohort_sizes, axis=0).astype("Float64")

    quality = CohortQualityReport(
        input_rows=len(dataframe),
        rows_used=len(transactions),
        dropped_rows=int((~usable).sum()),
        missing_customer_rows=int(missing_customer.sum()),
        invalid_date_rows=int(invalid_date.sum()),
        invalid_monetary_rows=int(invalid_monetary.sum()),
        missing_order_id_rows=missing_order_id_rows,
    )
    return CohortResult(
        counts=counts,
        retention=retention,
        cohort_sizes=cohort_sizes,
        observation_end=observation_end,
        customer_column=customer_column,
        date_column=date_column,
        monetary_column=monetary_column,
        order_column=order_column,
        quality=quality,
    )
