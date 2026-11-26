# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo", "altair", "duckdb"]
# ///

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="full", app_title="국민연금 사업장 분석", sql_output="native")


@app.cell
def _():
    import csv
    import io
    import json
    import sys
    from pathlib import Path
    from time import perf_counter
    from collections import defaultdict
    from html import escape

    import altair as alt
    import duckdb
    import marimo as mo

    return Path, alt, csv, duckdb, escape, io, json, mo, perf_counter, sys


@app.cell
async def _(Path, duckdb, json, mo, sys):
    _root = mo.notebook_location() / "public" / "data"
    if sys.platform == "emscripten":
        from pyodide.http import pyfetch

        _response = await pyfetch(str(_root / "metadata.json"))
        _parquet_response = await pyfetch(str(_root / "snapshot.parquet"))
        if not _response.ok or not _parquet_response.ok:
            raise RuntimeError("집계 데이터를 불러오지 못했습니다. 페이지를 새로고침해 주세요.")
        metadata = await _response.json()
        _parquet_path = Path("workplaces.parquet")
        _parquet_path.write_bytes(await _parquet_response.bytes())
    else:
        metadata = json.loads((_root / "metadata.json").read_text(encoding="utf-8"))
        _parquet_path = _root / "snapshot.parquet"
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE workplaces AS SELECT * FROM read_parquet(?)", [str(_parquet_path)])

    def query_rows(query, parameters=None):
        cursor = connection.execute(query, parameters or [])
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    source_rows = query_rows("SELECT DISTINCT region, status, kind, industry_code, industry FROM workplaces")
    return connection, metadata, query_rows, source_rows


@app.cell
def _(mo):
    reset_button = mo.ui.button(value=0, on_click=lambda value: value + 1, label="탐색 조건 초기화", full_width=True)
    return (reset_button,)


@app.cell
def _(metadata, mo, reset_button, source_rows):
    _reset = reset_button.value
    period_filter = mo.ui.dropdown(metadata["periods"], value=metadata["periods"][-1], label="자료 기준월", full_width=True)
    region_filter = mo.ui.dropdown(["전체", *sorted({r["region"] for r in source_rows})], value="전체", label="지역 · 원본 표기", searchable=True, full_width=True)
    status_filter = mo.ui.dropdown(["전체", *sorted({r["status"] for r in source_rows})], value="전체", label="가입 상태", full_width=True)
    kind_filter = mo.ui.dropdown(["전체", *sorted({r["kind"] for r in source_rows})], value="전체", label="사업장 형태", full_width=True)
    industry_options = {"전체": "전체"}
    industry_options.update({f"{r['industry']} [{r['industry_code']}]": r["industry_code"] for r in sorted(source_rows, key=lambda r: (r["industry"], r["industry_code"]))})
    industry_filter = mo.ui.dropdown(industry_options, value="전체", label="업종 · 전체 업종 검색", searchable=True, full_width=True)
    band_filter = mo.ui.dropdown(["전체", *metadata["size_bands"]], value="전체", label="사업장 가입자 규모", full_width=True)
    metric_filter = mo.ui.dropdown({"가입자 수": "subscribers", "사업장 수": "workplaces", "당월 고지금액": "billing"}, value="가입자 수", label="차트 비교 지표", full_width=True)
    mo.sidebar(
        mo.vstack([
            mo.Html('<div class="sidebar-brand"><span class="brand-symbol">연금</span><div><strong>국민연금 사업장</strong><small>공공데이터 분석</small></div></div>'),
            mo.md("### 탐색 조건"),
            period_filter, region_filter, status_filter, kind_filter, industry_filter, band_filter,
            mo.md("---"), metric_filter, reset_button,
        ], gap=0.8),
        footer=mo.md("[원본 데이터 ↗](https://www.data.go.kr/data/15083277/fileData.do) · 국민연금공단"),
        width=290,
    )
    return band_filter, industry_filter, kind_filter, metric_filter, period_filter, region_filter, status_filter


