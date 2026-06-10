from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"


KEYS = [
    ("DEEPSEEK_API_KEY", "DeepSeek API Key（可跳过，原文模式不需要）"),
    ("NCBI_API_KEY", "NCBI/PubMed API Key（可跳过，跳过后仍可抓 RSS）"),
    ("NCBI_EMAIL", "NCBI 联系邮箱（可跳过）"),
]


def _read_env() -> dict[str, str]:
    result: dict[str, str] = {}
    source = ENV_PATH if ENV_PATH.exists() else EXAMPLE_PATH
    if not source.exists():
        return result
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _write_env(values: dict[str, str]) -> None:
    template = EXAMPLE_PATH.read_text(encoding="utf-8") if EXAMPLE_PATH.exists() else ""
    seen: set[str] = set()
    lines = []
    for line in template.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in values:
                lines.append(f"{key}={values[key]}")
                seen.add(key)
                continue
        lines.append(line)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    try:
        ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    except PermissionError as exc:
        print("", file=sys.stderr)
        print(f"Cannot save .env file: {ENV_PATH}", file=sys.stderr)
        print(
            "This folder is not writable. Move the extracted PaperRadar folder to Desktop, Downloads, or C:\\PaperRadar, then run Windows-Install.bat again.",
            file=sys.stderr,
        )
        print("Do not run it from WeChat/QQ file cache or a zip preview window.", file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> None:
    values = _read_env()
    print()
    print("API 配置")
    print("直接回车会保留已有值；没有 key 也可以跳过。")
    print()
    for key, label in KEYS:
        current = values.get(key, "")
        shown = "已设置" if current else "未设置"
        new_value = input(f"{label}（当前：{shown}）：").strip()
        if new_value:
            values[key] = new_value
    _write_env(values)
    print()
    print(".env 已保存。")


if __name__ == "__main__":
    main()
