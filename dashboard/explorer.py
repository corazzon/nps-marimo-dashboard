# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo", "duckdb"]
# ///

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="full", app_title="국민연금 전체 데이터 탐색", sql_output="native")


@app.cell
def _():
    import csv
    import io
    import json
    import sys
    from pathlib import Path
    from time import perf_counter
    from html import escape

    import duckdb
    import marimo as mo

    return Path, csv, duckdb, escape, io, json, mo, perf_counter, sys


@app.cell
async def _(json, mo, sys):
    data_root = mo.notebook_location() / "public" / "data"
    if sys.platform == "emscripten":
        from pyodide.http import pyfetch as _pyfetch

        _response = await _pyfetch(str(data_root / "raw_metadata.json"))
        if not _response.ok:
            raise RuntimeError("전체 데이터의 출처 정보를 불러오지 못했습니다.")
        raw_metadata = await _response.json()
    else:
        raw_metadata = json.loads((data_root / "raw_metadata.json").read_text(encoding="utf-8"))
    return data_root, raw_metadata


@app.cell
def _(mo, raw_metadata):
    load_raw = mo.ui.run_button(label=f"전체 데이터 불러오기 · {raw_metadata['parquet_bytes'] / 1_000_000:,.1f}MB", kind="success", full_width=True)
    return (load_raw,)


@app.cell
async def _(Path, data_root, duckdb, load_raw, mo, perf_counter, sys):
    raw_connection = None
    load_elapsed_ms = None
    load_error = None
    if load_raw.value:
        _start = perf_counter()
        try:
            if sys.platform == "emscripten":
                from pyodide.http import pyfetch as _pyfetch

                _response = await _pyfetch(str(data_root / "raw.parquet"))
                if not _response.ok:
                    raise RuntimeError("전체 데이터 파일을 받지 못했습니다.")
                _path = Path("raw_workplaces.parquet")
                _path.write_bytes(await _response.bytes())
            else:
                _path = data_root / "raw.parquet"
            raw_connection = duckdb.connect(":memory:")
            raw_connection.execute("CREATE TABLE raw_workplaces AS SELECT * FROM read_parquet(?)", [str(_path)])
            load_elapsed_ms = (perf_counter() - _start) * 1000
        except Exception as _error:
            raw_connection = None
            load_error = str(_error)
    return load_elapsed_ms, load_error, raw_connection


@app.cell
def _(escape, load_elapsed_ms, load_error, load_raw, mo, raw_connection, raw_metadata):
    _loaded = raw_connection is not None
    _title = f"{raw_metadata['row_count']:,}행 × {raw_metadata['column_count']}열"
    _status = f"전체 데이터 준비 완료 · {load_elapsed_ms / 1000:,.1f}초" if _loaded else "집계 전 원본의 모든 행과 22개 열을 탐색합니다."
    mo.vstack([
        mo.Html(f'''<div style="background:linear-gradient(115deg,#14294d,#244fa7);border-radius:18px;padding:28px 32px;color:white"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px"><div><div style="font-size:13px;color:#bdcff3;margin-bottom:8px">국민연금 공개 사업장 데이터 · {escape(', '.join(raw_metadata['periods']))}</div><h1 style="font-size:29px;font-weight:750;margin:0;color:white">전체 데이터 탐색</h1><p style="font-size:14px;color:#dce7fb;margin:10px 0 0">{escape(_title)} · 사업장명·공개 주소·원본 지표 조회</p></div><a href="../" target="_top" style="border:1px solid #7694c7;border-radius:9px;padding:11px 17px;color:white;text-decoration:none;font-size:14px">대시보드로 돌아가기 ↗</a></div></div>'''),
        mo.hstack([mo.md(f"**{_status}**"), mo.md(f"원본 게시 {raw_metadata['source_published_at']} · 기준월 {', '.join(raw_metadata['periods'])}")], wrap=True),
        mo.callout(load_error, kind="warn") if load_error else (mo.callout("아래 버튼을 눌렀을 때만 전체 Parquet 파일을 받습니다. 준비 후에는 모든 행에 검색·슬라이드바·SQL을 적용하며 화면에는 현재 페이지의 행만 표시합니다.", kind="neutral") if not _loaded else mo.md("")),
        load_raw if not _loaded else mo.md(""),
    ], gap=1)