@app.cell
def _(escape, metadata, mo):
    mo.vstack([
        mo.Html('''<style>
        :root { --analysis-panel:#fff; --analysis-bg:#f5f7fb; --analysis-text:#17243b; --analysis-muted:#64748b; --analysis-line:#e3e9f2; --analysis-blue:#2563eb; }
        html.dark { --analysis-panel:#182234; --analysis-bg:#101827; --analysis-text:#edf2fa; --analysis-muted:#a1b0c4; --analysis-line:#334155; --analysis-blue:#8ab4ff; }
        body { background:var(--analysis-bg); }
        .analysis-heading { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:4px 0 8px; color:var(--analysis-text); }
        .analysis-heading h1 { font-size:29px; font-weight:750; margin:0 0 10px; letter-spacing:-.8px; }
        .analysis-heading p { color:var(--analysis-muted); margin:0; font-size:13px; }
        .period-badge { background:var(--analysis-panel); border:1px solid var(--analysis-line); border-radius:9px; padding:10px 15px; font-size:13px; white-space:nowrap; }
        .sidebar-brand { display:flex; align-items:center; gap:12px; margin:10px 0 22px; color:var(--analysis-text); }
        .brand-symbol { display:grid; place-items:center; border-radius:11px; background:#2563eb; color:white; width:43px; height:43px; font-size:14px; font-weight:750; }
        .sidebar-brand strong { display:block; font-size:17px; letter-spacing:-.4px; }
        .sidebar-brand small { display:block; color:var(--analysis-muted); font-size:12px; margin-top:3px; }
        .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }
        .metric-card { background:var(--analysis-panel); border:1px solid var(--analysis-line); border-radius:12px; padding:20px; color:var(--analysis-text); min-width:0; }
        .metric-label { font-size:13px; font-weight:600; color:var(--analysis-muted); margin-bottom:12px; }
        .metric-value { font-size:27px; line-height:1.3; font-weight:760; letter-spacing:-.7px; font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
        .metric-value small { font-size:14px; font-weight:500; letter-spacing:0; }
        .metric-note { color:var(--analysis-muted); font-size:11px; line-height:1.5; margin-top:9px; }
        .scope-line { display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; color:var(--analysis-muted); font-size:12px; padding:0 1px; }
        .scope-line b { color:var(--analysis-blue); }
        .panel-title { color:var(--analysis-text); font-size:17px; font-weight:700; margin:0; letter-spacing:-.4px; }
        .panel-note { color:var(--analysis-muted); font-size:12px; margin:4px 0 0; line-height:1.6; }
        .feature-steps { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
        .feature-step { padding:16px; border-radius:10px; border:1px solid var(--analysis-line); background:var(--analysis-panel); color:var(--analysis-text); font-size:13px; }
        .feature-step b { display:block; margin-bottom:7px; }
        .feature-step p { margin:0; color:var(--analysis-muted); line-height:1.7; }
        @media(max-width:1100px) { .metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .metric-value { font-size:25px; } }
        @media(max-width:600px) { .analysis-heading { align-items:flex-start; flex-direction:column; } .analysis-heading h1 { font-size:24px; } .metric-grid { gap:8px; } .metric-card { padding:14px; } .metric-value { font-size:21px; } .feature-steps { grid-template-columns:1fr; } }
        </style>'''),
        mo.Html(f'''<div class="analysis-heading"><div><h1>국민연금 사업장 분석</h1><p>지역·업종·규모별 공개 사업장 현황</p></div><div class="period-badge">자료 기준 <strong>{escape(', '.join(metadata['periods']))}</strong> &nbsp;·&nbsp; 게시 {escape(metadata['source_published_at'])}</div></div>'''),
    ], gap=0)


