# 국민연금 가입 사업장 대시보드

[공공데이터포털의 국민연금 가입 사업장 내역](https://www.data.go.kr/data/15083277/fileData.do)을 탐색하는 marimo 대시보드입니다. GitHub Pages가 정적 파일을 제공하고, Python과 DuckDB SQL은 방문자의 브라우저에서 Pyodide로 실행됩니다. 운영용 Python 서버나 API 키는 필요하지 않습니다.

현재 포함된 자료는 **2026년 11월 23일 게시 파일의 2026년 10월 기준 기록**입니다. 2026년 11월 26일에 공식 페이지의 게시일을 확인하고 원본 588,075행을 다시 내려받아 분석했습니다. 파일 게시일과 통계 기준월은 다릅니다.

| 구분 | 값 |
| --- | ---: |
| 원본 사업장 기록 | 588,075행 |
| 공개 집계 | 56,398행 |
| 가입자 수 | 11,597,244명 |
| 당월 고지금액 | 4,381,395,703,220원 |
| 신규취득자 수 | 448,834명 |
| 상실가입자 수 | 363,705명 |

사업장 수는 원본 행 수입니다. 제공 범위는 가입자 수 3인 이상 법인사업장과 10인 이상 개인사업장(2025년 7월 이후)이며 원본에는 탈퇴·0명 기록도 포함됩니다. 전체 사업장·전체 고용인구 통계로 해석할 수 없습니다. 신규취득자 수에는 납부재개, 상실가입자 수에는 납부예외 등이 포함되므로 둘의 차이는 순고용 증가가 아닙니다. 고지금액은 매출·실수령 급여와 다릅니다.

## 화면 구성

- 지역·가입 상태·사업장 형태·업종·가입자 규모 필터와 사업장·가입자·고지금액·취득/상실 지표
- 지역·업종·규모별 비교 및 신규취득/상실 비교 차트
- 현재 조건의 전체 집계 표와 CSV 다운로드
- DuckDB SQL 편집기, 예제 쿼리, 실행 시간, `EXPLAIN` 계획, SQL 결과 CSV
- 슬라이더에 따른 셀 재실행, 차트 선택과 표 연동, `mo.sql`을 확인하는 마리모 기능 체험
- 원본 게시일·수집일·SHA256·결측·중복·집계 기준을 확인하는 출처·품질 탭

SQL의 `workplaces`는 공개 집계 전체, `selection`은 현재 탐색 조건의 집계입니다. 한 집계행에 여러 사업장 기록이 포함되므로 사업장 수는 `COUNT(*)`가 아니라 `SUM(workplaces)`로 계산합니다.

DuckDB는 원본의 사전 집계와 브라우저의 조건별 집계·직접 SQL 조회에 사용합니다. 원본 114,885,359바이트에서 집계 Parquet 521,221바이트를 생성했으며, 브라우저가 Parquet을 한 번 받은 뒤 같은 메모리 연결을 재사용합니다. 반응형 셀은 바뀐 입력을 사용하는 셀을 갱신하고, 단일 Python 소스와 GitHub Actions로 실행·배포 과정을 재현합니다.

## 파일 구성

- `app.py`: marimo 대시보드와 브라우저용 패키지 선언
- `download_latest.py`: 공식 다운로드 버튼의 요청 계약으로 최신 공개 CSV 수집
- `prepare_data.py`: DuckDB SQL 집계, 출처·품질 검증, Parquet·JSON 생성
- `public/data/snapshot.parquet`: 브라우저가 읽는 공개 집계, 약 509KB
- `public/data/metadata.json`: 출처·기준월·합계·품질 메타데이터
- `public/data/snapshot.json.gz`: 집계 검증용 스냅샷
- `build.py`: `dist/` 정적 웹앱 생성
- `publish.py`: 대시보드 전용 GitHub 저장소에 선별 동기화·게시
- `requirements.txt`: 로컬·CI 빌드 패키지 버전
- `tests/test_snapshot.py`: 원본·집계·Parquet 대조 검증
- `../.github/workflows/deploy-dashboard.yml`: GitHub Pages 자동 배포

사업장명·상세주소·사업자등록번호는 공개 집계와 정적 배포에 포함하지 않습니다. 공개되는 차원은 기준월·지역·가입 상태·사업장 형태·업종·가입자 규모이며, 지표는 사업장 행 수·가입자 수·고지금액·취득/상실 인원입니다.

## 로컬 실행

모든 명령은 `dashboard/`가 들어 있는 저장소 루트에서 실행합니다. 기존 루트 `.venv`를 재사용합니다. 새 작업 폴더에 `.venv`가 없는 경우에만 다음 첫 명령으로 만듭니다.

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r dashboard/requirements.txt
```

```bash
uv run --no-sync marimo edit dashboard/app.py
```

빌드 환경은 `duckdb==1.5.5` 등 고정 버전을 사용합니다. 브라우저의 PEP 723 패키지 선언은 Pyodide가 제공하는 호환 버전을 사용하도록 고정하지 않았습니다. 브라우저에서는 Pyodide의 DuckDB 1.5.1로 Parquet 로딩과 SQL 실행을 확인했습니다.

## 정적 빌드와 검증

```bash
.venv/bin/python -m unittest discover -s dashboard/tests -v
.venv/bin/python dashboard/build.py
.venv/bin/python -m http.server 8000 --directory dashboard/dist
```

[로컬 대시보드](http://localhost:8000)를 엽니다. `index.html`을 파일로 직접 열지 말고 HTTP로 확인합니다. 이 서버는 로컬 미리보기 용도이며 GitHub Pages 운영에는 필요하지 않습니다.

브라우저는 첫 접속 시 CDN에서 marimo·Pyodide·Python 패키지를 내려받으므로 초기 로딩에 시간이 걸릴 수 있습니다. 다음 접속에는 브라우저 캐시가 사용됩니다. 인터넷 연결이 필요하며 완전한 오프라인 배포 구성은 아닙니다.

빌드는 커밋된 집계 파일만 사용합니다. CI는 대용량 원본 다운로드 없이 합계·공개 열·결측 범주·JSON/Parquet 일치 등을 검증합니다. 원본이 있는 로컬 환경에서는 전체·가입 상태별·복합 필터 합계와 SHA256까지 대조합니다. 원본이 없는 CI에서는 원본 복합 필터 대조와 원본 SHA256 검사 2개만 명시적으로 생략합니다.

## GitHub Pages 게시

대시보드 전용 저장소는 `corazzon/nps-marimo-dashboard`입니다. 현재 작업 폴더의 기존 Git 저장소 전체를 푸시하지 않고, `publish.py`가 대시보드와 배포에 필요한 파일만 별도 저장소로 동기화합니다. 원본 CSV·가상환경·임시 빌드·기존 작업물은 게시 대상에서 제외합니다.

최초 생성과 게시:

```bash
.venv/bin/python dashboard/publish.py --create
```

이후 변경 게시:

```bash
.venv/bin/python dashboard/publish.py
```

GitHub CLI(`gh`) 설치와 해당 계정 인증이 필요합니다. 워크플로는 빌드 성공 후 GitHub Pages에 게시하며, 저장소의 **Actions → 국민연금 대시보드 배포**에서 실행 결과를 확인할 수 있습니다. 별도 개인 액세스 토큰을 저장소 비밀 값에 추가하지 않고 GitHub Actions의 Pages 권한을 사용합니다.

**배포 주소:** [국민연금 가입 사업장 대시보드](https://corazzon.github.io/nps-marimo-dashboard/). 2026년 11월 26일 GitHub Actions의 빌드·검증·Pages 배포 성공과 공개 주소의 HTTP 200 응답을 확인했습니다.

다른 저장소에 직접 배포할 경우 `dashboard/`와 `.github/workflows/deploy-dashboard.yml`을 함께 올리고 **Settings → Pages → Build and deployment → Source → GitHub Actions**를 선택합니다. 배포 출력인 `index.html`, `assets/`, `public/`, `.nojekyll`을 함께 유지해야 합니다.

## 최신 자료로 갱신

수집에는 Scrapling이 필요합니다. 기존 루트 환경에는 이미 설치되어 있으며, 새 전용 저장소 환경에서 수집할 때만 추가 설치합니다.

```bash
uv pip install --python .venv/bin/python "scrapling[fetchers]==0.4.14"
.venv/bin/python dashboard/download_latest.py --help
.venv/bin/python dashboard/download_latest.py
.venv/bin/python dashboard/prepare_data.py
.venv/bin/python -m unittest discover -s dashboard/tests -v
.venv/bin/python dashboard/build.py
.venv/bin/python dashboard/publish.py
```

수집기는 공식 페이지의 Dataset 메타데이터로 현재 게시일을 확인하고, 다운로드 버튼의 식별자로 공식 파일 정보 요청을 보낸 뒤 CSV를 내려받습니다. 원본은 게시일을 붙인 `data/nps_workplaces_YYYYMMDD.csv`, 새 수집 기록은 `data/download_manifest_latest.csv`에 저장합니다. 과거 `data/download_manifest.csv`는 덮어쓰지 않습니다. 같은 게시일 파일의 내용이 달라지면 기존 원본을 덮어쓰지 않고 중단합니다.

`prepare_data.py`는 기본적으로 새 수집 기록에 적힌 원본을 선택합니다. 특정 파일을 재현하려면 경로를 명시합니다.

```bash
.venv/bin/python dashboard/prepare_data.py \
  --source data/nps_workplaces_20261123.csv \
  --manifest data/download_manifest_latest.csv
.venv/bin/python dashboard/prepare_data.py --help
```

이번 수집에서 공식 페이지 게시일·수정일은 모두 2026-11-23이었고 CSV 내부 기준월은 2026-10이었습니다. 원본의 SHA256은 `0b0d09d958f558a5ef2989aff2ff06524b248b072a4eacd3c51989c109f7cf62`입니다. DuckDB 집계 합계는 표준 `csv` 모듈로 원본을 별도 순회한 합계와 일치했고, 저장한 Parquet을 다시 읽은 합계도 일치했습니다. 완전 중복은 0행, 가입자 0명 기록은 34,658행, 업종명 결측은 712행이며 측정값 결측·음수는 없었습니다.

지역명은 원본 법정동 시도코드 기준입니다. 코드 12의 ‘전남광주통합특별시’는 원본 주소에 적힌 이름으로, 현재 공식 행정구역이라는 의미로 사용하지 않습니다. 구 코드와 새 코드를 임의 통합하지 않습니다.

제공기관의 새 파일 게시와 이 대시보드의 갱신은 별개입니다. 새 원본으로 수집·집계·재게시하기 전에는 기존 스냅샷을 표시합니다. GitHub Actions는 원본을 자동 수집하지 않으며, 단일 기준월 자료로 시계열 추세를 추정하지 않습니다.

## 참고 문서

- [marimo WebAssembly 내보내기](https://docs.marimo.io/guides/exporting/webassembly_html/)
- [marimo 데이터 파일 포함](https://docs.marimo.io/guides/wasm/)
- [marimo GitHub Pages 배포](https://docs.marimo.io/guides/publishing/github/)
- [GitHub Pages 사용자 지정 워크플로](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