@app.cell
def _(mo):
    reset_raw = mo.ui.button(value=0, on_click=lambda value: value + 1, label="검색·슬라이드바 초기화", full_width=True)
    return (reset_raw,)


@app.cell
def _(mo, raw_connection, raw_metadata, reset_raw):
    _reset = reset_raw.value
    _disabled = raw_connection is None
    search_raw = mo.ui.text(value="", label="사업장명·주소·사업자등록번호 검색", placeholder="예: 삼성, 금천구, 가산동", full_width=True, disabled=_disabled).form(bordered=False, submit_button_label="전체 행에서 검색", show_clear_button=True, clear_button_label="검색 지우기")
    region_options = {"전체": "전체", **{row["name"]: row["code"] for row in raw_metadata["regions"]}}
    region_raw = mo.ui.dropdown(region_options, value="전체", searchable=True, label="지역 · 원본 시도코드", full_width=True, disabled=_disabled)
    status_raw = mo.ui.dropdown({"전체": "전체", "등록": "1", "탈퇴": "2"}, value="전체", label="가입 상태", full_width=True, disabled=_disabled)
    kind_raw = mo.ui.dropdown({"전체": "전체", "법인": "1", "개인": "2"}, value="전체", label="사업장 형태", full_width=True, disabled=_disabled)
    subscriber_range = mo.ui.range_slider(start=0, stop=raw_metadata["max_subscribers"], step=1, value=[0, raw_metadata["max_subscribers"]], debounce=True, show_value=True, full_width=True, disabled=_disabled, label="가입자 수 범위 슬라이드바 · 두 손잡이로 최소/최대 지정")
    page_size_raw = mo.ui.dropdown({"50행": 50, "100행": 100, "200행": 200}, value="50행", label="페이지당 표시 행", full_width=True, disabled=_disabled)
    sort_raw = mo.ui.dropdown({"원본 순서": "rowid", "가입자 많은 순": '"가입자수" DESC, rowid', "고지금액 많은 순": '"당월고지금액" DESC, rowid'}, value="원본 순서", label="정렬", full_width=True, disabled=_disabled)
    return kind_raw, page_size_raw, region_raw, search_raw, sort_raw, status_raw, subscriber_range