@app.cell
def _(band_filter, connection, industry_filter, kind_filter, perf_counter, period_filter, query_rows, region_filter, status_filter):
    _started = perf_counter()
    _clauses = ["period = ?"]
    _parameters = [period_filter.value]
    for _column, _widget in [("region",region_filter),("status",status_filter),("kind",kind_filter),("industry_code",industry_filter),("size_band",band_filter)]:
        if _widget.value != "전체":
            _clauses.append(f"{_column} = ?")
            _parameters.append(_widget.value)
    connection.execute("CREATE OR REPLACE TEMP TABLE selection AS SELECT * FROM workplaces WHERE " + " AND ".join(_clauses), _parameters)
    metrics = ("workplaces", "subscribers", "billing", "new", "lost")
    totals = query_rows("SELECT " + ", ".join(f"CAST(COALESCE(SUM({k}),0) AS BIGINT) AS {k}" for k in metrics) + " FROM selection")[0]
    filtered_rows = query_rows("SELECT * FROM selection ORDER BY region, industry, size_band")
    filter_elapsed_ms = (perf_counter() - _started) * 1000
    return filter_elapsed_ms, filtered_rows, metrics, totals


@app.cell
def _(band_filter, escape, filter_elapsed_ms, industry_filter, kind_filter, metadata, mo, region_filter, status_filter, totals):
    _scope = " · ".join([str(region_filter.value), str(status_filter.value), str(kind_filter.value), str(band_filter.value)])
    if industry_filter.value != "전체":
        _scope += f" · 업종 {industry_filter.value}"
    _coverage = totals['workplaces'] / metadata['totals']['workplaces'] * 100 if metadata['totals']['workplaces'] else 0
    mo.vstack([
        mo.Html(f'<div class="scope-line"><span>현재 조건 &nbsp;<b>{escape(_scope)}</b></span><span>공개 사업장 행의 {_coverage:,.1f}% 선택 &nbsp;·&nbsp; SQL 조회 {filter_elapsed_ms:,.0f}ms</span></div>'),
        mo.Html(f'''<div class="metric-grid">
        <div class="metric-card"><div class="metric-label">사업장 수</div><div class="metric-value">{totals['workplaces']:,}<small> 개</small></div><div class="metric-note">원본 사업장 행 수</div></div>
        <div class="metric-card"><div class="metric-label">가입자 수</div><div class="metric-value">{totals['subscribers']:,}<small> 명</small></div><div class="metric-note">사업장별 가입자 합계</div></div>
        <div class="metric-card"><div class="metric-label">당월 고지금액</div><div class="metric-value">{totals['billing']/100_000_000:,.1f}<small> 억 원</small></div><div class="metric-note">실제 소득과 다를 수 있음</div></div>
        <div class="metric-card"><div class="metric-label">신규취득 / 상실</div><div class="metric-value" style="font-size:22px">{totals['new']:,} / {totals['lost']:,}<small> 명</small></div><div class="metric-note">납부재개 / 납부예외 포함</div></div>
        </div>'''),
        mo.md("<small>공개 범위: 가입자 3인 이상 법인·10인 이상 개인(2025년 7월 이후). 원본에 포함된 탈퇴·0명 행을 보존했습니다. 전체 고용 통계와 다릅니다.</small>"),
    ], gap=0.8)


@app.cell
def _(alt, escape, filtered_rows, metric_filter, metrics, mo, query_rows):
    metric_key = metric_filter.value
    metric_labels = {"subscribers": "가입자 수", "workplaces": "사업장 수", "billing": "당월 고지금액"}
    metric_units = {"subscribers": "명", "workplaces": "개", "billing": "억 원"}
    metric_divisor = 100_000_000 if metric_key == "billing" else 1

    def rollup(dimension):
        rows = query_rows(f'SELECT {dimension} AS "항목", ' + ", ".join(f"CAST(SUM({k}) AS BIGINT) AS {k}" for k in metrics) + f" FROM selection GROUP BY {dimension}")
        return [{**row, "값": row[metric_key] / metric_divisor} for row in rows]

    def bar_chart(rows, color="#2563eb", height=350, order=None):
        return (alt.Chart(alt.Data(values=rows)).mark_bar(color=color, cornerRadiusEnd=3).encode(
            x=alt.X("값:Q", title=metric_units[metric_key], axis=alt.Axis(format=",~s"), scale=alt.Scale(zero=True)),
            y=alt.Y("항목:N", sort=order if order is not None else "-x", title=None, axis=alt.Axis(labelLimit=185, labelFontSize=11)),
            tooltip=[alt.Tooltip("항목:N", title="구분"), alt.Tooltip("workplaces:Q", title="사업장 수(개)", format=","), alt.Tooltip("subscribers:Q", title="가입자 수(명)", format=","), alt.Tooltip("billing:Q", title="고지금액(원)", format=",")],
        ).properties(height=height, width="container").configure_view(stroke=None).configure_axis(labelFontSize=11, titleFontSize=11, gridColor="#e7ecf3"))

    def panel(title, content, note=""):
        return mo.vstack([
            mo.Html(f'<div><h2 class="panel-title">{escape(title)}</h2>' + (f'<p class="panel-note">{escape(note)}</p>' if note else '') + '</div>'), content,
        ], gap=1).style({"background":"var(--analysis-panel)","border":"1px solid var(--analysis-line)","border-radius":"12px","padding":"20px","min-width":"0"})

    region_rows = rollup("region")
    industry_rows = sorted(rollup("industry"), key=lambda r: r[metric_key], reverse=True)
    band_rows = rollup("size_band")
    return band_rows, bar_chart, industry_rows, metric_key, metric_labels, panel, region_rows


