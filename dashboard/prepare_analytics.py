"""사업장별 추정 연봉·규모·두 시점 비교용 경량 Parquet을 만든다."""

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


RATE_NUMERATOR = 95
RATE_DENOMINATOR = 1000
MONTHLY_UPPER = 6_590_000
DIMENSIONS = ["period", "region", "status", "kind", "industry_code", "industry", "size_band"]
MEASURES = ["subscribers", "billing", "new", "lost"]
RAW_MEASURES = dict(zip(["가입자수", "당월고지금액", "신규취득자수", "상실가입자수"], MEASURES))
SOURCES = [
    {"title": "국민연금공단 연금개혁 안내", "url": "https://www.nps.or.kr/pnsinfo/ntpsklg/getOHAF0104M0.do"},
    {"title": "국민연금공단 2026년 7월 기준소득월액 안내", "url": "https://www.npsonair.kr/advantages/detail.html?strIdx=3923&strPage=1"},
]


def rows(connection, query: str, parameters=None) -> list[dict]:
    """열 이름과 함께 조회 결과를 반환한다."""
    cursor = connection.execute(query, parameters or [])
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def independent_totals(source: Path) -> dict[str, int]:
    """원본 CSV를 별도로 순회하여 사업장 수와 측정값을 대조한다."""
    result = Counter({"workplaces": 0, **dict.fromkeys(MEASURES, 0)})
    with source.open(encoding="cp949", newline="") as stream:
        for row in csv.DictReader(stream):
            result["workplaces"] += 1
            result.update({metric: int(row[column]) for column, metric in RAW_MEASURES.items()})
    return dict(result)


def validate_periods(periods: list[str]) -> None:
    """확인한 요율·상한의 공통 적용 범위를 벗어나면 잘못된 추정을 막는다."""
    if len(periods) != 1 or not "2026-07" <= periods[0] <= "2026-12":
        raise ValueError("현재 추정 정책의 지원 기준월은 2026-07~2026-12입니다. 기준월별 보험료율·상한 설정을 먼저 확인하세요.")


