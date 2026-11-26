"""실제 다운로드 버튼에서 확인한 요청으로 최신 공개 CSV를 별도 보존한다."""

from __future__ import annotations

import csv
import argparse
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from scrapling.fetchers import FetcherSession


LANDING_URL = "https://www.data.go.kr/data/15083277/fileData.do"
DOWNLOAD_INFO_URL = "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do"
MANIFEST = Path("data/download_manifest_latest.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    with FetcherSession(impersonate="chrome", stealthy_headers=True, timeout=240, retries=1) as session:
        landing = session.get(LANDING_URL, headers={"Accept": "text/html,application/xhtml+xml"})
        if landing.status != 200:
            raise RuntimeError(f"페이지 요청 실패: HTTP {landing.status}")
        datasets = []
        for raw in landing.css('script[type="application/ld+json"]::text').getall():
            value = json.loads(str(raw).strip())
            if value.get("@type") == "Dataset":
                datasets.append(value)
        if len(datasets) != 1:
            raise RuntimeError("공식 데이터 게시 정보를 확인하지 못했습니다.")
        metadata = datasets[0]
        button = landing.css('[onclick*="fn_fileDataDown"]::attr(onclick)').get()
        matched = re.search(r"fn_fileDataDown\('([^']+)',\s*'([^']+)',\s*'([^']*)',\s*'([^']+)'", str(button))
        if not matched or matched.group(1) != "15083277":
            raise RuntimeError("최신 파일의 다운로드 버튼 계약이 변경되었습니다.")
        payload = {
            "publicDataDetailPk": matched.group(2), "publicDataPk": matched.group(1),
            "atchFileId": matched.group(3), "fileDetailSn": matched.group(4),
            "publicDataTyCode": "PR0051", "url": "/tcs/dss/selectFileDataDownload.do",
        }
        info_response = session.post(DOWNLOAD_INFO_URL, data=payload, headers={"Referer": LANDING_URL})
        if info_response.status != 200:
            raise RuntimeError(f"다운로드 정보 요청 실패: HTTP {info_response.status}")
        info = json.loads(info_response.body)
        if info.get("status") is not True:
            raise RuntimeError("공식 다운로드 정보 응답이 성공 상태가 아닙니다.")
        file_info = info["fileDataRegistVO"]
        if str(file_info["atchFileExtsn"]).lower() != "csv":
            raise RuntimeError("공식 첨부 파일이 CSV가 아닙니다.")
        download_url = "https://www.data.go.kr/cmm/cmm/fileDownload.do?" + urlencode({
            "atchFileId": info["atchFileId"], "fileDetailSn": info["fileDetailSn"], "insertDataPrcus": "N",
        })
        response = session.get(download_url, headers={"Accept": "text/csv,application/octet-stream,*/*", "Referer": LANDING_URL})
        if response.status != 200:
            raise RuntimeError(f"파일 요청 실패: HTTP {response.status}")
        if response.body.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            raise RuntimeError("CSV 대신 HTML을 받았습니다. 인증·차단 응답을 확인하세요.")
        decoded = response.body.decode("cp949")
        row_count = sum(1 for _ in csv.DictReader(io.StringIO(decoded)))
        if row_count == 0 or "자료생성년월" not in decoded.splitlines()[0]:
            raise RuntimeError("내려받은 파일의 원본 스키마 또는 행 수가 잘못되었습니다.")
        published = metadata["datePublished"]
        output = Path("data") / f"nps_workplaces_{published.replace('-', '')}.csv"
        digest = hashlib.sha256(response.body).hexdigest()
        if output.exists() and hashlib.sha256(output.read_bytes()).hexdigest() != digest:
            raise RuntimeError("같은 게시일의 다른 원본이 존재합니다. 기존 파일을 보존하고 확인하세요.")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(response.body)
        record = {
            "수집시각": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
            "데이터명": metadata["name"], "게시일": published, "수정일": metadata["dateModified"],
            "랜딩URL": LANDING_URL, "다운로드URL": download_url, "저장경로": output.as_posix(),
            "파일크기_바이트": len(response.body), "추정_데이터행수": row_count,
            "원본인코딩": "cp949", "SHA256": digest,
        }
        with MANIFEST.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(record))
            writer.writeheader()
            writer.writerow(record)
    print(f"최신 게시일: {published}")
    print(f"원본 저장: {output} ({row_count:,}행)")
    print(f"출처 기록 저장: {MANIFEST}")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
