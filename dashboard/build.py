"""기존 환경의 marimo로 GitHub Pages용 정적 대시보드를 만든다."""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import duckdb


def main() -> None:
    folder = Path(__file__).resolve().parent
    snapshot_path = folder / "public" / "data" / "snapshot.json.gz"
    if not snapshot_path.is_file():
        raise SystemExit("집계 파일이 없습니다. 먼저 dashboard/prepare_data.py를 실행하세요.")
    snapshot = json.loads(gzip.decompress(snapshot_path.read_bytes()))
    if not snapshot.get("rows"):
        raise SystemExit("집계 데이터가 비어 있어 배포를 중단합니다.")
    for metric, total in snapshot["metadata"]["totals"].items():
        if metric in {"workplaces", "subscribers", "billing", "new", "lost"}:
            if sum(row[metric] for row in snapshot["rows"]) != total:
                raise SystemExit(f"집계 합계가 맞지 않습니다: {metric}")
    metadata_path = folder / "public" / "data" / "metadata.json"
    parquet_path = folder / "public" / "data" / "snapshot.parquet"
    if json.loads(metadata_path.read_text(encoding="utf-8")) != snapshot["metadata"]:
        raise SystemExit("공개 메타데이터와 검증 스냅샷이 다릅니다.")
    with duckdb.connect() as connection:
        metrics = list(snapshot["metadata"]["totals"])
        totals = connection.execute(
            "SELECT " + ", ".join(f'SUM("{key}")' for key in metrics) + " FROM read_parquet(?)",
            [str(parquet_path)],
        ).fetchone()
        if dict(zip(metrics, totals)) != snapshot["metadata"]["totals"]:
            raise SystemExit("Parquet 데이터와 원본 집계의 합계가 다릅니다.")
    subprocess.run(
        [sys.executable, "-m", "marimo", "check", str(folder / "app.py")],
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "marimo", "export", "html-wasm", str(folder / "app.py"),
         "-o", str(folder / "dist"), "--mode", "run", "--no-execute", "--no-sandbox", "--force"],
        check=True,
    )
    output = folder / "dist"
    if not (output / "index.html").is_file() or not (output / "public" / "data" / "snapshot.parquet").is_file():
        raise SystemExit("정적 배포 파일이 완성되지 않았습니다.")
    (output / "public" / "data" / "snapshot.json").unlink(missing_ok=True)
    (output / ".nojekyll").touch()
    print("정적 대시보드 생성 완료: dashboard/dist")


if __name__ == "__main__":
    main()