def prepare(raw: Path, metadata_path: Path, output: Path, history: Path | None, history_manifest: Path | None) -> dict:
    """같은 최신 원본으로 분석 자료를 만들고 합계·차원·이력 연결을 검증한다."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw_metadata = json.loads(raw.with_name("raw_metadata.json").read_text(encoding="utf-8"))
    validate_periods(metadata["periods"])
    if metadata["source_sha256"] != raw_metadata["source_sha256"]:
        raise ValueError("원본 전체 조회와 요약 집계의 출처가 다릅니다.")
    with raw.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != raw_metadata["parquet_sha256"]:
            raise ValueError("원본 Parquet의 검증값이 기록과 다릅니다.")
    source = Path(metadata["source_file"])
    if source.exists():
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != metadata["source_sha256"]:
                raise ValueError("최신 원본 CSV의 검증값이 기록과 다릅니다.")
        if independent_totals(source) != metadata["totals"]:
            raise ValueError("독립적으로 순회한 원본 CSV의 합계가 집계와 다릅니다.")

    historical_info = None
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nps-analytics-") as temporary, duckdb.connect() as connection:
        connection.execute("SET preserve_insertion_order=true")
        connection.execute("CREATE TABLE raw AS SELECT * FROM read_parquet(?)", [str(raw)])
        connection.execute("CREATE TABLE region_names(code VARCHAR, region VARCHAR)")
        connection.executemany("INSERT INTO region_names VALUES (?, ?)", [(r["code"], r["region"]) for r in metadata["quality"]["source_region_counts"]])
        connection.execute("""
            CREATE TABLE current_records AS
            SELECT raw.rowid+1 AS record_id,
                "자료생성년월" AS period, COALESCE(region_names.region, '미상') AS region,
                CASE "사업장가입상태코드 1 등록 2 탈퇴" WHEN '1' THEN '등록' WHEN '2' THEN '탈퇴' ELSE '미상' END AS status,
                CASE "사업장형태구분코드 1 법인 2 개인" WHEN '1' THEN '법인' WHEN '2' THEN '개인' ELSE '미상' END AS kind,
                COALESCE("사업장업종코드", '미상') AS industry_code,
                COALESCE("사업장업종코드명", '미상') AS industry,
                CASE WHEN "가입자수"=0 THEN '0명' WHEN "가입자수"<=2 THEN '1~2명'
                    WHEN "가입자수"<=4 THEN '3~4명' WHEN "가입자수"<=9 THEN '5~9명'
                    WHEN "가입자수"<=29 THEN '10~29명' WHEN "가입자수"<=99 THEN '30~99명'
                    WHEN "가입자수"<=299 THEN '100~299명' WHEN "가입자수"<=999 THEN '300~999명'
                    ELSE '1,000명 이상' END AS size_band,
                "사업장명" AS business_name, "사업자등록번호" AS registration_prefix,
                "고객법정동주소코드" AS location_code,
                "가입자수" AS subscribers, "당월고지금액" AS billing,
                "신규취득자수" AS new, "상실가입자수" AS lost,
                "가입자수">0 AND "당월고지금액">0 AS salary_valid,
                CASE WHEN "가입자수">0 AND "당월고지금액">0
                    THEN "당월고지금액"*1000.0/("가입자수"*95) END AS monthly_income_proxy,
                CASE WHEN "가입자수">0 AND "당월고지금액">0
                    THEN "당월고지금액"*12000.0/("가입자수"*95) END AS annual_salary_proxy,
                "가입자수">0 AND "당월고지금액">0 AND "당월고지금액"*1000>"가입자수"*95*6590000 AS estimate_flag,
                CASE WHEN "가입자수"<5 THEN '5인 미만' WHEN "가입자수"<50 THEN '소규모 (5~49인)'
                    WHEN "가입자수"<300 THEN '중규모 (50~299인)' ELSE '대규모 (300인 이상)' END AS salary_size,
                COUNT(*) OVER(PARTITION BY trim("사업장명"),trim("사업자등록번호"),trim("고객법정동주소코드"),"사업장형태구분코드 1 법인 2 개인") AS current_key_count,
                "사업장형태구분코드 1 법인 2 개인" AS kind_code
            FROM raw LEFT JOIN region_names ON raw."법정동주소광역시도코드"=region_names.code
            ORDER BY raw.rowid
        """)
        if history is not None and history.exists() and history_manifest is not None and history_manifest.exists():
            with history_manifest.open(encoding="utf-8-sig", newline="") as stream:
                matches = [row for row in csv.DictReader(stream) if Path(row["저장경로"]).name == history.name]
            if len(matches) != 1:
                raise ValueError("과거 자료의 출처 기록이 정확히 한 개 필요합니다.")
            with history.open("rb") as stream:
                history_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if history_hash != matches[0]["SHA256"]:
                raise ValueError("과거 원본의 검증값이 출처 기록과 다릅니다.")
            utf8_history = Path(temporary) / "history.csv"
            with history.open(encoding="cp949", newline="") as reader, utf8_history.open("w", encoding="utf-8", newline="") as writer:
                shutil.copyfileobj(reader, writer)
            connection.execute("CREATE TABLE history_raw AS SELECT * FROM read_csv(?,header=true,all_varchar=true)", [str(utf8_history)])
            history_periods = [r[0] for r in connection.execute('SELECT DISTINCT "자료생성년월" FROM history_raw').fetchall()]
            if history_periods != ["2026-06"]:
                raise ValueError("예상한 과거 기준월 2026-06과 다릅니다.")
            connection.execute("""
                CREATE TABLE history_keys AS
                SELECT trim("사업장명") AS business_name, trim("사업자등록번호") AS registration_prefix,
                    trim("고객법정동주소코드") AS location_code, "사업장형태구분코드 1 법인 2 개인" AS kind_code,
                    count(*) AS previous_key_count, min("자료생성년월") AS previous_period,
                    min(CAST("가입자수" AS BIGINT)) AS previous_subscribers,
                    min(CAST("당월고지금액" AS BIGINT)) AS previous_billing
                FROM history_raw GROUP BY 1,2,3,4
            """)
            historical_info = {
                "period": "2026-06", "published_at": matches[0]["게시일"],
                "source_sha256": history_hash, "source_file": history.as_posix(),
                "monthly_income_upper": 6_370_000, "contribution_rate": 0.095,
            }
        else:
            connection.execute("CREATE TABLE history_keys(business_name VARCHAR,registration_prefix VARCHAR,location_code VARCHAR,kind_code VARCHAR,previous_key_count BIGINT,previous_period VARCHAR,previous_subscribers BIGINT,previous_billing BIGINT)")
        connection.execute("""
            CREATE TABLE analytics AS
            WITH linked AS (
                SELECT c.*,
                    CASE WHEN c.registration_prefix IS NULL OR trim(c.registration_prefix) IN ('','000000') OR c.business_name IS NULL OR trim(c.business_name)='' OR c.location_code IS NULL OR trim(c.location_code)=''
                         THEN 'missing_identifier'
                         WHEN c.current_key_count<>1 THEN 'ambiguous_current'
                         WHEN h.previous_key_count>1 THEN 'ambiguous_previous'
                         WHEN h.previous_key_count=1 THEN 'matched'
                         ELSE 'not_found' END AS match_status,
                    h.previous_period,h.previous_subscribers,h.previous_billing
                FROM current_records c LEFT JOIN history_keys h
                  ON trim(c.business_name)=h.business_name AND trim(c.registration_prefix)=h.registration_prefix
                 AND trim(c.location_code)=h.location_code AND c.kind_code=h.kind_code
            )
            SELECT record_id,period,region,status,kind,industry_code,industry,size_band,business_name,registration_prefix,location_code,
                subscribers,billing,new,lost,monthly_income_proxy,annual_salary_proxy,salary_valid,estimate_flag,salary_size,
                CASE WHEN match_status='matched' THEN previous_period END AS previous_period,
                CASE WHEN match_status='matched' THEN previous_subscribers END AS previous_subscribers,
                CASE WHEN match_status='matched' THEN previous_billing END AS previous_billing,
                match_status
            FROM linked ORDER BY record_id
        """)
        totals = rows(connection,"SELECT count(*)::BIGINT AS workplaces,"+",".join(f"SUM({key})::BIGINT AS {key}" for key in MEASURES)+" FROM analytics")[0]
        if totals != metadata["totals"]:
            raise ValueError("기업 분석 파일의 전체 합계가 원본 집계와 다릅니다.")
        dimensions_sql = ",".join(DIMENSIONS)
        metric_sql = "count(*)::BIGINT AS workplaces,"+",".join(f"SUM({key})::BIGINT AS {key}" for key in MEASURES)
        dimensions_difference = connection.execute(
            f"SELECT count(*) FROM ((SELECT {dimensions_sql},{metric_sql} FROM analytics GROUP BY {dimensions_sql} EXCEPT ALL SELECT * FROM read_parquet(?)) UNION ALL (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT {dimensions_sql},{metric_sql} FROM analytics GROUP BY {dimensions_sql}))",
            [str(metadata_path.with_name("snapshot.parquet")),str(metadata_path.with_name("snapshot.parquet"))],
        ).fetchone()[0]
        if dimensions_difference:
            raise ValueError("기업 분석 파일과 기존 집계의 차원별 합계가 일치하지 않습니다.")
        duplicate_ids = connection.execute("SELECT count(*)-count(DISTINCT record_id) FROM analytics").fetchone()[0]
        if duplicate_ids:
            raise ValueError("과거 자료 연결 중 원본 행이 증식했습니다.")
        default_summary = rows(connection,"""
            SELECT COUNT(*)::BIGINT AS workplaces,SUM(subscribers)::BIGINT AS subscribers,
                SUM(billing)::BIGINT AS billing,SUM(new)::BIGINT AS new,SUM(lost)::BIGINT AS lost,
                SUM(billing)*12000.0/(95*SUM(subscribers)) AS weighted_mean_annual,
                AVG(annual_salary_proxy) AS business_mean_annual,MEDIAN(annual_salary_proxy) AS business_median_annual,
                COUNT(*) FILTER(WHERE estimate_flag)::BIGINT AS above_cap_workplaces,
                COALESCE(SUM(subscribers) FILTER(WHERE estimate_flag),0)::BIGINT AS subscribers_at_above_cap_workplaces
            FROM analytics WHERE status='등록' AND subscribers>=5 AND salary_valid
        """)[0]
        size_summary = rows(connection,"""
            SELECT salary_size,COUNT(*)::BIGINT AS workplaces,SUM(subscribers)::BIGINT AS subscribers,
                SUM(billing)::BIGINT AS billing,SUM(billing)*12000.0/(95*SUM(subscribers)) AS weighted_mean_annual,
                MEDIAN(annual_salary_proxy) AS business_median_annual
            FROM analytics WHERE status='등록' AND subscribers>=5 AND salary_valid GROUP BY salary_size ORDER BY MIN(subscribers)
        """)
        match_counts = {name:value for name,value in connection.execute("SELECT match_status,count(*) FROM analytics GROUP BY match_status").fetchall()}
        connection.execute("COPY (SELECT * FROM analytics ORDER BY region,industry_code,kind,status,size_band,business_name) TO ? (FORMAT PARQUET,COMPRESSION ZSTD,COMPRESSION_LEVEL 15,ROW_GROUP_SIZE 500000)",[str(output)])
        schema = [{"name":r[0],"type":r[1]} for r in connection.execute("DESCRIBE SELECT * FROM read_parquet(?)",[str(output)]).fetchall()]
        written = connection.execute("SELECT count(*) FROM read_parquet(?)",[str(output)]).fetchone()[0]
        if written != metadata["totals"]["workplaces"]:
            raise ValueError("저장된 분석 파일의 행 수가 다릅니다.")

    analytics_metadata = {
        "schema_version":1,"title":"국민연금 사업장 추정 연봉·순위 분석","periods":metadata["periods"],
        "source_url":metadata["source_url"],"source_file":metadata["source_file"],"source_sha256":metadata["source_sha256"],
        "source_published_at":metadata["source_published_at"],"collected_at":metadata["collected_at"],
        "row_count":written,"columns":schema,"totals":totals,"default_summary":default_summary,"default_size_summary":size_summary,
        "contribution_rate":0.095,"monthly_income_lower":410_000,"monthly_income_upper":MONTHLY_UPPER,
        "annual_income_upper":MONTHLY_UPPER*12,"policy_period":"2026-07 ~ 2027-06",
        "supported_estimation_period":"2026-07 ~ 2026-12","rate_policy_note":"현재 9.5% 보험료율은 2026년 적용 기준입니다. 2027년부터 10%로 달라지므로 지원 범위 밖 기준월은 생성 단계에서 중단합니다.","sources":SOURCES,
        "formula":"추정 연봉 = 당월 고지금액 ÷ 가입자 수 ÷ 0.095 × 12",
        "default_population":"등록 상태이며 가입자 5명 이상, 가입자 수와 당월 고지금액이 모두 양수인 원본 사업장 행",
        "mean_definition":"가입자가중 평균은 대상 사업장 고지금액 합계 ÷ 대상 가입자 합계 ÷ 보험료율 × 12입니다. 사업장 단순평균과 구분합니다.",
        "median_definition":"중위값은 사업장별 추정 평균 연봉의 중앙값입니다. 개인 가입자 연봉의 중앙값을 알 수 있다는 의미가 아닙니다.",
        "cap_definition":"estimate_flag는 사업장 평균 역산 월소득이 659만원을 초과하는지 표시합니다. 개별 가입자의 실제 상한 초과 여부나 상한 초과 인원은 이 자료로 식별할 수 없습니다.",
        "salary_note":"국민연금 기준소득월액을 연환산한 대리값으로 실제 연봉·성과급·비과세 수당·실수령액과 다릅니다. 기준소득월액 상한에 따라 고소득이 과소추정될 수 있고 신고 시차·정산의 영향이 있습니다. 상한 초과 역산값을 임의 보정하지 않습니다.",
        "history":historical_info,"history_match_counts":match_counts,
        "history_note":"2026년 6월과 10월 두 시점만 비교합니다. 사업장명·축약 등록번호·법정동코드·형태가 각 원본에서 유일하게 일치한 경우에만 과거 값을 연결했습니다. 월별 연속 증가나 같은 법인의 전체 사업장 추세를 의미하지 않습니다.",
        "match_status_labels":{"matched":"두 시점 유일 일치","missing_identifier":"연결 식별값 부족","ambiguous_current":"현재 복합키 중복","ambiguous_previous":"과거 복합키 중복","not_found":"일치하는 과거 행 없음"},
        "record_note":"사업장 수는 원본 행 수이며 사업자등록번호는 축약되어 있어 고유 기업 수를 별도로 추정하지 않습니다.",
        "parquet_bytes":output.stat().st_size,"parquet_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
        "verification":"독립 CSV 순회 5지표 합계·원본 SHA256·기존 집계의 모든 7차원 합계·연결 후 행 수와 고유 record_id·저장된 Parquet 행 수를 검증했습니다.",
        "prepared_at":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
    }
    output.with_name("analytics_metadata.json").write_text(json.dumps(analytics_metadata,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return analytics_metadata


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,default=Path("dashboard/public/data/raw.parquet"),help="최신 전체 원본 Parquet")
    parser.add_argument("--metadata",type=Path,default=Path("dashboard/public/data/metadata.json"),help="최신 집계 메타데이터")
    parser.add_argument("--output",type=Path,default=Path("dashboard/public/data/analytics.parquet"),help="기업 분석 Parquet 저장 경로")
    parser.add_argument("--history",type=Path,default=Path("data/nps_workplaces_20260723.csv"),help="보유 중인 2026년 6월 원본 CSV")
    parser.add_argument("--history-manifest",type=Path,default=Path("data/download_manifest.csv"),help="과거 원본 수집 기록")
    args=parser.parse_args()
    result=prepare(args.raw,args.metadata,args.output,args.history,args.history_manifest)
    print(f"기업 분석 저장: {args.output} · {result['row_count']:,}행 · {result['parquet_bytes']:,}바이트")
    print("기본 분석 대상:",json.dumps(result["default_summary"],ensure_ascii=False))
    print("과거 연결:",json.dumps(result["history_match_counts"],ensure_ascii=False))


if __name__=="__main__":
    main()
