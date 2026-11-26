"""최신 공개 원본 22개 열을 보존한 전체 조회용 Parquet을 만든다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb


MEASURES = ["가입자수", "당월고지금액", "신규취득자수", "상실가입자수"]


def quoted(name: str) -> str:
    """원본 열 이름을 SQL 식별자로 인용한다."""
    return '"' + name.replace('"', '""') + '"'


def prepare(source: Path, metadata_path: Path, output: Path) -> dict:
    """원본 무결성·전체 행·열·측정값을 확인한 뒤 조회 파일을 저장한다."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != metadata["source_sha256"] or source.stat().st_size != metadata["source_bytes"]:
        raise ValueError("원본의 SHA256 또는 크기가 최신 집계의 출처와 다릅니다.")
    independent_totals = Counter()
    independent_missing = Counter()
    row_count = 0
    with source.open(encoding="cp949", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        for row in reader:
            row_count += 1
            independent_totals.update({name: int(row[name]) for name in MEASURES})
            independent_missing.update({name: int(row[name] == "") for name in columns})
    if row_count != metadata["quality"]["source_rows"] or len(columns) != 22:
        raise ValueError("원본 전체 행 수 또는 22개 열 명세가 일치하지 않습니다.")
    expected = {"가입자수": metadata["totals"]["subscribers"], "당월고지금액": metadata["totals"]["billing"], "신규취득자수": metadata["totals"]["new"], "상실가입자수": metadata["totals"]["lost"]}
    if dict(independent_totals) != expected:
        raise ValueError("독립적으로 순회한 원본 측정값 합계가 최신 집계와 다릅니다.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nps-raw-") as temporary, duckdb.connect() as connection:
        utf8 = Path(temporary) / "source.csv"
        with source.open(encoding="cp949", newline="") as reader, utf8.open("w", encoding="utf-8", newline="") as writer:
            shutil.copyfileobj(reader, writer)
        connection.execute("CREATE TABLE original AS SELECT * FROM read_csv(?, header=true, all_varchar=true)", [str(utf8)])
        expressions = [f"CAST({quoted(name)} AS BIGINT) AS {quoted(name)}" if name in MEASURES else quoted(name) for name in columns]
        connection.execute("CREATE TABLE typed AS SELECT " + ", ".join(expressions) + " FROM original")
        connection.execute("COPY typed TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(output)])
        schema = connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(output)]).fetchall()
        if [row[0] for row in schema] != columns:
            raise ValueError("Parquet의 원본 열 이름 또는 열 순서가 다릅니다.")
        totals = connection.execute("SELECT count(*), " + ", ".join(f"SUM({quoted(name)})" for name in MEASURES) + " FROM read_parquet(?)", [str(output)]).fetchone()
        if totals[0] != row_count or dict(zip(MEASURES, totals[1:])) != expected:
            raise ValueError("Parquet의 전체 행 수 또는 측정값 합계가 다릅니다.")
        missing = {name: connection.execute(f"SELECT count(*) FROM read_parquet(?) WHERE {quoted(name)} IS NULL", [str(output)]).fetchone()[0] for name in columns}
        if missing != dict(independent_missing):
            raise ValueError("Parquet의 열별 결측 수가 원본과 다릅니다.")
        differences = connection.execute("SELECT count(*) FROM ((SELECT * FROM typed EXCEPT ALL SELECT * FROM read_parquet(?)) UNION ALL (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT * FROM typed))", [str(output), str(output)]).fetchone()[0]
        if differences:
            raise ValueError("원본 자료형 변환 결과와 Parquet 전체 행이 다릅니다.")
        maximum = connection.execute('SELECT MAX("가입자수") FROM typed').fetchone()[0]
    if output.stat().st_size >= 100_000_000:
        raise ValueError("전체 조회 파일이 GitHub 일반 파일 용량 상한에 가까워 분할이 필요합니다.")
    public_metadata = {
        "schema_version": 1,
        "title": "국민연금 가입 사업장 전체 원본 탐색",
        "source_url": metadata["source_url"],
        "source_published_at": metadata["source_published_at"],
        "collected_at": metadata["collected_at"],
        "source_sha256": digest,
        "source_bytes": source.stat().st_size,
        "source_file": source.as_posix(),
        "periods": metadata["periods"],
        "row_count": row_count,
        "column_count": len(columns),
        "columns": [{"name": row[0], "type": row[1], "missing": missing[row[0]]} for row in schema],
        "parquet_bytes": output.stat().st_size,
        "parquet_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "max_subscribers": maximum,
        "regions": [{"code": row["code"], "name": row["region"]} for row in metadata["quality"]["source_region_counts"]],
        "totals": expected,
        "coverage_note": metadata["coverage_note"],
        "region_note": metadata["region_note"],
        "publication_note": "공공데이터포털이 공개한 원본 22개 열과 모든 행을 조회합니다. 사업장명·공개 주소·축약 사업자등록번호가 포함됩니다. 원본에 없는 식별정보를 추가하지 않습니다.",
        "type_note": "가입자수·당월고지금액·신규취득자수·상실가입자수는 정수형이며 코드·우편번호·일자는 원본 문자열을 보존합니다. 빈 필드는 결측으로 보존합니다.",
        "verification": "표준 csv 모듈의 독립 전체 행 수·열별 결측·측정값 합계·원본 SHA256을 대조했고, DuckDB EXCEPT ALL로 Parquet 전체 22열의 행 일치를 확인했습니다.",
        "prepared_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
    }
    output.with_name("raw_metadata.json").write_text(json.dumps(public_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return public_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None, help="공개 원본 CSV, 생략하면 최신 집계의 원본을 사용")
    parser.add_argument("--metadata", type=Path, default=Path("dashboard/public/data/metadata.json"), help="최신 집계의 출처 메타데이터")
    parser.add_argument("--output", type=Path, default=Path("dashboard/public/data/raw.parquet"), help="전체 조회용 Parquet")
    args = parser.parse_args()
    source = args.source or Path(json.loads(args.metadata.read_text(encoding="utf-8"))["source_file"])
    result = prepare(source, args.metadata, args.output)
    print(f"전체 데이터 저장: {args.output} · {result['row_count']:,}행 × {result['column_count']}열 · {result['parquet_bytes']:,}바이트")
    print("원본 SHA256·행 수·열 수·결측·측정값·Parquet 전체 행 일치 검증 통과")


if __name__ == "__main__":
    main()
