"""사업장 검색·기록 선택·실제 상세 계산의 의미를 검증한다."""

import csv
import json
import unittest
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import duckdb


class BusinessDetailsTest(unittest.TestCase):
    """이름이 아닌 원본 기록을 선택하고 보유한 두 시점만 비교하는지 확인한다."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path("dashboard/public/data")
        cls.metadata = json.loads((cls.folder / "analytics_metadata.json").read_text())
        cls.connection = duckdb.connect()
        cls.connection.execute(
            "CREATE TABLE businesses AS SELECT * FROM read_parquet(?)",
            [str(cls.folder / "analytics.parquet")],
        )
        cls.largest = cls.records(
            "SELECT * FROM businesses ORDER BY subscribers DESC, record_id LIMIT 1"
        )[0]
        cls.zero_previous = cls.records(
            "SELECT * FROM businesses WHERE match_status='matched' "
            "AND previous_subscribers=0 AND previous_billing=0 AND subscribers>0 "
            "ORDER BY subscribers DESC, record_id LIMIT 1"
        )[0]
        cls.zero_current = cls.records(
            "SELECT * FROM businesses WHERE match_status='matched' "
            "AND subscribers=0 AND previous_subscribers>0 "
            "ORDER BY previous_subscribers DESC, record_id LIMIT 1"
        )[0]
        cls.unmatched = cls.records(
            "SELECT * FROM businesses WHERE match_status<>'matched' "
            "ORDER BY subscribers DESC, record_id LIMIT 1"
        )[0]
        cls.duplicate_name = cls.connection.execute(
            "SELECT business_name FROM businesses GROUP BY business_name "
            "HAVING COUNT(*)>1 ORDER BY COUNT(*) DESC, business_name LIMIT 1"
        ).fetchone()[0]
        cls.duplicate_rows = cls.records(
            "SELECT * FROM businesses WHERE business_name=? ORDER BY record_id",
            [cls.duplicate_name],
        )
        cls.search_terms = ("삼성", "SAMSUNG", "%", "_", "'", "' OR 1=1 --")
        cls.expected_search = {term: [] for term in cls.search_terms}
        cls.current_samples = {}
        cls.current_path = Path(cls.metadata["source_file"])
        sample_ids = {
            row["record_id"] for row in
            [cls.largest, cls.zero_previous, cls.zero_current, cls.unmatched]
        }
        if cls.current_path.exists():
            with cls.current_path.open(encoding="cp949", newline="") as stream:
                for record_id, row in enumerate(csv.DictReader(stream), start=1):
                    if record_id in sample_ids:
                        cls.current_samples[record_id] = row
                    name = row["사업장명"].casefold()
                    for term in cls.search_terms:
                        if term.casefold() in name:
                            cls.expected_search[term].append(record_id)

        cls.history_info = cls.metadata.get("history")
        cls.previous_samples = {}
        cls.previous_key_counts = Counter()
        cls.history_path = (
            Path(cls.history_info["source_file"]) if cls.history_info else None
        )
        historical_rows = [cls.largest, cls.zero_previous, cls.zero_current]
        expected_keys = {cls.match_key(row) for row in historical_rows}
        if cls.history_path is not None and cls.history_path.exists():
            with cls.history_path.open(encoding="cp949", newline="") as stream:
                for row in csv.DictReader(stream):
                    key = (
                        row["사업장명"].strip(), row["사업자등록번호"].strip(),
                        row["고객법정동주소코드"].strip(),
                        row["사업장형태구분코드 1 법인 2 개인"],
                    )
                    if key in expected_keys:
                        cls.previous_key_counts[key] += 1
                        cls.previous_samples[key] = row

        # 실제 화면이 사용하는 공개 정의를 받아 계산과 표시 데이터의 연결을 검사한다.
        from dashboard.app import app

        _, definitions = app.run()
        cls.build_history = staticmethod(definitions["build_business_history"])
        cls.change = staticmethod(definitions["business_change"])

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    @classmethod
    def records(cls, query, parameters=None):
        cursor = cls.connection.execute(query, parameters or [])
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def match_key(row):
        return (
            row["business_name"].strip(), row["registration_prefix"].strip(),
            row["location_code"].strip(), "1" if row["kind"] == "법인" else "2",
        )

    def test_literal_name_search_matches_independent_csv(self):
        if not self.current_path.exists():
            self.skipTest("현재 원본 CSV가 없어 이름 검색의 독립 대조를 생략합니다.")
        for term in self.search_terms:
            with self.subTest(검색어=term):
                selected = self.connection.execute(
                    "SELECT record_id FROM businesses "
                    "WHERE contains(lower(business_name), lower(?)) ORDER BY record_id",
                    [term],
                ).fetchall()
                self.assertEqual(
                    [row[0] for row in selected], self.expected_search[term]
                )

    def test_literal_special_characters_do_not_mean_all_records(self):
        total = self.metadata["row_count"]
        for term in ("%", "_", "'"):
            count = self.connection.execute(
                "SELECT COUNT(*) FROM businesses WHERE contains(business_name,?)",
                [term],
            ).fetchone()[0]
            self.assertGreater(count, 0)
            self.assertLess(count, total)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM businesses WHERE contains(business_name,?)",
                ["' OR 1=1 --"],
            ).fetchone()[0],
            0,
        )

    def test_selected_record_matches_its_original_csv_row(self):
        if not self.current_path.exists():
            self.skipTest("현재 원본 CSV가 없어 상세 기록의 독립 대조를 생략합니다.")
        for row in [self.largest, self.zero_previous, self.zero_current, self.unmatched]:
            with self.subTest(원본기록=row["record_id"]):
                original = self.current_samples[row["record_id"]]
                self.assertEqual(row["business_name"], original["사업장명"])
                self.assertEqual(row["registration_prefix"], original["사업자등록번호"])
                self.assertEqual(row["location_code"], original["고객법정동주소코드"])
                for column, metric in [
                    ("가입자수", "subscribers"), ("당월고지금액", "billing"),
                    ("신규취득자수", "new"), ("상실가입자수", "lost"),
                ]:
                    self.assertEqual(row[metric], int(original[column]))

    def test_same_name_records_keep_their_own_detail_values(self):
        self.assertGreater(len(self.duplicate_rows), 1)
        identifiers = [row["record_id"] for row in self.duplicate_rows]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertGreater(len({row["subscribers"] for row in self.duplicate_rows}), 1)
        for row in self.duplicate_rows:
            selected = self.records(
                "SELECT * FROM businesses WHERE record_id=?", [row["record_id"]]
            )
            self.assertEqual(len(selected), 1)
            current = self.build_history(selected[0], self.metadata)[-1]
            self.assertEqual(current["subscribers"], row["subscribers"])
            self.assertEqual(current["billing"], row["billing"])

    def test_history_has_only_observed_periods_and_public_metrics(self):
        history = self.build_history(self.largest, self.metadata)
        self.assertEqual(len(history), 2)
        self.assertEqual(
            [row["period"] for row in history],
            [self.metadata["history"]["period"], self.largest["period"]],
        )
        for row in history:
            self.assertEqual(
                set(row), {"period", "subscribers", "billing", "annual_salary"}
            )

    def test_prior_values_and_annual_estimate_match_independent_csv(self):
        if self.history_path is None or not self.history_path.exists():
            self.skipTest("과거 원본 CSV가 없어 상세 변화의 독립 대조를 생략합니다.")
        rate = Decimal(str(self.metadata["history"]["contribution_rate"]))
        for selected in [self.largest, self.zero_previous, self.zero_current]:
            with self.subTest(원본기록=selected["record_id"]):
                key = self.match_key(selected)
                original = self.previous_samples[key]
                self.assertEqual(self.previous_key_counts[key], 1)
                before = self.build_history(selected, self.metadata)[0]
                subscribers = int(original["가입자수"])
                billing = int(original["당월고지금액"])
                self.assertEqual(before["subscribers"], subscribers)
                self.assertEqual(before["billing"], billing)
                if subscribers > 0 and billing > 0:
                    expected = Decimal(billing) * 12 / Decimal(subscribers) / rate
                    self.assertAlmostEqual(before["annual_salary"], float(expected), places=5)
                else:
                    self.assertIsNone(before["annual_salary"])

    def test_zero_observations_are_distinct_from_missing_history(self):
        previous_zero = self.build_history(self.zero_previous, self.metadata)
        self.assertEqual(len(previous_zero), 2)
        self.assertEqual(previous_zero[0]["subscribers"], 0)
        self.assertEqual(previous_zero[0]["billing"], 0)
        self.assertIsNone(previous_zero[0]["annual_salary"])
        delta = self.change(0, previous_zero[1]["subscribers"])
        self.assertEqual(delta["difference"], previous_zero[1]["subscribers"])
        self.assertIsNone(delta["percent"])
        current_zero = self.build_history(self.zero_current, self.metadata)
        self.assertEqual(current_zero[-1]["subscribers"], 0)
        self.assertEqual(current_zero[-1]["billing"], 0)
        self.assertIsNone(current_zero[-1]["annual_salary"])
        delta = self.change(current_zero[0]["subscribers"], 0)
        self.assertEqual(delta["difference"], -current_zero[0]["subscribers"])
        self.assertEqual(delta["percent"], -100)

    def test_unverified_or_incomplete_history_is_not_fabricated(self):
        self.assertEqual(len(self.build_history(self.unmatched, self.metadata)), 1)
        invalid = dict(self.unmatched, previous_period="2026-06", previous_subscribers=10, previous_billing=1000)
        self.assertEqual(len(self.build_history(invalid, self.metadata)), 1)
        incomplete = dict(self.largest, previous_subscribers=None)
        self.assertEqual(len(self.build_history(incomplete, self.metadata)), 1)
        missing_change = self.change(None, 100)
        self.assertIsNone(missing_change["difference"])
        self.assertIsNone(missing_change["percent"])

    def test_history_uses_its_own_rate_and_changes_use_both_denominators(self):
        policy = deepcopy(self.metadata)
        policy["history"]["contribution_rate"] = 0.09
        history = self.build_history(self.largest, policy)
        expected_previous = (
            Decimal(self.largest["previous_billing"]) * 12
            / Decimal(self.largest["previous_subscribers"]) / Decimal("0.09")
        )
        self.assertAlmostEqual(history[0]["annual_salary"], float(expected_previous), places=5)
        self.assertEqual(history[-1]["annual_salary"], self.largest["annual_salary_proxy"])
        before, after = self.largest["previous_subscribers"], self.largest["subscribers"]
        change = self.change(before, after)
        self.assertEqual(change["difference"], after - before)
        self.assertAlmostEqual(change["percent"], (after / before - 1) * 100, places=9)
        self.assertEqual(self.change(0, 0), {"difference": 0, "percent": None})


if __name__ == "__main__":
    unittest.main()
