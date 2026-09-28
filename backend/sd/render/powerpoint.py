"""Рендер через PowerPoint COM — эталон, с которым сверяются остальные.

Точность здесь абсолютная: слайд рисует тот же движок, который увидит жюри.
Взамен приходится аккуратно обращаться с чужим приложением: если PowerPoint у
пользователя уже открыт, мы работаем в его экземпляре и **не** закрываем его,
а свою презентацию убираем за собой в любом случае.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .base import RenderResult, cached, store

PPT_SAVE_NO = 0


class PowerPointRenderer:
    name = "powerpoint"
    fidelity = 3

    def available(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import win32com.client  # noqa: F401
        except ImportError:
            return False
        return self._powerpoint_registered()

    @staticmethod
    def _powerpoint_registered() -> bool:
        import winreg
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                           "PowerPoint.Application"))
            return True
        except OSError:
            return False

    @staticmethod
    def _acquire(win32com_client):
        """Берёт PowerPoint на время одного рендера.

        Экземпляр намеренно не кешируется между вызовами. Кеш выглядит
        выгоднее — меньше запусков приложения, — но переживший рендер прокси
        приходится освобождать уже за пределами инициализированного апартамента,
        и процесс падает с access violation при завершении. Цена запуска
        (доли секунды) этого не стоит.
        """
        try:
            return win32com_client.GetActiveObject("PowerPoint.Application"), True
        except Exception:
            return win32com_client.DispatchEx("PowerPoint.Application"), False

    @staticmethod
    def _export(slide, target: Path, width_px: int, height_px: int,
                attempts: int = 4) -> None:
        """Экспорт кадра с повтором: PowerPoint — одиночка на всю машину.

        Пока им управляет другой клиент (соседняя сборка, открытое окно), вызов
        отклоняется с «Call was rejected by callee». Это не поломка файла, а
        занятость: подождать и повторить дешевле, чем провалить всю задачу.
        """
        import time

        for attempt in range(attempts):
            try:
                slide.Export(str(target), "PNG", width_px, height_px)
                return
            except Exception:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.4 * 2 ** attempt)

    def render(self, deck: Path, out_dir: Path, width_px: int = 1280) -> RenderResult:
        deck = Path(deck).resolve()
        if (hit := cached(deck, width_px, self.name, Path(out_dir))) is not None:
            return RenderResult(hit, self.name, "из кеша")

        import pythoncom
        import win32com.client

        # PowerPoint разрешает относительные пути от своего рабочего каталога,
        # поэтому наружу отдаём только абсолютные.
        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        pythoncom.CoInitialize()
        app = None
        borrowed = False
        presentation = None
        try:
            app, borrowed = self._acquire(win32com.client)
            try:
                presentation = app.Presentations.Open(str(deck), ReadOnly=True,
                                                      Untitled=False, WithWindow=False)
            except Exception:
                # Чужой экземпляр мог отключиться (RPC_E_DISCONNECTED): прокси
                # остаётся живым объектом Python, но за ним уже никого нет.
                app = win32com.client.DispatchEx("PowerPoint.Application")
                borrowed = False
                presentation = app.Presentations.Open(str(deck), ReadOnly=True,
                                                      Untitled=False, WithWindow=False)
            height_px = int(round(width_px * presentation.PageSetup.SlideHeight
                                  / presentation.PageSetup.SlideWidth))

            images: list[Path] = []
            for index in range(1, presentation.Slides.Count + 1):
                target = out_dir / f"slide-{index:03d}.png"
                self._export(presentation.Slides(index), target, width_px, height_px)
                images.append(target)
            return RenderResult(store(deck, width_px, self.name, images), self.name)
        finally:
            if presentation is not None:
                try:
                    presentation.Close()
                except Exception:
                    pass
            if app is not None and not borrowed:
                try:
                    app.Quit()
                except Exception:
                    pass
            # Прокси освобождаем до закрытия апартамента: сборка мусора после
            # `CoUninitialize` роняет процесс.
            app = presentation = None
            pythoncom.CoUninitialize()
