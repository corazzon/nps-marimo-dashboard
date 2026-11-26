"""대시보드 공개 파일만 임시 Git 저장소에서 GitHub Pages 저장소로 올린다."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


PUBLIC_FILES = (
    "dashboard/app.py",
    "dashboard/explorer.py",
    "dashboard/build.py",
    "dashboard/prepare_data.py",
    "dashboard/prepare_raw.py",
    "dashboard/download_latest.py",
    "dashboard/requirements.txt",
    "dashboard/README.md",
    "dashboard/.gitignore",
    "dashboard/publish.py",
    "dashboard/tests/test_snapshot.py",
    "dashboard/public/data/metadata.json",
    "dashboard/public/data/snapshot.parquet",
    "dashboard/public/data/snapshot.json.gz",
    "dashboard/public/data/raw.parquet",
    "dashboard/public/data/raw_metadata.json",
    ".github/workflows/deploy-dashboard.yml",
)


def run(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """셸을 거치지 않고 명령을 실행하며 인증정보를 직접 다루지 않는다."""
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=check,
        capture_output=capture,
        text=True,
    )


def pages_url(repository: str) -> str:
    """저장소 이름에 대응하는 기본 GitHub Pages 주소를 만든다."""
    owner, name = repository.split("/", 1)
    suffix = "" if name.lower() == f"{owner.lower()}.github.io" else f"{name}/"
    return f"https://{owner.lower()}.github.io/{suffix}"


def ensure_pages(repository: str) -> None:
    """최초 게시 요청에서만 Pages의 GitHub Actions 배포를 설정한다."""
    endpoint = f"repos/{repository}/pages"
    existing = run(["gh", "api", endpoint], capture=True, check=False)
    if existing.returncode == 0:
        current = json.loads(existing.stdout)
        if current.get("build_type") != "workflow":
            raise RuntimeError(
                "기존 Pages가 다른 방식으로 배포되고 있습니다. "
                "저장소의 Pages 설정을 확인해 주세요."
            )
        return
    if "HTTP 404" not in existing.stderr:
        raise RuntimeError("Pages 설정을 확인하지 못했습니다. gh의 접근 권한을 확인해 주세요.")
    run(["gh", "api", "--method", "POST", endpoint, "-f", "build_type=workflow"], capture=True)


def publish(repository: str, *, create: bool, message: str) -> None:
    """기존 워크스페이스 Git 설정을 바꾸지 않고 명시한 파일만 게시한다."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repository):
        raise ValueError("저장소는 계정/저장소 형식으로 입력해 주세요.")
    for executable in ("gh", "git"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"{executable} 명령이 필요합니다.")

    source_root = Path(__file__).resolve().parent.parent
    # 파일이 빠진 상태에서 원격 저장소를 만들거나 변경하지 않는다.
    for relative in PUBLIC_FILES:
        source = source_root / relative
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"공개할 파일이 없거나 일반 파일이 아닙니다: {relative}")

    identity = json.loads(
        run(
            ["gh", "api", "user", "--jq", "{login: .login, id: .id}"],
            capture=True,
        ).stdout
    )
    existing = run(
        ["gh", "repo", "view", repository, "--json", "nameWithOwner"],
        capture=True,
        check=False,
    )
    if existing.returncode != 0:
        if not create:
            raise RuntimeError(
                "지정 저장소에 접근할 수 없습니다. 최초 생성이라면 --create를 사용해 주세요."
            )
        run(
            ["gh", "repo", "create", repository, "--public", "--description",
             "최신 국민연금 사업장 데이터를 marimo와 DuckDB로 탐색하는 정적 대시보드"],
        )

    with tempfile.TemporaryDirectory(prefix="nps-dashboard-publish-") as temporary:
        checkout = Path(temporary) / "repository"
        run(["gh", "repo", "clone", repository, str(checkout), "--", "--depth=1"])
        run(["git", "config", "user.name", str(identity["login"])], cwd=checkout)
        run(
            ["git", "config", "user.email",
             f"{identity['id']}+{identity['login']}@users.noreply.github.com"],
            cwd=checkout,
        )
        has_commit = run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=checkout,
            capture=True,
            check=False,
        ).returncode == 0
        if not has_commit:
            run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=checkout)

        for relative in PUBLIC_FILES:
            destination = checkout / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / relative, destination)
        (checkout / "README.md").write_text(
            "# 국민연금 사업장 분석 대시보드\n\n"
            f"[대시보드 열기]({pages_url(repository)})\n\n"
            "최신 공개 자료를 marimo와 DuckDB로 분석합니다. "
            "Python 계산과 SQL 조회는 브라우저에서 실행하며 별도 운영 서버가 필요하지 않습니다.\n\n"
            "[실행·데이터 갱신·배포 안내](dashboard/README.md)\n",
            encoding="utf-8",
        )
        (checkout / ".gitignore").write_text(
            "# 로컬 원본·가상환경·재생성 가능한 출력은 공개하지 않습니다.\n"
            ".venv/\n/data/\n__pycache__/\n*.py[cod]\n.DS_Store\n",
            encoding="utf-8",
        )
        run(["git", "add", "--", *PUBLIC_FILES, "README.md", ".gitignore"], cwd=checkout)
        difference = run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=checkout,
            capture=True,
            check=False,
        )
        if difference.returncode not in (0, 1):
            raise RuntimeError("게시할 변경 내역을 확인하지 못했습니다.")
        if difference.returncode == 1:
            run(["git", "commit", "-m", message], cwd=checkout)
            run(["git", "push", "origin", "HEAD:main"], cwd=checkout)
            print("대시보드 변경을 main 브랜치에 올렸습니다.")
        else:
            print("공개할 파일에 변경이 없습니다.")
        if create:
            ensure_pages(repository)

    print(f"저장소: https://github.com/{repository}")
    print(f"Pages 배포 대상: {pages_url(repository)}")
    print("실제 게시 완료 여부는 GitHub Actions의 배포 결과에서 확인해 주세요.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", default="corazzon/nps-marimo-dashboard", help="배포할 계정/저장소"
    )
    parser.add_argument(
        "--create", action="store_true", help="없는 저장소를 공개로 만들고 Pages를 최초 설정"
    )
    parser.add_argument(
        "--message", default="국민연금 대시보드 갱신", help="변경 커밋 설명"
    )
    args = parser.parse_args()
    try:
        publish(args.repo, create=args.create, message=args.message)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"게시 중단: {error}\n")


if __name__ == "__main__":
    main()