@app.cell
def _(kind_raw, page_size_raw, perf_counter, raw_connection, region_raw, search_raw, status_raw, subscriber_range):
    raw_where = '"가입자수" BETWEEN ? AND ?'
    raw_parameters = list(subscriber_range.value)
    for _column, _widget in [('법정동주소광역시도코드',region_raw),('사업장가입상태코드 1 등록 2 탈퇴',status_raw),('사업장형태구분코드 1 법인 2 개인',kind_raw)]:
        if _widget.value != "전체":
            raw_where += f' AND "{_column}" = ?'
            raw_parameters.append(_widget.value)
    _search = (search_raw.value or "").strip()
    if _search:
        raw_where += ' AND (contains(COALESCE("사업장명", \'\'), ?) OR contains(COALESCE("사업장지번상세주소", \'\'), ?) OR contains(COALESCE("사업장도로명상세주소", \'\'), ?) OR contains(COALESCE("사업자등록번호", \'\'), ?))'
        raw_parameters.extend([_search] * 4)
    matched_raw = 0
    count_elapsed_ms = None
    if raw_connection is not None:
        _start = perf_counter()
        matched_raw = raw_connection.execute("SELECT count(*) FROM raw_workplaces WHERE " + raw_where, raw_parameters).fetchone()[0]
        count_elapsed_ms = (perf_counter() - _start) * 1000
    page_count_raw = max(1, (matched_raw + page_size_raw.value - 1) // page_size_raw.value)
    return count_elapsed_ms, matched_raw, page_count_raw, raw_parameters, raw_where


@app.cell
def _(mo, page_count_raw, raw_connection):
    page_slider_raw = mo.ui.slider(start=1, stop=max(2, page_count_raw), step=1, value=1, debounce=True, disabled=raw_connection is None or page_count_raw == 1, show_value=True, include_input=True, full_width=True, label=f"조회 페이지 슬라이드바 · 전체 {page_count_raw:,}페이지")
    return (page_slider_raw,)


@app.cell
def _(page_size_raw, page_slider_raw, raw_connection, raw_parameters, raw_where, sort_raw):
    raw_page = []
    raw_offset = (page_slider_raw.value - 1) * page_size_raw.value
    if raw_connection is not None:
        _cursor = raw_connection.execute("SELECT * FROM raw_workplaces WHERE " + raw_where + " ORDER BY " + sort_raw.value + " LIMIT ? OFFSET ?", [*raw_parameters, page_size_raw.value, raw_offset])
        _names = [column[0] for column in _cursor.description]
        raw_page = [dict(zip(_names, row)) for row in _cursor.fetchall()]
    return raw_offset, raw_page


@app.cell
def _(count_elapsed_ms, csv, io, kind_raw, matched_raw, mo, page_size_raw, page_slider_raw, raw_connection, raw_metadata, raw_offset, raw_page, region_raw, reset_raw, search_raw, sort_raw, status_raw, subscriber_range):
    _columns = [row["name"] for row in raw_metadata["columns"]]
    _buffer = io.StringIO()
    _writer = csv.DictWriter(_buffer, fieldnames=_columns)
    _writer.writeheader()
    _writer.writerows(raw_page)
    _count_info = f"**전체 {raw_metadata['row_count']:,}행 중 {matched_raw:,}행** · 조회 {count_elapsed_ms:,.1f}ms" if raw_connection is not None else "전체 데이터 불러오기 후 검색과 슬라이드바를 사용할 수 있습니다."
    raw_browse = mo.vstack([
        mo.vstack([
            mo.md("### 전체 원본 검색"), search_raw,
            mo.hstack([region_raw, status_raw, kind_raw], widths="equal", wrap=True),
            subscriber_range,
            mo.hstack([sort_raw, page_size_raw, reset_raw], widths="equal", wrap=True, align="end"),
        ], gap=1).style({"background":"#f7f9fc","border":"1px solid #e0e7f1","border-radius":"12px","padding":"20px"}),
        mo.hstack([mo.md(_count_info), mo.download(_buffer.getvalue().encode("utf-8-sig"), filename="국민연금_원본_현재페이지.csv", mimetype="text/csv", label="현재 페이지 CSV", disabled=not raw_page)], wrap=True),
        page_slider_raw,
        mo.md(f"**{raw_offset + 1:,}~{raw_offset + len(raw_page):,}행** 표시 · 원본 22개 열을 가로로 스크롤하여 확인할 수 있습니다.") if raw_page else mo.callout("선택 조건에 맞는 행이 없습니다. 전체 데이터를 먼저 불러오거나 검색·범위를 초기화하세요.", kind="neutral"),
        mo.ui.table(raw_page, pagination=False, selection=None, show_download=False, show_column_summaries=False, show_data_types=False, max_columns=22, max_height=650, freeze_columns_left=["자료생성년월","사업장명"], label="원본 전체 데이터의 현재 페이지") if raw_page else mo.md(""),
    ], gap=1)
    return (raw_browse,)


@app.cell
def _(mo):
    raw_sql_presets = {
        "원본 100행": 'SELECT * FROM raw_workplaces\nLIMIT 100',
        "가입자 수 상위 사업장": 'SELECT "사업장명", "사업장지번상세주소", "가입자수", "당월고지금액"\nFROM raw_workplaces\nORDER BY "가입자수" DESC LIMIT 100',
        "지역별 원본 사업장 집계": 'SELECT "법정동주소광역시도코드", COUNT(*) AS "사업장 수",\n SUM("가입자수") AS "가입자 수", SUM("당월고지금액") AS "당월 고지금액"\nFROM raw_workplaces\nGROUP BY "법정동주소광역시도코드"\nORDER BY "가입자 수" DESC',
    }
    raw_sql_preset = mo.ui.dropdown(list(raw_sql_presets), value="원본 100행", label="전체 원본 SQL 예제", full_width=True)
    return raw_sql_preset, raw_sql_presets


@app.cell
def _(mo, raw_sql_preset, raw_sql_presets):
    raw_sql_editor = mo.ui.code_editor(raw_sql_presets[raw_sql_preset.value], language="sql", min_height=190, max_height=400).form(submit_button_label="전체 원본 SQL 실행")
    return (raw_sql_editor,)


@app.cell
def _(csv, io, mo, perf_counter, raw_connection, raw_metadata, raw_sql_editor, raw_sql_preset):
    _content = mo.callout(f"raw_workplaces는 원본 전체 {raw_metadata['row_count']:,}행과 {raw_metadata['column_count']}개 열입니다. 이 SQL에는 탐색 탭의 검색·슬라이드바 조건이 자동 적용되지 않습니다.", kind="neutral")
    if raw_sql_editor.value:
        if raw_connection is None:
            _content = mo.callout("먼저 화면 상단의 ‘전체 데이터 불러오기’를 눌러 주세요.", kind="warn")
        else:
            try:
                _statements = raw_connection.extract_statements(raw_sql_editor.value)
                if len(_statements) != 1 or str(_statements[0].type) != "StatementType.SELECT":
                    raise ValueError("SELECT 또는 WITH 조회문 한 개만 실행할 수 있습니다.")
                _query = _statements[0].query.strip().rstrip(";")
                _start = perf_counter()
                _cursor = raw_connection.execute("SELECT * FROM (" + _query + ") AS result LIMIT 3001")
                _names = [column[0] for column in _cursor.description]
                _result = _cursor.fetchall()
                _elapsed = (perf_counter() - _start) * 1000
                _truncated = len(_result) > 3000
                _result = _result[:3000]
                _records = [dict(zip(_names, row)) for row in _result]
                _buffer = io.StringIO()
                _writer = csv.writer(_buffer)
                _writer.writerow(_names)
                _writer.writerows(_result)
                _content = mo.vstack([
                    mo.hstack([mo.md(f"**{len(_records):,}행** · SQL 실행 {_elapsed:,.1f}ms" + (" · 3,000행까지만 표시·다운로드합니다." if _truncated else "")), mo.download(_buffer.getvalue().encode("utf-8-sig"), filename="국민연금_원본_SQL결과.csv", mimetype="text/csv", label="표시된 SQL 결과 CSV")], wrap=True),
                    mo.ui.table(_records, pagination=True, page_size=25, selection=None, show_download=False, show_column_summaries=False, show_data_types=False, max_columns=22, max_height=650),
                ])
            except Exception as _error:
                _content = mo.callout(f"조회하지 못했습니다: {_error}", kind="warn")
    raw_sql_panel = mo.vstack([mo.md("### 원본 전체 SQL 조회"), raw_sql_preset, raw_sql_editor, _content], gap=1)
    return (raw_sql_panel,)


@app.cell
def _(mo, raw_browse, raw_metadata, raw_sql_panel):
    _schema = [{"열": row["name"], "자료형": row["type"], "원본 결측 행": row["missing"]} for row in raw_metadata["columns"]]
    mo.ui.tabs({
        "전체 데이터 탐색": raw_browse,
        "전체 원본 SQL": raw_sql_panel,
        "원본 열·출처": mo.vstack([
            mo.md("### 원본의 22개 열"),
            mo.ui.table(_schema, pagination=False, selection=None, show_download=False, show_column_summaries=False, show_data_types=False),
            mo.md(raw_metadata["publication_note"]), mo.md(raw_metadata["coverage_note"]), mo.md(raw_metadata["region_note"]),
            mo.md(f"[원본 제공기관]({raw_metadata['source_url']}) · SHA256 `{raw_metadata['source_sha256']}`"),
            mo.md(raw_metadata["verification"]),
        ], gap=1),
    }, lazy=True)


if __name__ == "__main__":
    app.run()