@app.cell
def _(alt, band_rows, bar_chart, filtered_rows, industry_rows, metadata, metric_key, metric_labels, mo, panel, region_rows):
    if not filtered_rows:
        overview = mo.callout("선택한 조건에 해당하는 사업장이 없습니다. 탐색 조건을 초기화하거나 범위를 넓혀 주세요.", kind="info")
    else:
        _height = max(350, len(region_rows) * 23)
        _flow_rows = [{"지역": r["항목"], "구분": label, "인원": r[key]} for r in region_rows for label, key in [("신규취득", "new"), ("상실", "lost")]]
        _flow_chart = (alt.Chart(alt.Data(values=_flow_rows)).mark_bar(cornerRadiusEnd=2).encode(
            x=alt.X("인원:Q", title="명", axis=alt.Axis(format=",~s"), scale=alt.Scale(zero=True)),
            y=alt.Y("지역:N", sort=alt.EncodingSortField(field="인원", op="sum", order="descending"), title=None, axis=alt.Axis(labelLimit=180)),
            yOffset="구분:N", color=alt.Color("구분:N", scale=alt.Scale(domain=["신규취득", "상실"], range=["#2563eb", "#94a3b8"]), legend=alt.Legend(orient="top", title=None)),
            tooltip=["지역:N", "구분:N", alt.Tooltip("인원:Q", title="인원(명)", format=",")],
        ).properties(height=max(350, len(region_rows) * 27), width="container").configure_view(stroke=None))
        overview = mo.vstack([
            mo.hstack([
                panel(f"지역별 {metric_labels[metric_key]}", mo.ui.altair_chart(bar_chart(region_rows, height=_height), chart_selection=False, legend_selection=False), "지역명·코드는 원본 표기 기준"),
                panel(f"업종별 {metric_labels[metric_key]} · 상위 12개", mo.ui.altair_chart(bar_chart(industry_rows[:12], "#0d9488", _height), chart_selection=False, legend_selection=False), f"선택 조건의 {len(industry_rows):,}개 업종 중 상위 항목"),
            ], widths="equal", wrap=True, align="start", gap=1),
            mo.hstack([
                panel(f"사업장 규모별 {metric_labels[metric_key]}", mo.ui.altair_chart(bar_chart(band_rows, "#6366f1", 350, metadata["size_bands"]), chart_selection=False, legend_selection=False)),
                panel("지역별 신규취득·상실", mo.ui.altair_chart(_flow_chart, chart_selection=False, legend_selection=False), "납부 상태 변화가 포함되므로 채용·퇴사 인원과 다릅니다."),
            ], widths="equal", wrap=True, align="start", gap=1),
        ], gap=1)
    return (overview,)


