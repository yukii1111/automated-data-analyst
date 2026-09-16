"""Deterministic customer segmentation with recency, frequency, and monetary value.

The web application is deliberately kept out of this module.  RFM is a business
calculation, so it should be possible to verify it with a dataframe and reuse it
from a UI, a notebook, or a future API without importing Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


class RFMCalculationError(ValueError):
    """Raised when the selected columns cannot produce a meaningful RFM table."""


@dataclass(frozen=True)
class RFMQualityReport:
    """Counts that explain which input rows and customers reached the result."""

    input_rows: int
    rows_used: int
    dropped_rows: int
    missing_customer_rows: int
    invalid_date_rows: int
    invalid_monetary_rows: int
    missing_order_id_rows: int
    customers_excluded_without_purchase: int


@dataclass(frozen=True)
class RFMResult:
    """Customer-level RFM output plus the assumptions needed to interpret it."""

    customers: pd.DataFrame
    analysis_date: pd.Timestamp
    customer_column: str
    date_column: str
    monetary_column: str
    order_column: str | None
    quality: RFMQualityReport


def _require_columns(
    dataframe: pd.DataFrame,
    *,
    customer_column: str,
    date_column: str,
    monetary_column: str,
    order_column: str | None,
) -> None:
    selected = [customer_column, date_column, monetary_column]
    if order_column is not None:
        selected.append(order_column)

    missing = [column for column in selected if column not in dataframe.columns]
    if missing:
        raise RFMCalculationError(f"Selected RFM columns are missing: {', '.join(missing)}")
    if len(set(selected)) != len(selected):
        raise RFMCalculationError("Each RFM role must use a different column.")


def _clean_customer_ids(series: pd.Series) -> pd.Series:
    customers = series.astype("string").str.strip()
    return customers.mask(customers.eq(""))


def _clean_dates(series: pd.Series) -> pd.Series:
    # UTC parsing makes timezone-aware and timezone-naive uploads comparable.
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed.dt.tz_convert(None)


def _score(values: pd.Series, *, higher_is_better: bool) -> pd.Series:
    """Return robust 1-5 percentile scores, including for small or tied samples."""

    if values.empty:
        return pd.Series(dtype="int64", index=values.index)
    percentiles = values.rank(method="average", pct=True, ascending=higher_is_better)
    return np.ceil(percentiles * 5).clip(1, 5).astype("int64")


def _segment_customer(row: pd.Series) -> str:
    """Assign one mutually exclusive segment using an explicit priority order."""

    recency = int(row["R Score"])
    frequency = int(row["F Score"])
    monetary = int(row["M Score"])

    if recency >= 4 and frequency >= 4 and monetary >= 4:
        return "Champions"
    if recency <= 2 and (frequency >= 3 or monetary >= 3):
        return "At Risk"
    if recency >= 3 and frequency >= 4:
        return "Loyal Customers"
    if recency >= 4 and frequency == 1:
        return "New Customers"
    if recency >= 4 and frequency in {2, 3}:
        return "Potential Loyalists"
    if recency <= 2 and frequency <= 2 and monetary <= 2:
        return "Lost Customers"
    if recency <= 3 and (frequency >= 2 or monetary >= 2):
        return "Needs Attention"
    return "Others"


def calculate_rfm(
    dataframe: pd.DataFrame,
    *,
    customer_column: str,
    date_column: str,
    monetary_column: str,
    order_column: str | None = None,
    analysis_date: str | pd.Timestamp | None = None,
) -> RFMResult:
    """Build a customer-level RFM table from cleaned transaction data.

    Positive net orders count toward frequency and define the latest purchase.
    Negative rows still reduce monetary value, so returns are not silently lost.
    Without an order identifier, each positive row is treated as one transaction.
    The default analysis date is one day after the latest valid purchase, which
    makes the result reproducible instead of depending on the day it is opened.
    """

    _require_columns(
        dataframe,
        customer_column=customer_column,
        date_column=date_column,
        monetary_column=monetary_column,
        order_column=order_column,
    )
    if dataframe.empty:
        raise RFMCalculationError("RFM analysis needs at least one transaction row.")

    selected = [customer_column, date_column, monetary_column]
    if order_column is not None:
        selected.append(order_column)
    working = dataframe.loc[:, selected].copy()
    working["_customer"] = _clean_customer_ids(working[customer_column])
    working["_date"] = _clean_dates(working[date_column])
    working["_monetary"] = pd.to_numeric(working[monetary_column], errors="coerce")
    working["_monetary"] = working["_monetary"].replace([np.inf, -np.inf], np.nan)

    missing_customer = working["_customer"].isna()
    invalid_date = working["_date"].isna()
    invalid_monetary = working["_monetary"].isna()
    usable = ~(missing_customer | invalid_date | invalid_monetary)
    transactions = working.loc[usable].copy()
    if transactions.empty:
        raise RFMCalculationError("No rows have a valid customer, date, and monetary value.")

    missing_order_id_rows = 0
    if order_column is not None:
        order_ids = transactions[order_column].astype("string").str.strip()
        missing_order_ids = order_ids.isna() | order_ids.eq("")
        missing_order_id_rows = int(missing_order_ids.sum())
        # A missing order ID should not collapse unrelated rows into one order.
        fallback_ids = pd.Series(
            [f"row:{index}" for index in transactions.index], index=transactions.index, dtype="string"
        )
        transactions["_order"] = ("id:" + order_ids).where(~missing_order_ids, fallback_ids)
        orders = (
            transactions.groupby(["_customer", "_order"], as_index=False, sort=False)
            .agg(_date=("_date", "max"), _order_value=("_monetary", "sum"))
        )
    else:
        orders = transactions.loc[:, ["_customer", "_date", "_monetary"]].rename(
            columns={"_monetary": "_order_value"}
        )

    purchases = orders.loc[orders["_order_value"] > 0].copy()
    if purchases.empty:
        raise RFMCalculationError("No positive purchases remain after returns are netted against orders.")

    latest_purchase = purchases["_date"].max().normalize()
    if analysis_date is None:
        effective_analysis_date = latest_purchase + pd.offsets.Day(1)
    else:
        parsed_analysis_date = pd.to_datetime(analysis_date, errors="coerce", utc=True)
        if pd.isna(parsed_analysis_date):
            raise RFMCalculationError("The analysis date is not a valid date.")
        effective_analysis_date = pd.Timestamp(parsed_analysis_date).tz_convert(None).normalize()
        if effective_analysis_date < latest_purchase:
            raise RFMCalculationError("The analysis date cannot be before the latest purchase.")

    activity = purchases.groupby("_customer", sort=True).agg(
        _last_purchase=("_date", "max"), Frequency=("_order_value", "size")
    )
    monetary = transactions.groupby("_customer", sort=True)["_monetary"].sum().rename("Monetary")
    customer_table = activity.join(monetary, how="left")
    customer_table["Recency"] = (
        effective_analysis_date - customer_table["_last_purchase"].dt.normalize()
    ).dt.days
    customer_table = customer_table.drop(columns="_last_purchase").reset_index()
    customer_table = customer_table.rename(columns={"_customer": customer_column})

    customer_table["R Score"] = _score(customer_table["Recency"], higher_is_better=False)
    customer_table["F Score"] = _score(customer_table["Frequency"], higher_is_better=True)
    customer_table["M Score"] = _score(customer_table["Monetary"], higher_is_better=True)
    customer_table["RFM Score"] = (
        customer_table["R Score"] + customer_table["F Score"] + customer_table["M Score"]
    )
    customer_table["RFM Code"] = (
        customer_table["R Score"].astype(str)
        + customer_table["F Score"].astype(str)
        + customer_table["M Score"].astype(str)
    )
    customer_table["Segment"] = customer_table.apply(_segment_customer, axis=1)
    customer_table = customer_table.sort_values(
        ["RFM Score", "Monetary", customer_column], ascending=[False, False, True]
    ).reset_index(drop=True)

    all_valid_customers = int(transactions["_customer"].nunique())
    quality = RFMQualityReport(
        input_rows=len(dataframe),
        rows_used=len(transactions),
        dropped_rows=int((~usable).sum()),
        missing_customer_rows=int(missing_customer.sum()),
        invalid_date_rows=int(invalid_date.sum()),
        invalid_monetary_rows=int(invalid_monetary.sum()),
        missing_order_id_rows=missing_order_id_rows,
        customers_excluded_without_purchase=all_valid_customers - len(customer_table),
    )
    return RFMResult(
        customers=customer_table,
        analysis_date=effective_analysis_date,
        customer_column=customer_column,
        date_column=date_column,
        monetary_column=monetary_column,
        order_column=order_column,
        quality=quality,
    )
