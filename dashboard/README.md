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

| 화면 | 경로 | 용도 |
| --- | --- | --- |
| 요약 대시보드 | `/` | 핵심 지표·구성·차트·집계 SQL 분석 |
| 코드 편집 노트북 | `/editor/` | Python 셀 편집·추가·실행과 수정본 내려받기 |
| 전체 데이터 탐색 | `/explorer/` | 원본 588,075행·22열 검색·범위 조회·SQL 분석 |

상단은 자료 기준월, 핵심 지표, 지역별 가입자 구성과 화면 이동을 묶어 보여줍니다. 왼쪽의 업종 수 슬라이더는 비교 차트의 상위 업종을 **5~25개**로 조정합니다.

- 지역·가입 상태·사업장 형태·업종·가입자 규모 필터와 사업장·가입자·고지금액·취득/상실 지표
- 지역·업종·규모별 비교 및 신규취득/상실 비교 차트
- 현재 조건의 전체 집계 표와 CSV 다운로드
- DuckDB SQL 편집기, 예제 쿼리, 실행 시간, `EXPLAIN` 계획, SQL 결과 CSV
- 슬라이더에 따른 셀 재실행, 차트 선택과 표 연동, `mo.sql`을 확인하는 마리모 기능 체험
- 원본 게시일·수집일·SHA256·결측·중복·집계 기준을 확인하는 출처·품질 탭

SQL의 `workplaces`는 공개 집계 전체, `selection`은 현재 탐색 조건의 집계입니다. 한 집계행에 여러 사업장 기록이 포함되므로 사업장 수는 `COUNT(*)`가 아니라 `SUM(workplaces)`로 계산합니다.

DuckDB는 원본의 사전 집계와 브라우저의 조건별 집계·직접 SQL 조회에 사용합니다. 원본 114,885,359바이트에서 집계 Parquet 521,221바이트를 생성했으며, 브라우저가 Parquet을 한 번 받은 뒤 같은 메모리 연결을 재사용합니다. 반응형 셀은 바뀐 입력을 사용하는 셀을 갱신하고, 단일 Python 소스와 GitHub Actions로 실행·배포 과정을 재현합니다.

## 브라우저에서 코드 편집

대시보드 상단의 **노트북 편집**을 눌러 `/editor/`를 엽니다. 편집기는 같은 `app.py`를 marimo의 네이티브 편집 모드로 실행합니다.

1. 첫 접속에서는 우하단의 노란 **▶ 전체 실행** 버튼을 누릅니다. 단축키는 **⌘/Ctrl+Shift+R**입니다. 편집기에서는 자동으로 모든 셀을 실행하지 않습니다.
2. Python 셀을 수정한 뒤 **⌘/Ctrl+Enter**로 실행합니다. 바뀐 셀을 사용하는 결과가 의존관계에 따라 갱신됩니다.
3. 하단의 **Python**으로 새 셀을 추가해 계산·표·차트를 작성할 수 있습니다. 기존 변수는 새 셀에서 사용할 수 있습니다.
4. 수정한 내용은 우측 메뉴의 **Download → Download notebook source**로 Python 수정본을 보관합니다. 내려받기 전에 **⌘/Ctrl+S**를 눌러 현재 코드를 저장하세요. 페이지를 새로고침하거나 닫기 전에 필요한 수정본을 내려받으세요.

편집 내용은 방문자의 브라우저 세션에서 실행되며 GitHub 저장소나 다른 방문자의 공개 화면에 자동 저장되지 않습니다. 수정본을 운영 화면에 반영하려면 내려받은 Python 소스를 로컬 `dashboard/app.py`에 적용하고 검증·빌드 후 `publish.py`로 다시 게시합니다. 현재 배포 파이프라인의 입력은 Python 노트북 소스입니다.

편집기 상단의 **배포 원본 .py**는 `public/notebooks/app.py`에 있는 **현재 배포된 원본**입니다. 브라우저에서 수정한 내용은 이 파일에 포함되지 않습니다. `public/notebooks/explorer.py`도 각 화면에서 내려받을 수 있습니다.

## 전체 원본 데이터 탐색

`/explorer/`에서 **전체 데이터 불러오기**를 누르면 약 **25.3MB**의 Parquet을 받습니다. 요약 대시보드나 편집기 진입만으로 이 파일을 받지는 않습니다. 파일을 준비한 뒤 DuckDB가 원본 전체 588,075행을 대상으로 질의하며, 화면에는 현재 페이지의 50·100·200행만 렌더링합니다.

