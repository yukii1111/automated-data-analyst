import unittest

import pandas as pd

from rfm import RFMCalculationError, build_segment_actions, calculate_rfm


class RFMCalculationTests(unittest.TestCase):
    def test_calculates_customer_metrics_and_reproducible_analysis_date(self):
        frame = pd.DataFrame(
            {
                "Customer ID": ["A", "A", "B"],
                "Order Date": ["2026-01-01", "2026-01-10", "2026-01-05"],
                "Order ID": ["A-1", "A-2", "B-1"],
                "Revenue": [100, 50, 80],
            }
        )

        result = calculate_rfm(
            frame,
            customer_column="Customer ID",
            date_column="Order Date",
            monetary_column="Revenue",
            order_column="Order ID",
        )
        customers = result.customers.set_index("Customer ID")

        self.assertEqual(result.analysis_date, pd.Timestamp("2026-01-11"))
        self.assertEqual(customers.loc["A", "Recency"], 1)
        self.assertEqual(customers.loc["A", "Frequency"], 2)
        self.assertEqual(customers.loc["A", "Monetary"], 150)
        self.assertEqual(customers.loc["B", "Recency"], 6)
        self.assertEqual(customers.loc["B", "Frequency"], 1)

    def test_multiple_lines_from_one_order_count_once(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "A"],
                "Date": ["2026-02-01", "2026-02-01", "2026-02-05"],
                "Order": ["O-1", "O-1", "O-2"],
                "Amount": [30, 20, 40],
            }
        )

        result = calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
            order_column="Order",
        )

        self.assertEqual(result.customers.loc[0, "Frequency"], 2)
        self.assertEqual(result.customers.loc[0, "Monetary"], 90)

    def test_returns_reduce_monetary_and_zero_net_orders_do_not_count(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "A"],
                "Date": ["2026-03-01", "2026-03-01", "2026-03-05"],
                "Order": ["O-1", "O-1", "O-2"],
                "Amount": [100, -100, 60],
            }
        )

        result = calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
            order_column="Order",
        )

        self.assertEqual(result.customers.loc[0, "Frequency"], 1)
        self.assertEqual(result.customers.loc[0, "Monetary"], 60)
        self.assertEqual(result.customers.loc[0, "Recency"], 1)

    def test_positive_rows_are_transactions_when_order_column_is_omitted(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "A"],
                "Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "Amount": [20, -5, 30],
            }
        )

        result = calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
        )

        self.assertEqual(result.customers.loc[0, "Frequency"], 2)
        self.assertEqual(result.customers.loc[0, "Monetary"], 45)

    def test_missing_order_ids_fall_back_to_separate_transactions(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A"],
                "Date": ["2026-01-01", "2026-01-02"],
                "Order": [None, ""],
                "Amount": [20, 30],
            }
        )

        result = calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
            order_column="Order",
        )

        self.assertEqual(result.customers.loc[0, "Frequency"], 2)
        self.assertEqual(result.quality.missing_order_id_rows, 2)

    def test_quality_report_explains_dropped_rows_and_excluded_customers(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", None, "B", "C", "D"],
                "Date": ["2026-01-01", "2026-01-01", "bad", "2026-01-03", "2026-01-04"],
                "Amount": [10, 20, 30, "bad", -5],
            }
        )

        result = calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
        )

        self.assertEqual(result.quality.input_rows, 5)
        self.assertEqual(result.quality.rows_used, 2)
        self.assertEqual(result.quality.dropped_rows, 3)
        self.assertEqual(result.quality.missing_customer_rows, 1)
        self.assertEqual(result.quality.invalid_date_rows, 1)
        self.assertEqual(result.quality.invalid_monetary_rows, 1)
        self.assertEqual(result.quality.customers_excluded_without_purchase, 1)

    def test_scores_reward_recent_frequent_and_high_value_customers(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "A", "B", "C"],
                "Date": ["2026-05-10", "2026-05-09", "2026-05-08", "2026-04-01", "2026-01-01"],
                "Order": ["A1", "A2", "A3", "B1", "C1"],
                "Amount": [300, 250, 200, 100, 10],
            }
        )

        customers = calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
            order_column="Order",
        ).customers.set_index("Customer")

        self.assertGreater(customers.loc["A", "R Score"], customers.loc["C", "R Score"])
        self.assertGreater(customers.loc["A", "F Score"], customers.loc["B", "F Score"])
        self.assertGreater(customers.loc["A", "M Score"], customers.loc["C", "M Score"])
        self.assertEqual(customers.loc["A", "Segment"], "Champions")

    def test_explicit_analysis_date_is_supported(self):
        frame = pd.DataFrame({"Customer": ["A"], "Date": ["2026-01-01"], "Amount": [10]})

        result = calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
            analysis_date="2026-01-11",
        )

        self.assertEqual(result.analysis_date, pd.Timestamp("2026-01-11"))
        self.assertEqual(result.customers.loc[0, "Recency"], 10)

    def test_invalid_configuration_has_a_clear_error(self):
        frame = pd.DataFrame({"Customer": ["A"], "Date": ["2026-01-01"], "Amount": [10]})

        with self.assertRaisesRegex(RFMCalculationError, "missing"):
            calculate_rfm(
                frame,
                customer_column="Missing Customer",
                date_column="Date",
                monetary_column="Amount",
            )
        with self.assertRaisesRegex(RFMCalculationError, "different column"):
            calculate_rfm(
                frame,
                customer_column="Customer",
                date_column="Date",
                monetary_column="Date",
            )
        with self.assertRaisesRegex(RFMCalculationError, "before the latest purchase"):
            calculate_rfm(
                frame,
                customer_column="Customer",
                date_column="Date",
                monetary_column="Amount",
                analysis_date="2025-12-31",
            )

    def test_input_dataframe_is_not_modified(self):
        frame = pd.DataFrame({"Customer": ["A"], "Date": ["2026-01-01"], "Amount": [10]})
        original = frame.copy(deep=True)

        calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
        )

        pd.testing.assert_frame_equal(frame, original)

    def test_segment_actions_are_specific_and_backed_by_result_values(self):
        frame = pd.DataFrame(
            {
                "Customer": ["A", "A", "A", "B", "C"],
                "Date": ["2026-05-10", "2026-05-09", "2026-05-08", "2026-04-01", "2026-01-01"],
                "Order": ["A1", "A2", "A3", "B1", "C1"],
                "Amount": [300, 250, 200, 100, 10],
            }
        )
        result = calculate_rfm(
            frame,
            customer_column="Customer",
            date_column="Date",
            monetary_column="Amount",
            order_column="Order",
        )

        actions = build_segment_actions(result)
        champions = next(item for item in actions if item.segment == "Champions")

        self.assertEqual(champions.customers, 1)
        self.assertEqual(champions.monetary, 750)
        self.assertIn("1 customers", champions.rationale)
        self.assertAlmostEqual(sum(item.monetary_share for item in actions), 1.0)
        self.assertEqual(len(actions), result.customers["Segment"].nunique())


if __name__ == "__main__":
    unittest.main()
