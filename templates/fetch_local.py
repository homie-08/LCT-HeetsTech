"""Собирает локальный набор шаблонов для тестов.

Организаторы шаблоны не выдали, поэтому берём те, что уже есть на машине:
поставляемые с Microsoft Office .potx и темы .thmx. В репозиторий они не
попадают (см. .gitignore) — набор воспроизводится этой командой.

    python templates/fetch_local.py [--list]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Где Office держит шаблоны и темы. 1049 — русская локаль, en-US тоже проверяем.
SEARCH_ROOTS = [
    Path(r"C:\Program Files\Microsoft Office\root\Templates"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Templates"),
    Path(r"C:\Program Files\Microsoft Office\root\Document Themes 16"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Document Themes 16"),
    Path(r"C:\Program Files\LibreOffice\share\template"),
]

PATTERNS = ("*.potx", "*.pptx", "*.thmx", "*.otp")


def discover() -> list[Path]:
    found: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for pattern in PATTERNS:
            found.extend(sorted(root.rglob(pattern)))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="только показать найденное")
    args = parser.parse_args()

    found = discover()
    if not found:
        print("Ничего не найдено. Положите шаблоны в templates/ вручную.", file=sys.stderr)
        return 1

    for src in found:
        kind = "theme" if src.suffix.lower() == ".thmx" else "deck"
        dst = HERE / kind / src.name
        if args.list:
            print(f"{src.stat().st_size / 1024:8.0f} КБ  {src}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"→ {dst.relative_to(HERE.parent)}")

    if not args.list:
        print(f"\nВсего: {len(found)} файлов в {HERE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