- 사업장명·공개 주소 검색과 지역·가입 상태·사업장 형태 조건을 결합합니다.
- 가입자 수 범위 슬라이드바의 **두 손잡이**로 최소·최대 인원을 정합니다.
- 조회 페이지 슬라이드바를 움직이거나 숫자를 직접 입력하여 페이지를 이동합니다.
- **현재 페이지 CSV**는 현재 검색·범위·정렬 조건의 **표시된 페이지 행만** 내려받습니다. 검색 결과 전체를 내려받는 기능과 구분합니다.
- **전체 원본 SQL**의 `raw_workplaces`는 원본 전체 테이블입니다. 탐색 화면의 검색·슬라이드바 조건은 SQL에 자동 적용되지 않으므로 필요한 `WHERE` 조건을 직접 작성합니다.
- SQL의 화면 표시와 CSV 다운로드는 같은 결과를 사용하며 **최대 3,000행**으로 제한됩니다. 사업장 수는 원본 테이블에서 `COUNT(*)`로 계산할 수 있습니다.

원본 22개 열을 모두 보존하며 코드·우편번호·일자 열은 문자열로 유지합니다. 가입자 수·고지금액·신규취득·상실 인원은 정수입니다. 열별 자료형·결측 행 수와 출처는 **원본 열·출처** 탭에서 확인합니다.

## 파일 구성

- `app.py`: 요약 대시보드와 동일 소스를 사용하는 편집 노트북
- `explorer.py`: 전체 원본 검색·슬라이드바·페이지 조회·원본 SQL 탐색
- `download_latest.py`: 공식 다운로드 버튼의 요청 계약으로 최신 공개 CSV 수집
- `prepare_data.py`: DuckDB SQL 집계, 출처·품질 검증, Parquet·JSON 생성
- `prepare_raw.py`: 원본 22개 열을 보존한 전체 조회용 Parquet과 출처 생성
- `public/data/snapshot.parquet`: 브라우저가 읽는 공개 집계, 약 509KB
- `public/data/metadata.json`: 출처·기준월·합계·품질 메타데이터
- `public/data/snapshot.json.gz`: 집계 검증용 스냅샷
- `public/data/raw.parquet`: 전체 원본 588,075행·22열, 약 25.3MB
- `public/data/raw_metadata.json`: 원본 열·자료형·결측·파일 무결성 기록
- `build.py`: `dist/`, `dist/editor/`, `dist/explorer/`의 세 정적 화면 생성
- `publish.py`: 대시보드 전용 GitHub 저장소에 선별 동기화·게시
- `requirements.txt`: 로컬·CI 빌드 패키지 버전
- `tests/test_snapshot.py`: 원본·집계·Parquet 대조 검증
- `../.github/workflows/deploy-dashboard.yml`: GitHub Pages 자동 배포

요약 대시보드와 편집 노트북의 데이터는 지역·업종·규모별 집계입니다. **전체 원본 탐색에는 제공기관이 공개한 원본의 22개 열을 보존**하므로 사업장명·공개 주소·사업자등록번호 열도 제공기관의 값 그대로 포함됩니다. 원본 CSV를 별도로 게시하지 않고 전체 조회용 Parquet으로 제공합니다.

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

