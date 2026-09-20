import unittest

import pandas as pd

from cohort import CohortCalculationError, calculate_cohort_retention, weighted_retention


class CohortRetentionTests(unittest.TestCase):
    def test_calculates_monthly_cohorts_and_distinguishes_zero_from_future(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "B", "C", "C"],
                "Date": ["2026-01-03", "2026-02-04", "2026-01-15", "2026-02-07", "2026-03-02"],
            }
        )

        result = calculate_cohort_retention(
            frame, customer_column="Customer", date_column="Date"
        )

        january = pd.Timestamp("2026-01-01")
        february = pd.Timestamp("2026-02-01")
        self.assertEqual(result.cohort_sizes.loc[january], 2)
        self.assertEqual(result.counts.loc[january, 1], 1)
        self.assertEqual(result.retention.loc[january, 1], 0.5)
        self.assertEqual(result.counts.loc[january, 2], 0)
        self.assertEqual(result.retention.loc[february, 1], 1.0)
        self.assertTrue(pd.isna(result.retention.loc[february, 2]))
        self.assertEqual(result.observation_end, pd.Timestamp("2026-03-01"))

    def test_customer_counts_once_per_activity_month(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "A"],
                "Date": ["2026-01-01", "2026-01-20", "2026-02-01"],
            }
        )

        result = calculate_cohort_retention(
            frame, customer_column="Customer", date_column="Date"
        )

        self.assertEqual(result.counts.iloc[0, 0], 1)
        self.assertEqual(result.counts.iloc[0, 1], 1)

    def test_overall_retention_is_weighted_by_eligible_cohort_size(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "B", "C", "C"],
                "Date": ["2026-01-03", "2026-02-04", "2026-01-15", "2026-02-07", "2026-03-02"],
            }
        )
        result = calculate_cohort_retention(
            frame, customer_column="Customer", date_column="Date"
        )

        # January contributes 1 retained customer from a base of 2; February
        # contributes 1 from 1. Weighted retention is 2/3, not (50%+100%)/2.
        self.assertAlmostEqual(weighted_retention(result, 1), 2 / 3)
        self.assertIsNone(weighted_retention(result, 99))

    def test_order_lines_are_netted_and_returns_do_not_create_activity(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "A", "A"],
                "Date": ["2026-01-02", "2026-01-02", "2026-02-03", "2026-03-03"],
                "Order": ["O1", "O1", "O2", "R1"],
                "Amount": [80, 20, 50, -25],
            }
        )

        result = calculate_cohort_retention(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
            order_column="Order",
        )

        self.assertEqual(result.counts.iloc[0, 0], 1)
        self.assertEqual(result.counts.iloc[0, 1], 1)
        self.assertEqual(result.counts.iloc[0, 2], 0)

    def test_quality_report_tracks_invalid_rows_and_missing_order_ids(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", None, "B", "C"],
                "Date": ["2026-01-01", "2026-01-02", "bad", "2026-02-01"],
                "Order": [None, "O2", "O3", "O4"],
                "Amount": [10, 20, 30, "bad"],
            }
        )

        result = calculate_cohort_retention(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
            order_column="Order",
        )

        self.assertEqual(result.quality.input_rows, 4)
        self.assertEqual(result.quality.rows_used, 1)
        self.assertEqual(result.quality.dropped_rows, 3)
        self.assertEqual(result.quality.missing_customer_rows, 1)
        self.assertEqual(result.quality.invalid_date_rows, 1)
        self.assertEqual(result.quality.invalid_monetary_rows, 1)
        self.assertEqual(result.quality.missing_order_id_rows, 1)

    def test_invalid_configuration_has_clear_errors(self):
        frame = pd.DataFrame({"Customer": ["A"], "Date": ["2026-01-01"]})

        with self.assertRaisesRegex(CohortCalculationError, "missing"):
            calculate_cohort_retention(
                frame, customer_column="Missing", date_column="Date"
            )
        with self.assertRaisesRegex(CohortCalculationError, "different column"):
            calculate_cohort_retention(
                frame, customer_column="Customer", date_column="Customer"
            )

    def test_input_dataframe_is_not_modified(self):
        frame = pd.DataFrame({"Customer": ["A"], "Date": ["2026-01-01"]})
        original = frame.copy(deep=True)

        calculate_cohort_retention(frame, customer_column="Customer", date_column="Date")

        pd.testing.assert_frame_equal(frame, original)


if __name__ == "__main__":
    unittest.main()
