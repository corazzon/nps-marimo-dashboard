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
    top_n_filter = mo.ui.slider(start=5, stop=25, step=1, value=12, label="차트에 표시할 업종 수", show_value=True, full_width=True)
    metric_filter = mo.ui.dropdown({"가입자 수": "subscribers", "사업장 수": "workplaces", "당월 고지금액": "billing"}, value="가입자 수", label="차트 비교 지표", full_width=True)
    mo.sidebar(
        mo.vstack([
            mo.Html('<div class="sidebar-brand"><span class="brand-symbol">연금</span><div><strong>국민연금 사업장</strong><small>공공데이터 분석</small></div></div>'),
            mo.md("### 탐색 조건"),
            period_filter, region_filter, status_filter, kind_filter, industry_filter, band_filter,
            mo.md("---"), metric_filter, top_n_filter, reset_button,
        ], gap=0.8),
        footer=mo.md("[원본 데이터 ↗](https://www.data.go.kr/data/15083277/fileData.do) · 국민연금공단"),
        width=290,
    )
    return band_filter, industry_filter, kind_filter, metric_filter, period_filter, region_filter, status_filter, top_n_filter


@app.cell
def _(mo, sys):
    _location = str(mo.notebook_location()).rstrip("/")
    _editing = _location.endswith("/editor")
    _prefix = "../" if _editing else "./"
    if sys.platform != "emscripten":
        _prefix = "https://corazzon.github.io/nps-marimo-dashboard/"
    page_links = {
        "dashboard": _prefix,
        "editor": _prefix + "editor/",
        "explorer": _prefix + "explorer/",
        "source": "public/notebooks/app.py",
        "editing": _editing,
    }
    return (page_links,)


