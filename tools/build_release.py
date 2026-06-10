from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ZIP_PATH = DIST / "PaperRadar-Windows.zip"
PACKAGE_ROOT = "PaperRadar"


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


def main() -> None:
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


if __name__ == "__main__":
    main()