@app.cell
def _(csv, filtered_rows, io, mo, panel):
    _columns = {"period":"자료 기준월","region":"지역","status":"가입 상태","kind":"사업장 형태","industry_code":"업종코드","industry":"업종","size_band":"가입자 규모","workplaces":"사업장 수","subscribers":"가입자 수","billing":"당월 고지금액(원)","new":"신규취득자 수","lost":"상실가입자 수"}
    _records = [{label: row[key] for key, label in _columns.items()} for row in filtered_rows]
    _csv_buffer = io.StringIO()
    _writer = csv.DictWriter(_csv_buffer, fieldnames=list(_columns.values()))
    _writer.writeheader()
    _writer.writerows(_records)
    detail = panel("선택 조건의 집계 데이터", mo.vstack([
        mo.hstack([mo.md(f"**{len(_records):,}개 집계행** · 표 검색·열 정렬 지원"), mo.download(_csv_buffer.getvalue().encode("utf-8-sig"), filename="국민연금_선택조건_집계.csv", mimetype="text/csv", label="현재 조건 전체 CSV 내려받기")], wrap=True),
        mo.ui.table(_records, pagination=True, page_size=20, selection=None, show_download=False, show_column_summaries=False, show_data_types=False, label="필터가 적용된 전체 집계", max_height=640),
    ]), "한 행은 기준월·지역·가입 상태·형태·업종·가입자 규모의 조합입니다. 원본 개별 사업장 목록과 다릅니다.")
    return (detail,)


@app.cell
def _(mo):
    demo_top = mo.ui.slider(start=3, stop=20, step=1, value=8, label="연동할 상위 업종 수", show_value=True, full_width=True)
    return (demo_top,)


@app.cell
def _(bar_chart, demo_top, industry_rows, mo):
    demo_rows = industry_rows[:demo_top.value]
    demo_chart = mo.ui.altair_chart(bar_chart(demo_rows, "#2563eb", 370), chart_selection="point", legend_selection=False, label="막대를 클릭해 업종 선택")
    return demo_chart, demo_rows


@app.cell
def _(connection, mo, totals):
    _scope_dependency = totals
    _result = mo.sql(
        """
        SELECT region, SUM(workplaces)::BIGINT AS workplaces,
               SUM(subscribers)::BIGINT AS subscribers
        FROM selection
        GROUP BY region
        ORDER BY subscribers DESC
        LIMIT 5
        """,
        engine=connection,
        output=False,
    )
    demo_native_sql = [dict(zip(["지역", "사업장 수", "가입자 수"], row)) for row in _result.fetchall()]
    return (demo_native_sql,)


