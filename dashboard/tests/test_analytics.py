"""추정값·분석 모수·규모 경계·이력 연결의 의미를 검증한다."""

import csv
import hashlib
import json
import statistics
import unittest
from collections import Counter
from pathlib import Path

import duckdb

from dashboard.prepare_analytics import validate_periods


class AnalyticsTest(unittest.TestCase):
    """공개 분석 파일과 독립적인 원본 계산을 대조한다."""

    @classmethod
    def setUpClass(cls):
        cls.path = Path("dashboard/public/data/analytics.parquet")
        cls.metadata = json.loads(cls.path.with_name("analytics_metadata.json").read_text())
        cls.snapshot = json.loads(cls.path.with_name("metadata.json").read_text())
        cls.connection = duckdb.connect()
        cls.connection.execute("CREATE TABLE analytics AS SELECT * FROM read_parquet(?)", [str(cls.path)])
        cls.source = Path(cls.metadata["source_file"])
        cls.expected_totals = Counter()
        cls.eligible_totals = Counter()
        cls.eligible_estimates = []
        cls.above_cap_count = 0
        cls.range_totals = Counter({"workplaces": 0, "subscribers": 0, "billing": 0, "new": 0, "lost": 0})
        if cls.source.exists():
            with cls.source.open(encoding="cp949", newline="") as stream:
                for row in csv.DictReader(stream):
                    subscribers = int(row["가입자수"])
                    billing = int(row["당월고지금액"])
                    values = {"workplaces": 1, "subscribers": subscribers, "billing": billing,
                              "new": int(row["신규취득자수"]), "lost": int(row["상실가입자수"])}
                    cls.expected_totals.update(values)
                    if 10 <= subscribers <= 50 and billing <= 100_000_000 and values["new"] <= 5 and values["lost"] <= 5:
                        cls.range_totals.update(values)
                    if row["사업장가입상태코드 1 등록 2 탈퇴"] == "1" and subscribers >= 5 and billing > 0:
                        cls.eligible_totals.update(values)
                        cls.eligible_estimates.append(billing / subscribers / 0.095 * 12)
                        cls.above_cap_count += billing * 1000 > subscribers * 95 * 6_590_000

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_original_rows_and_totals_are_preserved(self):
        values = self.connection.execute("SELECT COUNT(*),SUM(subscribers),SUM(billing),SUM(new),SUM(lost) FROM analytics").fetchone()
        actual = dict(zip(["workplaces", "subscribers", "billing", "new", "lost"], values))
        self.assertEqual(actual, self.metadata["totals"])
        self.assertEqual(actual, self.snapshot["totals"])
        if self.source.exists():
            self.assertEqual(actual, dict(self.expected_totals))
        self.assertEqual(self.connection.execute("SELECT count(DISTINCT record_id),min(record_id),max(record_id) FROM analytics").fetchone(), (values[0], 1, values[0]))

    def test_source_and_parquet_checksums(self):
        self.assertEqual(self.metadata["source_sha256"], self.snapshot["source_sha256"])
        with self.path.open("rb") as stream:
            self.assertEqual(hashlib.file_digest(stream, "sha256").hexdigest(), self.metadata["parquet_sha256"])
        self.assertEqual(self.path.stat().st_size, self.metadata["parquet_bytes"])

    def test_estimate_formula_and_invalid_denominators(self):
        valid, invalid = self.connection.execute("SELECT COUNT(*) FILTER(WHERE salary_valid),COUNT(*) FILTER(WHERE NOT salary_valid) FROM analytics").fetchone()
        self.assertGreater(valid, 0)
        self.assertGreater(invalid, 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM analytics WHERE NOT salary_valid AND (annual_salary_proxy IS NOT NULL OR monthly_income_proxy IS NOT NULL)").fetchone()[0], 0)
        self.assertLess(self.connection.execute("SELECT MAX(ABS(annual_salary_proxy - billing * 12000.0 / (95 * subscribers))) FROM analytics WHERE salary_valid").fetchone()[0], 0.000001)

    def test_rate_and_upper_bound_are_period_specific(self):
        self.assertEqual(self.metadata["contribution_rate"], 0.095)
        self.assertEqual(self.metadata["monthly_income_upper"], 6_590_000)
        self.assertEqual(self.metadata["history"]["monthly_income_upper"], 6_370_000)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM analytics WHERE estimate_flag <> (salary_valid AND billing*1000>subscribers*95*6590000)").fetchone()[0], 0)
        boundary = self.connection.execute("SELECT billing*1000>subscribers*95*6590000 FROM (VALUES(1,626050),(1,626051)) AS t(subscribers,billing)").fetchall()
        self.assertEqual(boundary, [(False,), (True,)])

    def test_unsupported_period_does_not_reuse_the_2026_rate(self):
        for period in ["2026-07", "2026-10", "2026-12"]:
            validate_periods([period])
        for periods in [["2026-06"], ["2027-01"], [], ["2026-10", "2026-11"]]:
            with self.assertRaises(ValueError):
                validate_periods(periods)

    def test_size_boundaries_use_actual_subscriber_counts(self):
        expected = {4: "5인 미만", 5: "소규모 (5~49인)", 49: "소규모 (5~49인)", 50: "중규모 (50~299인)", 299: "중규모 (50~299인)", 300: "대규모 (300인 이상)"}
        for subscribers, label in expected.items():
            result = self.connection.execute("SELECT DISTINCT salary_size FROM analytics WHERE subscribers=?", [subscribers]).fetchall()
            self.assertEqual(result, [(label,)])

    def test_default_population_mean_and_median_match_csv(self):
        if not self.source.exists():
            self.skipTest("원본 CSV가 없어 독립 연봉 통계 대조를 생략합니다.")
        summary = self.metadata["default_summary"]
        for key, value in self.eligible_totals.items():
            self.assertEqual(summary[key], value)
        weighted = self.eligible_totals["billing"] / self.eligible_totals["subscribers"] / 0.095 * 12
        self.assertAlmostEqual(summary["weighted_mean_annual"], weighted, places=5)
        self.assertAlmostEqual(summary["business_mean_annual"], statistics.fmean(self.eligible_estimates), places=5)
        self.assertAlmostEqual(summary["business_median_annual"], statistics.median(self.eligible_estimates), places=5)
        self.assertEqual(summary["above_cap_workplaces"], self.above_cap_count)

    def test_history_is_only_connected_for_unique_matches(self):
        matched = self.connection.execute("SELECT COUNT(*) FROM analytics WHERE match_status='matched'").fetchone()[0]
        self.assertEqual(matched, self.metadata["history_match_counts"]["matched"])
        self.assertGreater(matched, 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM analytics WHERE match_status<>'matched' AND (previous_period IS NOT NULL OR previous_subscribers IS NOT NULL OR previous_billing IS NOT NULL)").fetchone()[0], 0)
        self.assertEqual(
            self.connection.execute("SELECT DISTINCT period,previous_period FROM analytics WHERE match_status='matched'").fetchall(),
            [(self.metadata["periods"][0], self.metadata["history"]["period"])],
        )

    def test_history_sample_matches_independent_original_rows(self):
        history = self.metadata.get("history")
        if not history or not Path(history["source_file"]).exists():
            self.skipTest("과거 원본 CSV가 없어 이력 연결 표본 대조를 생략합니다.")
        sample = self.connection.execute("SELECT business_name,registration_prefix,location_code,kind,previous_subscribers,previous_billing FROM analytics WHERE match_status='matched' ORDER BY subscribers DESC LIMIT 30").fetchall()
        expected = {(name.strip(), prefix.strip(), location.strip(), "1" if kind == "법인" else "2"): (subscribers, billing) for name, prefix, location, kind, subscribers, billing in sample}
        actual = {}
        found_counts = Counter()
        with Path(history["source_file"]).open(encoding="cp949", newline="") as stream:
            for row in csv.DictReader(stream):
                key = (row["사업장명"].strip(), row["사업자등록번호"].strip(), row["고객법정동주소코드"].strip(), row["사업장형태구분코드 1 법인 2 개인"])
                if key in expected:
                    found_counts[key] += 1
                    actual[key] = (int(row["가입자수"]), int(row["당월고지금액"]))
        self.assertEqual(actual, expected)
        self.assertTrue(all(value == 1 for value in found_counts.values()))

    def test_numeric_range_filter_matches_independent_csv(self):
        if not self.source.exists():
            self.skipTest("원본 CSV가 없어 수치 범위 필터의 독립 대조를 생략합니다.")
        values = self.connection.execute(
            "SELECT COUNT(*),SUM(subscribers),SUM(billing),SUM(new),SUM(lost) FROM analytics "
            "WHERE subscribers BETWEEN 10 AND 50 AND billing<=100000000 AND new<=5 AND lost<=5"
        ).fetchone()
        actual = dict(zip(["workplaces", "subscribers", "billing", "new", "lost"], values))
        self.assertEqual(actual, dict(self.range_totals))

    def test_numeric_slider_upper_bounds_are_open_ended(self):
        bounds = self.metadata["numeric_filter_bounds"]
        for metric in ["subscribers", "billing", "new", "lost"]:
            with self.subTest(지표=metric):
                bound = bounds[metric]
                sentinel = bound["maximum"] * bound["divisor"]
                percentile, maximum = self.connection.execute(
                    f"SELECT QUANTILE_CONT({metric},0.999),MAX({metric}) FROM analytics"
                ).fetchone()
                self.assertTrue(bound["open_ended_max"])
                self.assertGreaterEqual(sentinel, percentile)
                self.assertGreater(maximum, sentinel)


if __name__ == "__main__":
    unittest.main()
