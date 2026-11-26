"""실제 원본과 배포 스냅샷의 합계·필터 범위·공개 필드를 검증한다."""

import csv
import gzip
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

import duckdb


class SnapshotTest(unittest.TestCase):
    """생성 코드와 독립적인 CSV 순회로 배포 데이터의 의미를 확인한다."""

    @classmethod
    def setUpClass(cls):
        cls.snapshot_path = Path("dashboard/public/data/snapshot.json.gz")
        cls.payload = gzip.decompress(cls.snapshot_path.read_bytes())
        cls.snapshot = json.loads(cls.payload)
        cls.metadata = cls.snapshot["metadata"]
        cls.rows = cls.snapshot["rows"]
        cls.measures = {
            "가입자수": "subscribers", "당월고지금액": "billing",
            "신규취득자수": "new", "상실가입자수": "lost",
        }
        cls.raw_totals = Counter()
        cls.raw_by_status = {}
        cls.raw_selected = Counter()
        cls.raw_zero_count = 0
        cls.raw_unknown_industry_count = 0
        cls.source_path = Path(cls.metadata["source_file"])
        if not cls.source_path.exists():
            return
        with cls.source_path.open(encoding="cp949", newline="") as stream:
            for record in csv.DictReader(stream):
                values = {"workplaces": 1}
                values.update({metric: int(record[column]) for column, metric in cls.measures.items()})
                cls.raw_totals.update(values)
                status = {"1": "등록", "2": "탈퇴"}.get(record["사업장가입상태코드 1 등록 2 탈퇴"], "미상")
                cls.raw_by_status.setdefault(status, Counter()).update(values)
                if int(record["가입자수"]) == 0:
                    cls.raw_zero_count += 1
                if not record["사업장업종코드명"]:
                    cls.raw_unknown_industry_count += 1
                if (
                    record["법정동주소광역시도코드"] == "41"
                    and record["사업장가입상태코드 1 등록 2 탈퇴"] == "1"
                    and record["사업장형태구분코드 1 법인 2 개인"] == "2"
                    and 10 <= int(record["가입자수"]) <= 29
                ):
                    cls.raw_selected.update(values)

    def aggregate(self, predicate=lambda row: True):
        totals = Counter({"workplaces": 0, **dict.fromkeys(self.measures.values(), 0)})
        for row in self.rows:
            if predicate(row):
                totals.update({name: row[name] for name in totals})
        return dict(totals)

    def test_all_metrics_match_original(self):
        self.assertEqual(self.aggregate(), self.metadata["totals"])
        if self.source_path.exists():
            self.assertEqual(self.aggregate(), dict(self.raw_totals))

    def test_status_totals_match_original(self):
        for status, totals in self.metadata["totals_by_status"].items():
            self.assertEqual(self.aggregate(lambda row: row["status"] == status), totals)
            if self.source_path.exists():
                self.assertEqual(totals, dict(self.raw_by_status[status]))

    def test_combined_filter_matches_original(self):
        if not self.source_path.exists():
            self.skipTest("대용량 원본이 없어 원본 복합 필터 대조를 생략합니다.")
        selected = self.aggregate(lambda row: (
            row["region"] == "경기도" and row["status"] == "등록"
            and row["kind"] == "개인" and row["size_band"] == "10~29명"
        ))
        self.assertGreater(selected["workplaces"], 0)
        self.assertEqual(selected, dict(self.raw_selected))

    def test_zero_and_missing_categories_are_preserved(self):
        zero = self.aggregate(lambda row: row["size_band"] == "0명")
        self.assertEqual(zero["subscribers"], 0)
        self.assertEqual(zero["workplaces"], self.metadata["quality"]["zero_subscriber_rows"])
        self.assertEqual(
            self.aggregate(lambda row: row["industry"] == "미상")["workplaces"],
            self.metadata["quality"]["missing_values"]["사업장업종코드명"],
        )
        if self.source_path.exists():
            self.assertEqual(zero["workplaces"], self.raw_zero_count)
            self.assertEqual(self.metadata["quality"]["missing_values"]["사업장업종코드명"], self.raw_unknown_industry_count)

    def test_source_checksum(self):
        if not self.source_path.exists():
            self.skipTest("대용량 원본이 없어 원본 SHA256 대조를 생략합니다.")
        with self.source_path.open("rb") as stream:
            self.assertEqual(hashlib.file_digest(stream, "sha256").hexdigest(), self.metadata["source_sha256"])

    def test_public_rows_have_only_approved_fields(self):
        expected = {
            "period", "region", "status", "kind", "industry_code", "industry",
            "size_band", "workplaces", "subscribers", "billing", "new", "lost",
        }
        self.assertTrue(self.rows)
        for row in self.rows:
            self.assertEqual(set(row), expected)

    def test_compressed_and_local_snapshots_are_equal(self):
        local_json = self.snapshot_path.with_suffix("")
        if local_json.exists():
            self.assertEqual(self.payload, local_json.read_bytes())
        self.assertEqual(self.snapshot_path.read_bytes()[4:8], b"\x00\x00\x00\x00")

    def test_metadata_matches_snapshot(self):
        metadata_file = self.snapshot_path.with_name("metadata.json")
        self.assertEqual(json.loads(metadata_file.read_text()), self.metadata)

    def test_parquet_rows_match_snapshot(self):
        with duckdb.connect() as connection:
            cursor = connection.execute("SELECT * FROM read_parquet(?)", [str(self.snapshot_path.with_name("snapshot.parquet"))])
            names = [column[0] for column in cursor.description]
            parquet_rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
        self.assertEqual(parquet_rows, self.rows)


if __name__ == "__main__":
    unittest.main()
