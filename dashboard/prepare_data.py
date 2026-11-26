"""국민연금 사업장 원본을 정적 대시보드용 익명 집계로 변환한다."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb


REGIONS = {
    "11": "서울특별시",
    "12": "전남광주통합특별시",
    "26": "부산광역시",
    "27": "대구광역시",
    "28": "인천광역시",
    "29": "광주광역시",
    "30": "대전광역시",
    "31": "울산광역시",
    "36": "세종특별자치시",
    "41": "경기도",
    "42": "강원도",
    "43": "충청북도",
    "44": "충청남도",
    "45": "전라북도",
    "46": "전라남도",
    "47": "경상북도",
    "48": "경상남도",
    "50": "제주특별자치도",
    "51": "강원특별자치도",
    "52": "전북특별자치도",
}
METRICS = {
    "가입자수": "subscribers",
    "당월고지금액": "billing",
    "신규취득자수": "new",
    "상실가입자수": "lost",
}
DIMENSIONS = [
    "period", "region", "status", "kind", "industry_code", "industry", "size_band"
]
SIZE_BANDS = [
    "0명", "1~2명", "3~4명", "5~9명", "10~29명", "30~99명",
    "100~299명", "300~999명", "1,000명 이상",
]
SOURCE_URL = "https://www.data.go.kr/data/15083277/fileData.do"


def records(connection, query: str, parameters=None) -> list[dict]:
    """DuckDB 조회 결과를 열 이름이 있는 사전 목록으로 변환한다."""
    cursor = connection.execute(query, parameters or [])
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def identifier(value: str) -> str:
    """원본 열 이름을 SQL 식별자로 안전하게 인용한다."""
    return '"' + value.replace('"', '""') + '"'


def source_totals(source: Path) -> tuple[int, dict[str, int], dict[str, dict[str, int]]]:
    """DuckDB 집계와 별개로 원본을 한 행씩 읽어 전체·가입상태 합계를 계산한다."""
    count = 0
    totals = Counter({"workplaces": 0, **dict.fromkeys(METRICS.values(), 0)})
    by_status: dict[str, Counter] = {}
    with source.open(encoding="cp949", newline="") as stream:
        for row in csv.DictReader(stream):
            count += 1
            status = {"1": "등록", "2": "탈퇴"}.get(
                row["사업장가입상태코드 1 등록 2 탈퇴"], "미상"
            )
            status_total = by_status.setdefault(status, Counter())
            totals["workplaces"] += 1
            status_total["workplaces"] += 1
            for original, metric in METRICS.items():
                value = int(row[original])
                totals[metric] += value
                status_total[metric] += value
    return count, dict(totals), {key: dict(value) for key, value in by_status.items()}


def prepare(source: Path, manifest: Path, output: Path) -> dict:
    """원본 무결성과 합계를 확인하고 사업장 식별정보가 없는 집계 파일을 저장한다."""
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        entries = list(csv.DictReader(stream))
    matched = [row for row in entries if Path(row["저장경로"]).name == source.name]
    if len(matched) != 1:
        raise ValueError("원본 파일에 대응하는 출처 기록이 정확히 한 개 필요합니다.")
    record = matched[0]
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != record["SHA256"]:
        raise ValueError("원본의 SHA256이 수집 기록과 다릅니다.")
    if source.stat().st_size != int(record["파일크기_바이트"]):
        raise ValueError("원본의 파일 크기가 수집 기록과 다릅니다.")
    if record["랜딩URL"] != SOURCE_URL:
        raise ValueError("요청한 데이터와 수집 기록의 출처가 다릅니다.")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nps-dashboard-") as temporary, duckdb.connect() as connection:
        utf8_source = Path(temporary) / "source.csv"
        with source.open(encoding="cp949", newline="") as reader, utf8_source.open("w", encoding="utf-8", newline="") as writer:
            shutil.copyfileobj(reader, writer)
        connection.execute(
            "CREATE TABLE raw_source AS SELECT * FROM read_csv(?, header=true, all_varchar=true)",
            [str(utf8_source)],
        )
        columns = [row[0] for row in connection.execute("DESCRIBE raw_source").fetchall()]
        required = {"자료생성년월", "법정동주소광역시도코드", "사업장업종코드", "사업장업종코드명", "사업장가입상태코드 1 등록 2 탈퇴", "사업장형태구분코드 1 법인 2 개인", *METRICS}
        if not required.issubset(columns):
            raise ValueError("원본 열 명세가 변경되었습니다. 필요한 열을 확인하세요.")
        missing_values = {
            name: connection.execute(f"SELECT count(*) FROM raw_source WHERE {identifier(name)} IS NULL").fetchone()[0]
            for name in columns
        }
        missing_metrics = {name: missing_values[name] for name in METRICS}
        negative_metrics = {
            name: connection.execute(f"SELECT count(*) FROM raw_source WHERE CAST({identifier(name)} AS BIGINT) < 0").fetchone()[0]
            for name in METRICS
        }
        if any(missing_metrics.values()):
            raise ValueError("측정값에 결측이 있어 집계를 중단했습니다. 결측 처리 기준을 확인하세요.")
        if any(negative_metrics.values()):
            raise ValueError("측정값에 음수가 있어 집계를 중단했습니다. 원본 값을 확인하세요.")
        connection.execute("CREATE TABLE region_names (code VARCHAR, region VARCHAR)")
        connection.executemany("INSERT INTO region_names VALUES (?, ?)", list(REGIONS.items()))
        numeric_fields = ", ".join(f"CAST({identifier(name)} AS BIGINT) AS {identifier(metric)}" for name, metric in METRICS.items())
        connection.execute(f"""
            CREATE TABLE normalized AS
            SELECT COALESCE("자료생성년월", '미상') AS period,
                   COALESCE(region_names.region, '미상') AS region,
                   CASE "사업장가입상태코드 1 등록 2 탈퇴" WHEN '1' THEN '등록' WHEN '2' THEN '탈퇴' ELSE '미상' END AS status,
                   CASE "사업장형태구분코드 1 법인 2 개인" WHEN '1' THEN '법인' WHEN '2' THEN '개인' ELSE '미상' END AS kind,
                   COALESCE("사업장업종코드", '미상') AS industry_code,
                   COALESCE("사업장업종코드명", '미상') AS industry,
                   CASE WHEN CAST("가입자수" AS BIGINT) = 0 THEN '0명'
                        WHEN CAST("가입자수" AS BIGINT) <= 2 THEN '1~2명'
                        WHEN CAST("가입자수" AS BIGINT) <= 4 THEN '3~4명'
                        WHEN CAST("가입자수" AS BIGINT) <= 9 THEN '5~9명'
                        WHEN CAST("가입자수" AS BIGINT) <= 29 THEN '10~29명'
                        WHEN CAST("가입자수" AS BIGINT) <= 99 THEN '30~99명'
                        WHEN CAST("가입자수" AS BIGINT) <= 299 THEN '100~299명'
                        WHEN CAST("가입자수" AS BIGINT) <= 999 THEN '300~999명'
                        ELSE '1,000명 이상' END AS size_band,
                   {numeric_fields}
            FROM raw_source
            LEFT JOIN region_names ON raw_source."법정동주소광역시도코드" = region_names.code
        """)
        dimension_sql = ", ".join(identifier(name) for name in DIMENSIONS)
        metric_sums = ", ".join(f"CAST(sum({identifier(metric)}) AS BIGINT) AS {identifier(metric)}" for metric in METRICS.values())
        connection.execute(f"""
            CREATE TABLE aggregates AS
            SELECT {dimension_sql}, count(*) AS workplaces, {metric_sums}
            FROM normalized GROUP BY {dimension_sql} ORDER BY {dimension_sql}
        """)
        rows = records(connection, "SELECT * FROM aggregates")
        measures = ["workplaces", *METRICS.values()]
        sum_sql = ", ".join(f"CAST(sum({identifier(name)}) AS BIGINT) AS {identifier(name)}" for name in measures)
        aggregate_totals = records(connection, f"SELECT {sum_sql} FROM aggregates")[0]
        aggregate_status = {}
        for row in records(connection, f"SELECT status, {sum_sql} FROM aggregates GROUP BY status"):
            status = row.pop("status")
            aggregate_status[status] = row
        count, totals, status_totals = source_totals(source)
        original_count = connection.execute("SELECT count(*) FROM raw_source").fetchone()[0]
        if count != original_count or totals != aggregate_totals or status_totals != aggregate_status:
            raise ValueError("독립적으로 계산한 원본 합계와 DuckDB 집계 합계가 일치하지 않습니다.")
        for dimension in DIMENSIONS:
            split_totals = records(connection, f"SELECT {sum_sql} FROM (SELECT {identifier(dimension)}, {sum_sql} FROM aggregates GROUP BY {identifier(dimension)})")[0]
            if split_totals != totals:
                raise ValueError(f"{dimension}별 분할 합계가 전체 합계와 다릅니다.")
        periods = [row[0] for row in connection.execute("SELECT DISTINCT period FROM normalized ORDER BY period").fetchall()]
        region_counts = [
            {"code": code, "region": REGIONS.get(code, "미상"), "rows": value}
            for code, value in connection.execute("""SELECT COALESCE("법정동주소광역시도코드", '미상') AS code, count(*) FROM raw_source GROUP BY code ORDER BY code""").fetchall()
        ]
        quality = {
            "source_rows": count, "source_columns": len(columns), "aggregate_rows": len(rows),
            "duplicate_rows": connection.execute("SELECT (SELECT count(*) FROM raw_source) - (SELECT count(*) FROM (SELECT DISTINCT * FROM raw_source))").fetchone()[0],
            "zero_subscriber_rows": connection.execute("SELECT count(*) FROM normalized WHERE subscribers=0").fetchone()[0],
            "missing_values": missing_values, "metric_missing_values": missing_metrics,
            "metric_negative_values": negative_metrics,
            "unknown_region_rows": connection.execute("SELECT count(*) FROM normalized WHERE region='미상'").fetchone()[0],
            "unknown_status_rows": connection.execute("SELECT count(*) FROM normalized WHERE status='미상'").fetchone()[0],
            "unknown_kind_rows": connection.execute("SELECT count(*) FROM normalized WHERE kind='미상'").fetchone()[0],
            "source_region_counts": region_counts,
            "duplicate_policy": "완전 중복 행도 원본 기록으로 보존하며 임의 제거하지 않습니다.",
            "metric_missing_policy": "측정값 결측이나 음수가 있으면 0으로 바꾸지 않고 생성에 실패합니다.",
            "verification": "표준 csv 모듈로 원본 전체·가입상태별 합계를 독립 재계산하고 DuckDB SQL의 전체·상태별·모든 집계 차원의 분할 합계와 대조했습니다.",
        }
        parquet_path = output.with_suffix(".parquet")
        quoted_path = "'" + str(parquet_path).replace("'", "''") + "'"
        connection.execute(f"COPY aggregates TO {quoted_path} (FORMAT PARQUET, COMPRESSION ZSTD)")
        parquet_totals = records(connection, f"SELECT {sum_sql} FROM read_parquet(?)", [str(parquet_path)])[0]
        if parquet_totals != totals:
            raise ValueError("Parquet 배포 데이터 합계가 원본과 다릅니다.")
    metadata = {
        "schema_version": 1,
        "title": record["데이터명"],
        "source_url": record["랜딩URL"],
        "download_url": record["다운로드URL"],
        "source_published_at": record["게시일"],
        "source_modified_at": record["수정일"],
        "collected_at": record["수집시각"],
        "source_sha256": digest,
        "source_bytes": source.stat().st_size,
        "source_encoding": "cp949",
        "prepared_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "periods": periods,
        "source_file": source.as_posix(),
        "aggregation_engine": f"DuckDB {duckdb.__version__}",
        "parquet_file": "public/data/" + output.with_suffix(".parquet").name,
        "size_bands": SIZE_BANDS,
        "totals": totals,
        "totals_by_status": status_totals,
        "quality": quality,
        "coverage_note": "공공데이터포털 안내상 제공 범위는 가입자 수 3인 이상 법인사업장과 10인 이상 개인사업장(2025년 7월 이후)입니다. 원본에는 탈퇴·0명 사업장 기록도 포함되어 있습니다. 전체 사업장 또는 전체 고용인구 통계로 해석할 수 없습니다.",
        "record_note": "사업장 수는 원본 행 수입니다. 사업자등록번호가 축약되어 있어 고유 사업장 수를 별도로 추정하지 않았습니다.",
        "region_note": "지역은 원본 법정동 시도코드에 대응합니다. 코드 12의 ‘전남광주통합특별시’는 원본 주소 표기를 사용하며 현재 공식 행정구역이라는 의미가 아닙니다. 구 코드 42·45와 새 코드 51·52를 합치지 않았습니다.",
        "period_note": "자료생성년월은 신고 반영 기준 월입니다. 파일 게시일·수집일·대시보드 생성일과 다르며 단일 월 스냅샷으로 시계열 추세를 추정하지 않습니다.",
        "billing_note": "당월 고지금액은 국민연금 고지금액이며 매출·실수령 급여·실제소득과 같지 않습니다.",
        "flow_note": "신규취득자수와 상실가입자수는 신고된 자격 취득·상실 인원입니다. 차이를 순고용 증가나 전체 고용 변동으로 해석하지 않습니다.",
        "publication_note": "정적 배포에는 집계 행만 포함하고 사업장명·상세주소·사업자등록번호는 포함하지 않습니다.",
    }
    snapshot = {"metadata": metadata, "rows": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    output.write_bytes(payload)
    output.with_suffix(output.suffix + ".gz").write_bytes(gzip.compress(payload, mtime=0))
    output.with_name("metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="원본 CSV 경로(생략하면 수집 기록에서 선택)")
    parser.add_argument("--manifest", type=Path, default=Path("data/download_manifest_latest.csv"), help="수집 기록 경로")
    parser.add_argument("--output", type=Path, default=Path("dashboard/public/data/snapshot.json"), help="집계 JSON 저장 경로")
    args = parser.parse_args()
    if args.source is None:
        with args.manifest.open(encoding="utf-8-sig", newline="") as stream:
            args.source = Path(next(csv.DictReader(stream))["저장경로"])
    snapshot = prepare(args.source, args.manifest, args.output)
    print(f"집계 저장: {args.output}")
    print(f"정적 배포용 압축 저장: {args.output.with_suffix(args.output.suffix + '.gz')}")
    print(f"원본 {snapshot['metadata']['quality']['source_rows']:,}행 → 집계 {len(snapshot['rows']):,}행")
    print(f"전체 합계: {json.dumps(snapshot['metadata']['totals'], ensure_ascii=False)}")
    print(f"브라우저 SQL용 Parquet 저장: {args.output.with_suffix('.parquet')}")
    print(f"출처 메타데이터 저장: {args.output.with_name('metadata.json')}")
    print("원본 SHA256·파일 크기·DuckDB/CSV/Parquet 전체·상태별·차원별 합계 검증 통과")


if __name__ == "__main__":
    main()
