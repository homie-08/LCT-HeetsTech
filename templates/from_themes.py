"""Делает шаблоны презентаций из тем оформления Office.

`.thmx` — это дизайн-система без макетов: палитра, пара шрифтов, стили заливок
и эффектов. PowerPoint умеет применить её к презентации, получив полноценный
набор мастеров и макетов в этом стиле. Так из десяти установленных тем
получаются десять непохожих шаблонов — куда более современных, чем поставляемые
с Office «деловые» заготовки, и хорошая проверка адаптивности решения.

    python templates/from_themes.py [--only Ion Slice]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
THEMES = HERE / "theme"
OUT = HERE / "deck"

# Именно OpenXML-шаблон: ppSaveAsTemplate (5) — это старый бинарный .pot,
# PowerPoint дописывает к нему расширение и отдаёт файл на 16 МБ.
PP_SAVE_AS_OPENXML_TEMPLATE = 26


def build(theme: Path, target: Path) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = presentation = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        presentation = app.Presentations.Add(WithWindow=False)
        presentation.PageSetup.SlideSize = 15          # ppSlideSizeOnScreen16x9
        presentation.ApplyTheme(str(theme))
        # Один слайд нужен, чтобы PowerPoint зафиксировал мастер и макеты.
        presentation.Slides.Add(1, 11)                 # ppLayoutTitleOnly
        presentation.Slides(1).Delete()
        presentation.SaveAs(str(target), PP_SAVE_AS_OPENXML_TEMPLATE)
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        app = presentation = None
        pythoncom.CoUninitialize()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="имена тем без расширения")
    args = parser.parse_args()

    if sys.platform != "win32":
        print("нужен PowerPoint: тема применяется через COM", file=sys.stderr)
        return 2
    if not THEMES.exists():
        print("нет тем — запустите templates/fetch_local.py", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    wanted = {name.lower() for name in (args.only or [])}
    made = 0
    for theme in sorted(THEMES.glob("*.thmx")):
        if wanted and theme.stem.lower() not in wanted:
            continue
        target = OUT / f"{theme.stem.replace(' ', '')}Theme.potx"
        try:
            build(theme, target)
        except Exception as error:
            print(f"  {theme.stem}: не получилось — {error}")
            continue
        print(f"→ {target.relative_to(HERE.parent)}")
        made += 1

    print(f"\nготово: {made} шаблонов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