[로컬 대시보드](http://localhost:8000), [편집 노트북](http://localhost:8000/editor/), [전체 데이터 탐색](http://localhost:8000/explorer/)을 엽니다. `index.html`을 파일로 직접 열지 말고 HTTP로 확인합니다. 이 서버는 로컬 미리보기 용도이며 GitHub Pages 운영에는 필요하지 않습니다.

브라우저는 첫 접속 시 CDN에서 marimo·Pyodide·Python 패키지를 내려받으므로 초기 로딩에 시간이 걸릴 수 있습니다. 다음 접속에는 브라우저 캐시가 사용됩니다. 인터넷 연결이 필요하며 완전한 오프라인 배포 구성은 아닙니다.

빌드는 커밋된 집계와 전체 조회용 Parquet을 사용하며 원본 CSV를 다시 받지 않습니다. 기본 화면과 편집기에는 요약 데이터만 복사하고 **전체 원본 파일은 `explorer/public/data/`에만 포함**합니다. 각 화면의 프런트엔드 자산을 독립적으로 내보내므로 전체 빌드 출력은 약 109MB입니다. 세 화면과 다운로드 파일이 모두 완성된 뒤 기존 출력을 교체합니다.

CI는 원본 CSV 다운로드 없이 집계 합계·공개 열·결측 범주·JSON/Parquet 일치와 전체 데이터의 행·열·자료형·SHA256 등을 검증합니다. 원본 CSV가 있는 로컬 환경에서는 전체·가입 상태별·복합 필터 합계와 원본 SHA256까지 추가 대조하며, CSV가 없는 환경의 원본 대조는 명시적으로 생략합니다.

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

**서비스 주소:** [요약 대시보드](https://corazzon.github.io/nps-marimo-dashboard/) · [편집 노트북](https://corazzon.github.io/nps-marimo-dashboard/editor/) · [전체 데이터 탐색](https://corazzon.github.io/nps-marimo-dashboard/explorer/).

세 화면은 같은 정적 배포에 포함됩니다. 기본 대시보드에서 편집기와 전체 원본 탐색으로 이동할 수 있으며, 배포 상태는 저장소의 최신 GitHub Actions 실행 결과에서 확인합니다.

다른 저장소에 직접 배포할 경우 `dashboard/`와 `.github/workflows/deploy-dashboard.yml`을 함께 올리고 **Settings → Pages → Build and deployment → Source → GitHub Actions**를 선택합니다. 배포 출력인 `index.html`, `assets/`, `public/`, `.nojekyll`과 `editor/`, `explorer/` 하위 폴더 전체를 함께 유지해야 합니다.

## 최신 자료로 갱신

수집에는 Scrapling이 필요합니다. 기존 루트 환경에는 이미 설치되어 있으며, 새 전용 저장소 환경에서 수집할 때만 추가 설치합니다.

```bash
uv pip install --python .venv/bin/python "scrapling[fetchers]==0.4.14"
.venv/bin/python dashboard/download_latest.py --help
.venv/bin/python dashboard/download_latest.py
.venv/bin/python dashboard/prepare_data.py
.venv/bin/python dashboard/prepare_raw.py
.venv/bin/python -m unittest discover -s dashboard/tests -v
.venv/bin/python dashboard/build.py
.venv/bin/python dashboard/publish.py
```

수집기는 공식 페이지의 Dataset 메타데이터로 현재 게시일을 확인하고, 다운로드 버튼의 식별자로 공식 파일 정보 요청을 보낸 뒤 CSV를 내려받습니다. 원본은 게시일을 붙인 `data/nps_workplaces_YYYYMMDD.csv`, 새 수집 기록은 `data/download_manifest_latest.csv`에 저장합니다. 과거 `data/download_manifest.csv`는 덮어쓰지 않습니다. 같은 게시일 파일의 내용이 달라지면 기존 원본을 덮어쓰지 않고 중단합니다.

`prepare_data.py`는 기본적으로 새 수집 기록에 적힌 원본을 선택합니다. **먼저 집계를 갱신한 다음 `prepare_raw.py`를 실행**하면 새 집계의 출처에 적힌 동일 원본으로 전체 조회 파일을 생성합니다. 두 파일의 원본 SHA256이 다르면 빌드가 중단됩니다. 특정 파일을 재현하려면 경로를 명시합니다.

```bash
.venv/bin/python dashboard/prepare_data.py \
  --source data/nps_workplaces_20261123.csv \
  --manifest data/download_manifest_latest.csv
.venv/bin/python dashboard/prepare_raw.py \
  --source data/nps_workplaces_20261123.csv \
  --metadata dashboard/public/data/metadata.json
.venv/bin/python dashboard/prepare_data.py --help
.venv/bin/python dashboard/prepare_raw.py --help
```

이번 수집에서 공식 페이지 게시일·수정일은 모두 2026-11-23이었고 CSV 내부 기준월은 2026-10이었습니다. 원본의 SHA256은 `0b0d09d958f558a5ef2989aff2ff06524b248b072a4eacd3c51989c109f7cf62`입니다. DuckDB 집계 합계는 표준 `csv` 모듈로 원본을 별도 순회한 합계와 일치했고, 저장한 Parquet을 다시 읽은 합계도 일치했습니다. 완전 중복은 0행, 가입자 0명 기록은 34,658행, 업종명 결측은 712행이며 측정값 결측·음수는 없었습니다.

지역명은 원본 법정동 시도코드 기준입니다. 코드 12의 ‘전남광주통합특별시’는 원본 주소에 적힌 이름으로, 현재 공식 행정구역이라는 의미로 사용하지 않습니다. 구 코드와 새 코드를 임의 통합하지 않습니다.

제공기관의 새 파일 게시와 이 대시보드의 갱신은 별개입니다. 새 원본으로 수집·집계·재게시하기 전에는 기존 스냅샷을 표시합니다. GitHub Actions는 원본을 자동 수집하지 않으며, 단일 기준월 자료로 시계열 추세를 추정하지 않습니다.

## 참고 문서

- [marimo WebAssembly 내보내기](https://docs.marimo.io/guides/exporting/webassembly_html/)
- [marimo 데이터 파일 포함](https://docs.marimo.io/guides/wasm/)
- [marimo GitHub Pages 배포](https://docs.marimo.io/guides/publishing/github/)
- [GitHub Pages 사용자 지정 워크플로](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