@app.cell
def _(escape, metadata, mo, page_links):
    mo.vstack([
        mo.Html('''<style>
        :root { --analysis-panel:#fff; --analysis-bg:#f4f7fc; --analysis-text:#17243b; --analysis-muted:#64748b; --analysis-line:#e1e8f2; --analysis-blue:#2563eb; }
        html.dark { --analysis-panel:#182234; --analysis-bg:#101827; --analysis-text:#edf2fa; --analysis-muted:#a1b0c4; --analysis-line:#334155; --analysis-blue:#8ab4ff; }
        body { background:var(--analysis-bg); }
        .overview-hero { position:relative; overflow:hidden; padding:27px 30px; border-radius:18px; color:white; background:linear-gradient(115deg,#122441 0%,#173660 62%,#1852a0 100%); display:grid; grid-template-columns:minmax(0,1fr) auto; gap:22px; align-items:center; box-shadow:0 12px 30px #0b27581a; }
        .overview-hero:before { content:""; position:absolute; width:400px; height:400px; right:-120px; top:-210px; border:1px solid #ffffff18; border-radius:50%; box-shadow:0 0 0 40px #ffffff06,0 0 0 85px #ffffff04; pointer-events:none; }
        .hero-kicker { display:flex; gap:9px; align-items:center; color:#c5d8f5; font-size:12px; letter-spacing:.2px; margin-bottom:12px; }
        .hero-kicker span:first-child { background:#ffffff13; border:1px solid #ffffff29; border-radius:20px; padding:4px 9px; color:#e4eeff; }
        .overview-hero h1 { color:white; font-size:31px; font-weight:780; margin:0 0 9px; letter-spacing:-1px; line-height:1.3; }
        .hero-subtitle { margin:0; color:#c5d8f5; font-size:13px; line-height:1.7; }
        .hero-right { position:relative; display:flex; flex-direction:column; align-items:flex-end; gap:13px; }
        .hero-period { display:flex; gap:14px; align-items:center; }
        .hero-period span { font-size:11px; color:#b9cce9; }
        .hero-period strong { color:white; font-size:22px; letter-spacing:.3px; font-variant-numeric:tabular-nums; }
        .hero-actions { display:flex; flex-wrap:wrap; gap:8px; }
        .hero-actions a { display:inline-flex; justify-content:center; align-items:center; gap:7px; border-radius:8px; padding:10px 13px; text-decoration:none; font-size:12px; font-weight:650; border:1px solid #ffffff3a; color:#eef4ff; background:#ffffff0b; }
        .hero-actions a.primary { color:#18355c; background:white; border-color:white; }
        .hero-actions a:hover { transform:translateY(-1px); box-shadow:0 4px 12px #071a3d20; }
        .hero-actions a:focus-visible { outline:3px solid #9ac1ff; outline-offset:3px; }
        .hero-hint { font-size:11px; color:#b9cce9; }
        .sidebar-brand { display:flex; align-items:center; gap:12px; margin:10px 0 22px; color:var(--analysis-text); }
        .brand-symbol { display:grid; place-items:center; border-radius:11px; background:#2563eb; color:white; width:43px; height:43px; font-size:14px; font-weight:750; }
        .sidebar-brand strong { display:block; font-size:17px; letter-spacing:-.4px; }
        .sidebar-brand small { display:block; color:var(--analysis-muted); font-size:12px; margin-top:3px; }
        .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:13px; }
        .metric-card { position:relative; background:var(--analysis-panel); border:1px solid var(--analysis-line); border-radius:13px; padding:19px 19px 16px; color:var(--analysis-text); min-width:0; overflow:hidden; }
        .metric-card:before { content:""; position:absolute; top:0; left:20px; right:20px; height:3px; background:var(--metric-accent); border-radius:0 0 3px 3px; }
        .metric-top { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:12px; }
        .metric-label { font-size:12px; font-weight:650; color:var(--analysis-muted); }
        .metric-icon { width:33px; height:33px; display:grid; place-items:center; border-radius:9px; color:var(--metric-accent); background:var(--metric-tint); flex-shrink:0; }
        .metric-icon svg { width:18px; height:18px; }
        .metric-value { font-size:28px; line-height:1.25; font-weight:780; letter-spacing:-.8px; font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
        .metric-value small { font-size:12px; font-weight:500; letter-spacing:0; margin-left:3px; color:var(--analysis-muted); }
        .metric-note { color:var(--analysis-muted); font-size:11px; line-height:1.6; margin-top:10px; }
        .metric-progress { display:flex; height:4px; border-radius:8px; overflow:hidden; background:var(--analysis-line); margin-top:12px; }
        .flow-values { display:grid; grid-template-columns:1fr 1fr; gap:9px; }
        .flow-values div+div { border-left:1px solid var(--analysis-line); padding-left:9px; }
        .flow-values strong { display:block; font-size:21px; font-weight:750; font-variant-numeric:tabular-nums; letter-spacing:-.6px; }
        .flow-values span { display:block; color:var(--analysis-muted); font-size:10px; margin-top:5px; }
        .scope-line { display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; color:var(--analysis-muted); font-size:11px; padding:0 1px; align-items:center; }
        .scope-chips { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
        .scope-chips b { font-weight:550; color:var(--analysis-blue); border:1px solid var(--analysis-line); border-radius:6px; background:var(--analysis-panel); padding:4px 8px; }
        .region-summary { display:grid; grid-template-columns:150px minmax(0,1fr); gap:18px; align-items:center; background:var(--analysis-panel); border:1px solid var(--analysis-line); border-radius:11px; padding:13px 18px; }
        .region-summary strong { display:block; color:var(--analysis-text); font-size:12px; font-weight:650; }
        .region-summary small { display:block; color:var(--analysis-muted); font-size:10px; margin-top:4px; }
        .region-track { display:flex; height:9px; border-radius:6px; overflow:hidden; background:var(--analysis-line); }
        .region-legend { display:flex; gap:12px; flex-wrap:wrap; margin-top:7px; color:var(--analysis-muted); font-size:10px; }
        .region-legend i { display:inline-block; width:6px; height:6px; border-radius:2px; margin-right:4px; }
        @media(max-width:1250px) { .overview-hero { grid-template-columns:1fr; gap:17px; padding:24px; } .hero-right { flex-direction:row; flex-wrap:wrap; align-items:center; justify-content:space-between; } .hero-hint { display:none; } .hero-period strong { font-size:19px; } .metric-value { font-size:24px; } .flow-values strong { font-size:18px; } }
        @media(max-width:1050px) { .metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .metric-value { font-size:28px; } .flow-values strong { font-size:23px; } }
        @media(max-width:600px) { .overview-hero { padding:23px 19px; border-radius:13px; } .overview-hero h1 { font-size:25px; } .hero-subtitle { font-size:12px; } .hero-right { align-items:flex-start; flex-direction:column; gap:12px; } .hero-actions { width:100%; } .hero-actions a { flex:1; padding:9px 8px; } .metric-grid { gap:9px; } .metric-card { padding:15px 13px; } .metric-value { font-size:22px; } .metric-icon { width:27px; height:27px; } .metric-label { font-size:11px; } .metric-note { font-size:10px; } .flow-values strong { font-size:18px; } .region-summary { grid-template-columns:1fr; gap:9px; padding:12px 14px; } .region-summary small { display:none; } }
        </style>'''),
        mo.Html(f'''<section class="overview-hero" aria-label="국민연금 사업장 대시보드 상단"><div><div class="hero-kicker"><span>월간 공개자료</span><span>국민연금공단 · 게시 {escape(metadata['source_published_at'])}</span></div><h1>국민연금 사업장 분석</h1><p class="hero-subtitle">지역·업종·규모별 현황을 살펴보고, 전체 원본과 코드를 직접 탐색하세요.</p></div><div class="hero-right"><div class="hero-period"><span>자료 기준월</span><strong>{escape(', '.join(metadata['periods']))}</strong></div><nav class="hero-actions" aria-label="분석 화면 이동"><a href="{escape(page_links['dashboard'] if page_links['editing'] else page_links['editor'])}" class="primary">{'대시보드 보기' if page_links['editing'] else '노트북 편집'} <span aria-hidden="true">↗</span></a><a href="{escape(page_links['explorer'])}">전체 데이터 탐색 <span aria-hidden="true">→</span></a></nav><span class="hero-hint">편집기는 ‘전체 실행’으로 시작 · 수정한 노트북은 내려받아 보관</span></div></section>'''),
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
def _(band_filter, escape, filter_elapsed_ms, filtered_rows, industry_filter, kind_filter, metadata, mo, region_filter, status_filter, totals):
    _scopes = [
        "전국" if region_filter.value == "전체" else str(region_filter.value),
        "모든 가입 상태" if status_filter.value == "전체" else str(status_filter.value),
        "모든 사업장 형태" if kind_filter.value == "전체" else str(kind_filter.value),
        "모든 규모" if band_filter.value == "전체" else str(band_filter.value),
    ]
    if industry_filter.value != "전체":
        _scopes.append(f"업종 {industry_filter.value}")
    _scope_html = "".join(f"<b>{escape(label)}</b>" for label in _scopes)
    _coverage = totals["workplaces"] / metadata["totals"]["workplaces"] * 100 if metadata["totals"]["workplaces"] else 0
    _registered = sum(row["workplaces"] for row in filtered_rows if row["status"] == "등록")
    _registered_share = _registered / totals["workplaces"] * 100 if totals["workplaces"] else 0
    _billing_share = totals["billing"] / metadata["totals"]["billing"] * 100 if metadata["totals"]["billing"] else 0
    _subscriber_share = totals["subscribers"] / metadata["totals"]["subscribers"] * 100 if metadata["totals"]["subscribers"] else 0
    _average = f"{totals['subscribers']/totals['workplaces']:,.1f}명" if totals["workplaces"] else "—"
    _per_subscriber = f"{totals['billing']/totals['subscribers']:,.0f}원" if totals["subscribers"] else "—"
    _flow_total = totals["new"] + totals["lost"]
    _new_share = totals["new"] / _flow_total * 100 if _flow_total else 0
    _icon_start = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    _building = _icon_start + '<path d="M4 21V5l8-2v18M12 9h8v12M2 21h20M7 8h2M7 12h2M7 16h2M15 12h2M15 16h2"/></svg>'
    _people = _icon_start + '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M19 21v-3a6 6 0 0 0-2-4"/></svg>'
    _wallet = _icon_start + '<rect x="3" y="5" width="18" height="15" rx="3"/><path d="M3 8h18M16 12h5v5h-5zM5 5V3h12"/></svg>'
    _arrows = _icon_start + '<path d="M3 7h16M15 3l4 4-4 4M21 17H5M9 13l-4 4 4 4"/></svg>'
    _regions = {}
    for _row in filtered_rows:
        _regions[_row["region"]] = _regions.get(_row["region"], 0) + _row["subscribers"]
    _leaders = sorted(_regions.items(), key=lambda pair: pair[1], reverse=True)[:4]
    _remainder = totals["subscribers"] - sum(value for _, value in _leaders)
    if _remainder:
        _leaders.append(("그 외 지역", _remainder))
    _colors = ["#2563eb", "#5b8def", "#16a3a1", "#8b5cf6", "#c4cfdf"]
    _region_track = ""
    _region_legend = ""
    if totals["subscribers"]:
        for (_name, _value), _color in zip(_leaders, _colors):
            _share = _value / totals["subscribers"] * 100
            _region_track += f'<span style="width:{_share}%;background:{_color}" title="{escape(_name)} {_share:.1f}%"></span>'
            _region_legend += f'<span><i style="background:{_color}"></i>{escape(_name)} {_share:.1f}%</span>'
    _region_summary = mo.Html(f'<div class="region-summary"><div><strong>가입자의 지역 구성</strong><small>현재 선택 범위의 가입자 합계</small></div><div><div class="region-track" role="img" aria-label="지역별 가입자 구성">{_region_track}</div><div class="region-legend">{_region_legend}</div></div></div>') if totals["subscribers"] else mo.Html("")
    mo.vstack([
        mo.Html(f'<div class="scope-line"><div class="scope-chips"><span>분석 범위</span>{_scope_html}</div><span>공개 기록의 {_coverage:,.1f}% 선택 · SQL 조회 {filter_elapsed_ms:,.0f}ms</span></div>'),
        mo.Html(f'''<div class="metric-grid">
        <article class="metric-card" style="--metric-accent:#2563eb;--metric-tint:#edf3ff"><div class="metric-top"><span class="metric-label">사업장 수</span><span class="metric-icon">{_building}</span></div><div class="metric-value">{totals['workplaces']:,}<small>개</small></div><div class="metric-note">등록 {_registered_share:.1f}% · 원본 사업장 행 수</div><div class="metric-progress"><span style="width:{_registered_share}%;background:#2563eb"></span></div></article>
        <article class="metric-card" style="--metric-accent:#0d9488;--metric-tint:#e7f7f4"><div class="metric-top"><span class="metric-label">가입자 수</span><span class="metric-icon">{_people}</span></div><div class="metric-value">{totals['subscribers']:,}<small>명</small></div><div class="metric-note">사업장당 평균 {_average}</div><div class="metric-progress" title="전체 공개 가입자의 {_subscriber_share:.1f}%" aria-label="전체 공개 가입자의 {_subscriber_share:.1f}%"><span style="width:{_subscriber_share}%;background:#0d9488"></span></div></article>
        <article class="metric-card" style="--metric-accent:#7c3aed;--metric-tint:#f3edff"><div class="metric-top"><span class="metric-label">당월 고지금액</span><span class="metric-icon">{_wallet}</span></div><div class="metric-value">{totals['billing']/100_000_000:,.1f}<small>억 원</small></div><div class="metric-note">가입자당 {_per_subscriber} · 실제 소득과 다름</div><div class="metric-progress" title="전체 공개 고지금액의 {_billing_share:.1f}%" aria-label="전체 공개 고지금액의 {_billing_share:.1f}%"><span style="width:{_billing_share}%;background:#7c3aed"></span></div></article>
        <article class="metric-card" style="--metric-accent:#d97706;--metric-tint:#fff5e8"><div class="metric-top"><span class="metric-label">신규취득 · 상실</span><span class="metric-icon">{_arrows}</span></div><div class="flow-values"><div><strong>{totals['new']:,}</strong><span>신규취득(명)</span></div><div><strong>{totals['lost']:,}</strong><span>상실(명)</span></div></div><div class="metric-note">납부재개 · 납부예외 포함</div><div class="metric-progress"><span style="width:{_new_share}%;background:#d97706"></span><span style="flex:1;background:#f4d2a2"></span></div></article>
        </div>'''),
        _region_summary,
        mo.md("<small>공개 범위: 가입자 3인 이상 법인·10인 이상 개인(2025년 7월 이후). 탈퇴·0명 원본 행을 보존했으며 전체 고용 통계와 다릅니다.</small>"),
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
            mo.Html(f'<div><h2 style="color:var(--analysis-text);font-size:17px;font-weight:700;margin:0;letter-spacing:-.4px">{escape(title)}</h2>' + (f'<p style="color:var(--analysis-muted);font-size:12px;margin:5px 0 0;line-height:1.6">{escape(note)}</p>' if note else '') + '</div>'), content,
        ], gap=1).style({"background":"var(--analysis-panel)","border":"1px solid var(--analysis-line)","border-radius":"12px","padding":"20px","min-width":"0"})

    region_rows = rollup("region")
    industry_rows = sorted(rollup("industry"), key=lambda r: r[metric_key], reverse=True)
    band_rows = rollup("size_band")
    return band_rows, bar_chart, industry_rows, metric_key, metric_labels, panel, region_rows


@app.cell
def _(alt, band_rows, bar_chart, filtered_rows, industry_rows, metadata, metric_key, metric_labels, mo, panel, region_rows, top_n_filter):
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
                panel(f"업종별 {metric_labels[metric_key]} · 상위 {top_n_filter.value}개", mo.ui.altair_chart(bar_chart(industry_rows[:top_n_filter.value], "#0d9488", max(_height,top_n_filter.value*24)), chart_selection=False, legend_selection=False), f"선택 조건의 {len(industry_rows):,}개 업종 중 상위 항목"),
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
def _(alt, bar_chart, demo_top, industry_rows, mo):
    demo_rows = industry_rows[:demo_top.value]
    _selection = alt.selection_point(name="industry_choice", fields=["항목"], empty=True)
    _chart = bar_chart(demo_rows, "#2563eb", 370).add_params(_selection).encode(
        color=alt.condition(_selection, alt.value("#2563eb"), alt.value("#cbd5e1"))
    )
    demo_chart = mo.ui.altair_chart(_chart, chart_selection=False, legend_selection=False, label="막대를 클릭해 업종 선택")
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
    _signal = demo_chart.selections.get("industry_choice") or {}
    _names = set(_signal.get("항목") or [])
    _selection = [row for row in demo_rows if row["항목"] in _names]
    _selected = [{"업종":r["항목"],"사업장 수":r["workplaces"],"가입자 수":r["subscribers"],"당월 고지금액(원)":r["billing"]} for r in _selection]
    marimo_demo = mo.vstack([
        mo.hstack([
            mo.vstack([mo.md("**1. 슬라이더를 움직이세요**"), mo.md("바뀐 입력을 사용하는 셀만 자동 재실행됩니다. 업종 수와 차트가 함께 갱신됩니다.")], gap=0.5).style({"padding":"16px","border":"1px solid var(--analysis-line)","border-radius":"10px","background":"var(--analysis-panel)","font-size":"13px"}),
            mo.vstack([mo.md("**2. 차트 막대를 클릭하세요**"), mo.md("선택한 차트 데이터가 Python으로 전달되어 표에 연결됩니다. Shift와 클릭으로 여러 업종을 선택하세요.")], gap=0.5).style({"padding":"16px","border":"1px solid var(--analysis-line)","border-radius":"10px","background":"var(--analysis-panel)","font-size":"13px"}),
            mo.vstack([mo.md("**3. 코드를 확인하세요**"), mo.md("UI와 차트·표를 하나의 Python 파일로 관리합니다. 셀 의존관계에 따라 결과가 갱신됩니다.")], gap=0.5).style({"padding":"16px","border":"1px solid var(--analysis-line)","border-radius":"10px","background":"var(--analysis-panel)","font-size":"13px"}),
        ], widths="equal", wrap=True, align="stretch", gap=0.8),
        panel("반응형 셀과 차트·표 연동", mo.vstack([
            demo_top, mo.md(f"현재 **상위 {demo_top.value}개 업종**을 표시합니다. 왼쪽 탐색 조건도 함께 적용됩니다."), demo_chart,
            mo.md(f"**선택한 업종 {len(_selected)}개**"),
            mo.ui.table(_selected, selection=None, show_column_summaries=False, show_data_types=False, label="차트 선택과 연결된 표") if _selected else mo.callout("차트의 막대를 클릭하면 해당 업종의 수치가 여기에 나타납니다. 빈 공간을 두 번 클릭하면 선택이 해제됩니다.", kind="neutral"),
        ])),
        panel("화면을 만드는 핵심 코드", mo.md('''```python
# 첫 번째 셀: 입력 위젯
업종수 = mo.ui.slider(start=3, stop=20, value=8)

# 두 번째 셀: 입력 변경 시 이 차트 셀을 자동 실행
선택 = alt.selection_point(fields=["항목"])
연동차트 = mo.ui.altair_chart(차트.add_params(선택))

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
