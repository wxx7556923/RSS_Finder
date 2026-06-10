from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ZIP_PATH = DIST / "PaperRadar-Windows.zip"
PACKAGE_ROOT = "PaperRadar"
WHEEL_DIR = ROOT / "wheels"
DEFAULT_WINDOWS_PYTHON_VERSIONS = ("310", "311", "312", "313")
DEFAULT_WINDOWS_PLATFORM = "win_amd64"
DEFAULT_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
LOCAL_BUILD_WHEELS = ("sgmllib3k==1.0.0",)
WHEELHOUSE_REQUIREMENTS = (
    "annotated-types==0.7.0",
    "anyio==4.13.0",
    "certifi==2026.5.20",
    "click==8.4.1",
    "colorama==0.4.6",
    "exceptiongroup==1.3.1",
    "fastapi==0.115.6",
    "feedparser==6.0.11",
    "h11==0.16.0",
    "httpcore==1.0.9",
    "httpx==0.28.1",
    "idna==3.18",
    "jinja2==3.1.5",
    "MarkupSafe==3.0.3",
    "pydantic==2.13.4",
    "pydantic-core==2.46.4",
    "python-dotenv==1.0.1",
    "PyYAML==6.0.2",
    "socksio==1.0.0",
    "starlette==0.41.3",
    "typing-extensions==4.15.0",
    "typing-inspection==0.4.2",
    "uvicorn==0.34.0",
)


EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "dist",
    "volumes",
}

EXCLUDE_FILES = {
    ".env",
    "data/rss_ai.db",
    "logs/app.log",
    "logs/web.log",
    "logs/paper-radar.pid",
    "output/output.xml",
    "output/original.xml",
}


def _download_windows_wheels(python_versions: tuple[str, ...], index_url: str) -> None:
    if WHEEL_DIR.exists():
        shutil.rmtree(WHEEL_DIR)
    WHEEL_DIR.mkdir(exist_ok=True)

    local_wheel_cmd = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--wheel-dir",
        str(WHEEL_DIR),
        "--no-deps",
        "--index-url",
        index_url,
        *LOCAL_BUILD_WHEELS,
    ]
    print("Building local pure-Python wheels...")
    subprocess.run(local_wheel_cmd, cwd=ROOT, check=True)

    for python_version in python_versions:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--dest",
            str(WHEEL_DIR),
            "--only-binary=:all:",
            "--no-deps",
            "--platform",
            DEFAULT_WINDOWS_PLATFORM,
            "--implementation",
            "cp",
            "--python-version",
            python_version,
            "--index-url",
            index_url,
            *WHEELHOUSE_REQUIREMENTS,
        ]
        print(f"Downloading Windows wheels for Python {python_version}...")
        subprocess.run(cmd, cwd=ROOT, check=True)


def _should_include(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(part in EXCLUDE_DIRS for part in path.relative_to(ROOT).parts):
        return False
    if rel in EXCLUDE_FILES:
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    if rel.startswith("logs/") and path.suffix == ".log":
        return False
    if rel.startswith("output/") and path.suffix == ".xml":
        return False
    if rel.startswith("data/") and path.suffix in {".db", ".sqlite", ".sqlite3"}:
        return False
    return True


def _build_zip() -> None:
    DIST.mkdir(exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or not _should_include(path):
                continue
            rel = path.relative_to(ROOT).as_posix()
            archive.write(path, f"{PACKAGE_ROOT}/{rel}")

    size_mb = ZIP_PATH.stat().st_size / 1024 / 1024
    print(f"Built {ZIP_PATH} ({size_mb:.2f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Paper Radar Windows zip.")
    parser.add_argument(
        "--with-wheels",
        action="store_true",
        help="Download Windows wheels into wheels/ before building the zip.",
    )
    parser.add_argument(
        "--python-version",
        action="append",
        dest="python_versions",
        help="Windows Python version tag for wheels, e.g. 310. Can be repeated.",
    )
    parser.add_argument(
        "--index-url",
        default=DEFAULT_INDEX_URL,
        help="Package index used when --with-wheels is set.",
    )
    args = parser.parse_args()

    if args.with_wheels:
        versions = tuple(args.python_versions or DEFAULT_WINDOWS_PYTHON_VERSIONS)
        _download_windows_wheels(versions, args.index_url)

    _build_zip()


if __name__ == "__main__":
    main()
