"""기존 환경의 marimo로 GitHub Pages용 정적 대시보드를 만든다."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb


EDITOR_GUIDE = '''
<aside id="dashboard-editor-guide" aria-label="편집기 사용 안내">
  <a href="../">← 대시보드</a>
  <span><strong>처음에는 우하단 ▶ 전체 실행</strong><span class="editor-guide-shortcut"> · 셀 실행 ⌘/Ctrl+Enter · 저장 ⌘/Ctrl+S</span></span>
  <span class="editor-guide-note">저장 후 우측 Download 메뉴에서 수정본 .py 내려받기 · 공개 화면 자동 반영 없음</span>
  <a href="public/notebooks/app.py" download title="편집한 내용이 아닌 현재 배포된 원본 Python 파일을 내려받습니다.">배포 원본 .py</a>
</aside>
<style>
#dashboard-editor-guide { position:fixed;z-index:40;top:8px;left:60px;right:110px;display:flex;align-items:center;flex-wrap:wrap;gap:6px 14px;min-height:36px;padding:7px 12px;border:1px solid #c8d9f6;border-radius:8px;background:#f1f6ff;color:#25436d;font:12px/1.4 system-ui,sans-serif;box-sizing:border-box; }
#dashboard-editor-guide a { color:#1d4ed8;text-decoration:none;font-weight:650;white-space:nowrap; }
#dashboard-editor-guide a:focus-visible { outline:2px solid #2563eb;outline-offset:3px; }
@media (max-width:1400px) { #dashboard-editor-guide .editor-guide-note { display:none; } }
@media (max-width:600px) { #dashboard-editor-guide { left:44px;right:100px;gap:3px 10px;font-size:10px;padding:6px 8px; } #dashboard-editor-guide .editor-guide-shortcut { display:none; } #dashboard-editor-guide>a:last-child { display:none; } }
</style>
'''


def export_notebook(notebook: Path, output: Path, mode: str, *, raw_data: bool = False) -> None:
    """같은 노트북을 조회 화면 또는 브라우저 편집 화면으로 내보낸다."""
    subprocess.run(
        [sys.executable, "-m", "marimo", "export", "html-wasm", str(notebook),
         "-o", str(output), "--mode", mode, "--no-execute", "--no-sandbox", "--force"],
        check=True,
    )
    index = output / "index.html"
    expected_mode = "read" if mode == "run" else "edit"
    if not index.is_file() or not re.search(
        rf'"mode"\s*:\s*"{expected_mode}"', index.read_text(encoding="utf-8")
    ):
        raise SystemExit(f"{mode} 모드의 내보내기 결과가 올바르지 않습니다.")
    if mode == "edit":
        # 첫 실행 전에는 노트북 셀 출력이 없으므로 정적 안내를 제공한다.
        html = index.read_text(encoding="utf-8")
        index.write_text(html.replace("</body>", EDITOR_GUIDE + "\n</body>"), encoding="utf-8")
    data_file = "raw.parquet" if raw_data else "snapshot.parquet"
    if not (output / "public" / "data" / data_file).is_file():
        raise SystemExit(f"{mode} 화면의 집계 데이터가 누락되었습니다.")
    excluded_files = (
        ["snapshot.json", "snapshot.json.gz", "snapshot.parquet", "metadata.json", "analytics.parquet"]
        if raw_data else ["snapshot.json", "raw.parquet", "raw_metadata.json"]
    )
    for filename in excluded_files:
        (output / "public" / "data" / filename).unlink(missing_ok=True)
    notebook_downloads = output / "public" / "notebooks"
    notebook_downloads.mkdir(parents=True, exist_ok=True)
    for filename in ("app.py", "explorer.py"):
        shutil.copyfile(notebook.parent / filename, notebook_downloads / filename)
    (output / ".nojekyll").touch()


def main() -> None:
    folder = Path(__file__).resolve().parent
    for filename in ("app.py", "explorer.py"):
        if not (folder / filename).is_file():
            raise SystemExit(f"배포할 노트북이 없습니다: dashboard/{filename}")
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
        raw_path = folder / "public" / "data" / "raw.parquet"
        raw_metadata_path = folder / "public" / "data" / "raw_metadata.json"
        if not raw_path.is_file() or not raw_metadata_path.is_file():
            raise SystemExit("전체 데이터 탐색에 필요한 원본 Parquet 또는 메타데이터가 없습니다.")
        raw_metadata = json.loads(raw_metadata_path.read_text(encoding="utf-8"))
        raw_count = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [str(raw_path)]
        ).fetchone()[0]
        raw_columns = connection.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(raw_path)]
        ).fetchall()
        if raw_count != raw_metadata["row_count"]:
            raise SystemExit("전체 데이터의 행 수가 원본 메타데이터와 다릅니다.")
        if [(column[0], column[1]) for column in raw_columns] != [
            (column["name"], column["type"]) for column in raw_metadata["columns"]
        ]:
            raise SystemExit("전체 데이터의 열 구성이 원본 메타데이터와 다릅니다.")
        if raw_path.stat().st_size != raw_metadata["parquet_bytes"]:
            raise SystemExit("전체 데이터의 파일 크기가 기록과 다릅니다.")
        with raw_path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != raw_metadata["parquet_sha256"]:
                raise SystemExit("전체 데이터 파일의 SHA256이 기록과 다릅니다.")
        if raw_metadata["source_sha256"] != snapshot["metadata"]["source_sha256"]:
            raise SystemExit("전체 데이터와 요약 집계가 서로 다른 원본에서 생성되었습니다.")
    analytics_path = folder / "public" / "data" / "analytics.parquet"
    analytics_metadata = json.loads(analytics_path.with_name("analytics_metadata.json").read_text(encoding="utf-8"))
    with analytics_path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != analytics_metadata["parquet_sha256"]:
            raise SystemExit("사업장 분석 자료의 파일 검증값이 다릅니다.")
    if analytics_path.stat().st_size != analytics_metadata["parquet_bytes"]:
        raise SystemExit("사업장 분석 자료의 파일 크기가 다릅니다.")
    if analytics_metadata["source_sha256"] != snapshot["metadata"]["source_sha256"]:
        raise SystemExit("추정 연봉 분석과 요약 자료의 원본이 서로 다릅니다.")
    with duckdb.connect() as connection:
        metrics = list(analytics_metadata["totals"])
        values = connection.execute("SELECT COUNT(*), SUM(subscribers), SUM(billing), SUM(new), SUM(lost) FROM read_parquet(?)", [str(analytics_path)]).fetchone()
        if dict(zip(["workplaces", "subscribers", "billing", "new", "lost"], values)) != snapshot["metadata"]["totals"]:
            raise SystemExit("추정 연봉 분석의 전체 행·지표 합계가 원본과 다릅니다.")
    for filename in ("app.py", "explorer.py"):
        subprocess.run(
            [sys.executable, "-m", "marimo", "check", str(folder / filename)],
            check=True,
        )
    output = folder / "dist"
    # 세 화면이 모두 완성된 뒤에만 기존 미리보기를 교체한다.
    with tempfile.TemporaryDirectory(prefix=".build-", dir=folder) as temporary:
        staged_output = Path(temporary) / "site"
        export_notebook(folder / "app.py", staged_output, "run")
        export_notebook(folder / "app.py", staged_output / "editor", "edit")
        export_notebook(folder / "explorer.py", staged_output / "explorer", "run", raw_data=True)
        if output.exists():
            shutil.rmtree(output)
        shutil.move(str(staged_output), output)
    print("정적 대시보드 생성 완료: dashboard/dist")
    print("브라우저 편집 노트북 생성 완료: dashboard/dist/editor")
    print("전체 데이터 탐색 화면 생성 완료: dashboard/dist/explorer")


if __name__ == "__main__":
    main()