@app.cell
def _(demo_chart, demo_native_sql, demo_rows, demo_top, mo, panel):
    _indices = set()
    _names = set()
    for _selection in demo_chart.selections.values():
        _indices.update(int(value) - 1 for value in _selection.get("_vgsid_", []))
        _names.update(_selection.get("항목", []))
        for _point in _selection.get("vlPoint", {}).get("or", []):
            if "_vgsid_" in _point:
                _indices.add(int(_point["_vgsid_"]) - 1)
            if "항목" in _point:
                _names.add(_point["항목"])
    _selection = [row for index, row in enumerate(demo_rows) if index in _indices or row["항목"] in _names]
    _selected = [{"업종":r["항목"],"사업장 수":r["workplaces"],"가입자 수":r["subscribers"],"당월 고지금액(원)":r["billing"]} for r in _selection]
    marimo_demo = mo.vstack([
        mo.Html('''<div class="feature-steps"><div class="feature-step"><b>1. 슬라이더를 움직이세요</b><p>바뀐 입력을 사용하는 셀만 자동 재실행됩니다. 화면의 업종 수와 차트가 함께 갱신됩니다.</p></div><div class="feature-step"><b>2. 차트 막대를 클릭하세요</b><p>선택한 차트 데이터가 Python 변수로 전달되고 아래 표에 연결됩니다. Shift와 클릭으로 여러 업종을 선택하세요.</p></div><div class="feature-step"><b>3. 코드를 확인하세요</b><p>UI와 차트·표를 하나의 Python 파일로 관리합니다. 로컬 편집 시 셀의 의존관계를 따라 결과가 갱신됩니다.</p></div></div>'''),
        panel("반응형 셀과 차트·표 연동", mo.vstack([
            demo_top, mo.md(f"현재 **상위 {demo_top.value}개 업종**을 표시합니다. 왼쪽 탐색 조건도 함께 적용됩니다."), demo_chart,
            mo.md(f"**선택한 업종 {len(_selected)}개**"),
            mo.ui.table(_selected, selection=None, show_column_summaries=False, show_data_types=False, label="차트 선택과 연결된 표") if _selected else mo.callout("차트의 막대를 클릭하면 해당 업종의 수치가 여기에 나타납니다. 빈 공간을 두 번 클릭하면 선택이 해제됩니다.", kind="neutral"),
        ])),
        panel("화면을 만드는 핵심 코드", mo.md('''```python
# 첫 번째 셀: 입력 위젯
업종수 = mo.ui.slider(start=3, stop=20, value=8)

# 두 번째 셀: 입력 변경 시 이 차트 셀을 자동 실행
연동차트 = mo.ui.altair_chart(차트, chart_selection="point")

# 세 번째 셀: 차트 선택이 바뀌면 표 셀을 자동 실행
# 차트의 선택 상태를 받아 업종과 연결
선택상태 = 연동차트.selections
mo.ui.table(선택한업종)
```'''), "실제 앱은 왼쪽 조건으로 집계한 업종에서 슬라이더 값만큼 선택해 차트를 그립니다."),
        panel("Python과 SQL을 같은 노트북에서", mo.hstack([
            mo.md('```python\n결과 = mo.sql(\n    "SELECT region, SUM(subscribers)\\n"\n    "FROM selection GROUP BY region",\n    engine=연결, output=False\n)\n```'),
            mo.ui.table(demo_native_sql, selection=None, show_column_summaries=False, show_data_types=False, show_download=False, label="현재 조건의 가입자 상위 5개 지역"),
        ], widths="equal", wrap=True), "실제 mo.sql 셀이 같은 DuckDB 연결을 사용합니다. 왼쪽 조건을 바꾸면 SQL 결과도 갱신됩니다."),
        mo.callout("이 페이지의 Python은 Pyodide로 브라우저에서 실행됩니다. 운영용 Python 서버 없이 GitHub Pages에 배포할 수 있습니다. 최초 실행에는 런타임과 패키지 다운로드가 필요합니다.", kind="info"),
    ], gap=1)
    return (marimo_demo,)


@app.cell
def _(mo):
    sql_presets = {
        "지역별 가입자": 'SELECT region AS "지역", SUM(workplaces) AS "사업장 수", SUM(subscribers) AS "가입자 수"\nFROM selection\nGROUP BY region ORDER BY "가입자 수" DESC',
        "업종별 평균 가입자": 'SELECT industry AS "업종", SUM(workplaces) AS "사업장 수",\n ROUND(SUM(subscribers) * 1.0 / NULLIF(SUM(workplaces), 0), 1) AS "사업장 평균 가입자"\nFROM selection GROUP BY industry HAVING SUM(workplaces) >= 100\nORDER BY "사업장 평균 가입자" DESC LIMIT 30',
        "규모별 가입자 비중": 'SELECT size_band AS "가입자 규모", SUM(workplaces) AS "사업장 수",\n SUM(subscribers) AS "가입자 수",\n ROUND(100.0 * SUM(subscribers) / NULLIF(SUM(SUM(subscribers)) OVER (), 0), 2) AS "가입자 비중(%)"\nFROM selection GROUP BY size_band ORDER BY "가입자 수" DESC',
    }
    sql_preset = mo.ui.dropdown(list(sql_presets), value="지역별 가입자", label="SQL 예제", full_width=True)
    return sql_preset, sql_presets


@app.cell
def _(mo, sql_preset, sql_presets):
    sql_editor = mo.ui.code_editor(sql_presets[sql_preset.value], language="sql", min_height=180, max_height=360).form(submit_button_label="SQL 실행", show_clear_button=True, clear_button_label="입력 지우기")
    return (sql_editor,)


@app.cell
def _(connection, csv, io, mo, panel, perf_counter, sql_editor, sql_preset, totals):
    _scope_dependency = totals
    _result_content = mo.callout("예제를 선택하거나 SQL을 편집한 뒤 실행하세요. selection은 왼쪽 조건, workplaces는 전체 집계입니다.", kind="neutral")
    if sql_editor.value:
        try:
            _statements = connection.extract_statements(sql_editor.value)
            if len(_statements) != 1 or str(_statements[0].type) != "StatementType.SELECT":
                raise ValueError("SELECT 또는 WITH로 시작하는 조회문 한 개만 실행할 수 있습니다.")
            _query = _statements[0].query.strip().rstrip(";")
            _start = perf_counter()
            _cursor = connection.execute("SELECT * FROM (" + _query + ") AS result LIMIT 3001")
            _columns = [c[0] for c in _cursor.description]
            _result = _cursor.fetchall()
            _elapsed = (perf_counter() - _start) * 1000
            _truncated = len(_result) > 3000
            _result = _result[:3000]
            _records = [dict(zip(_columns, row)) for row in _result]
            _buffer = io.StringIO()
            _writer = csv.writer(_buffer)
            _writer.writerow(_columns)
            _writer.writerows(_result)
            _plan = connection.execute("EXPLAIN " + _query).fetchall()
            _result_content = mo.vstack([
                mo.hstack([mo.md(f"**{len(_records):,}행** · 실행 **{_elapsed:,.1f}ms**" + (" · 미리보기 상한 3,000행에 도달했습니다." if _truncated else "")), mo.download(_buffer.getvalue().encode("utf-8-sig"), filename="국민연금_SQL결과.csv", mimetype="text/csv", label="표시된 SQL 결과 CSV")], wrap=True),
                mo.ui.table(_records, pagination=True, page_size=20, selection=None, show_column_summaries=False, show_data_types=False, show_download=False, max_height=450),
                mo.accordion({"DuckDB 실행계획": mo.ui.code_editor("\n".join(str(row[-1]) for row in _plan), language="text", disabled=True, min_height=150, max_height=350)}, lazy=True),
            ])
        except Exception as _error:
            _result_content = mo.callout(f"SQL을 실행하지 못했습니다: {_error}", kind="warn")
    sql_explorer = mo.vstack([
        panel("브라우저에서 실행하는 DuckDB SQL", mo.vstack([sql_preset, sql_editor, _result_content]), "selection: 현재 탐색 조건 · workplaces: 최신 집계 전체. 사업장 수는 COUNT(*)가 아닌 SUM(workplaces)입니다."),
        panel("집계 테이블의 열", mo.ui.table([
            {"열":"period / region / status / kind","의미":"기준월 / 지역 / 가입 상태 / 사업장 형태"},
            {"열":"industry_code / industry / size_band","의미":"업종코드 / 업종명 / 가입자 규모 구간"},
            {"열":"workplaces / subscribers / billing","의미":"사업장 행 수 / 가입자 수 / 고지금액(원)"},
            {"열":"new / lost","의미":"신규취득자 수 / 상실가입자 수"},
        ], selection=None, show_download=False, show_column_summaries=False, show_data_types=False)),
    ], gap=1)
    return (sql_explorer,)


@app.cell
def _(json, metadata, mo, panel):
    source_detail = panel("출처와 집계 기준", mo.vstack([
        mo.md(f"[국민연금공단 · 국민연금 가입 사업장 내역](https://www.data.go.kr/data/15083277/fileData.do) · 원본 게시 **{metadata['source_published_at']}** · 수집 **{metadata['collected_at']}**"),
        mo.md("이 페이지는 수집한 파일의 스냅샷입니다. 원본 제공기관의 다음 게시가 자동 반영되지는 않습니다."),
        mo.md("\n\n".join(metadata[key] for key in ["coverage_note","record_note","region_note","period_note","billing_note","flow_note"])),
        mo.accordion({"원본 품질·검증 메타데이터": mo.ui.code_editor(json.dumps(metadata, ensure_ascii=False, indent=2), language="json", disabled=True, min_height=220, max_height=480)}, lazy=True),
    ]))
    return (source_detail,)


@app.cell
def _(detail, marimo_demo, mo, overview, source_detail, sql_explorer):
    mo.ui.tabs({"현황 비교":overview,"집계 데이터":detail,"SQL 탐색":sql_explorer,"마리모 기능 체험":marimo_demo,"출처·품질":source_detail}, lazy=True)


if __name__ == "__main__":
    app.run()
