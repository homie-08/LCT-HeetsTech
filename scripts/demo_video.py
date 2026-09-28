"""Запись видео-демо: живой прогон сервиса от шаблона до готовой презентации.

ТЗ просит «запись экрана без монтажных склеек или живой прогон» до семи минут.
Здесь второе, записанное первым: браузер ведёт скрипт, Playwright пишет
непрерывное видео страницы — ни склеек, ни ускорений. Курсор рисуется
наложением (в браузере его в записи не видно), чтобы зрителю было понятно,
куда нажимают; всё остальное на экране — настоящий интерфейс.

Запуск (из окружения с Playwright, например route-planner):

    python scripts/demo_video.py --out data/out/demo
    python scripts/demo_video.py --out data/out/demo --fast   # репетиция без модели

Сервер должен быть уже поднят (run.cmd), иначе скрипт об этом скажет.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTENT = ROOT / "data" / "content" / "product" / "product.md"

BRIEF = ("Платформа «Поток»: зачем нужна, как устроена, какой эффект дал пилот "
         "и что дальше")

# Накладной курсор: Playwright шлёт настоящие события мыши, поэтому точка
# следует за ними, а на клике расходится круг. Это единственное, чего нет в
# самом интерфейсе, — метка для зрителя.
CURSOR = """
(() => {
  const dot = document.createElement('div');
  dot.style.cssText = `position:fixed;z-index:2147483647;width:18px;height:18px;
    margin:-9px 0 0 -9px;border-radius:50%;pointer-events:none;
    background:rgba(255,255,255,.9);box-shadow:0 0 0 2px rgba(0,119,255,.9),0 2px 8px rgba(0,0,0,.4);
    transition:transform .08s ease-out;opacity:0`;
  const attach = () => document.body && document.body.appendChild(dot);
  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', attach) : attach();
  addEventListener('mousemove', (e) => {
    dot.style.opacity = '1';
    dot.style.left = e.clientX + 'px';
    dot.style.top = e.clientY + 'px';
  }, true);
  addEventListener('mousedown', (e) => {
    dot.style.transform = 'scale(.6)';
    const ring = document.createElement('div');
    ring.style.cssText = `position:fixed;z-index:2147483646;left:${e.clientX}px;top:${e.clientY}px;
      width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;pointer-events:none;
      border:2px solid rgba(0,119,255,.9);transition:all .45s ease-out`;
    document.body.appendChild(ring);
    requestAnimationFrame(() => {
      ring.style.width = ring.style.height = '52px';
      ring.style.margin = '-26px 0 0 -26px';
      ring.style.opacity = '0';
    });
    setTimeout(() => ring.remove(), 500);
  }, true);
  addEventListener('mouseup', () => { dot.style.transform = 'scale(1)'; }, true);
})();
"""


class Demo:
    """Шаги показа. Каждый сам себя объявляет в консоли — по журналу видно,
    на чём прогон сорвался, если сорвался."""

    def __init__(self, page, fast: bool, url: str, slides: int = 12, repair: bool = True,
                 brief: str = BRIEF):
        self.page = page
        self.fast = fast
        self.url = url
        self.slides = slides
        self.repair = repair
        self.brief = brief
        self.started = time.monotonic()

    def say(self, text: str) -> None:
        print(f"[{time.monotonic() - self.started:6.1f} с] {text}", flush=True)

    def pause(self, seconds: float) -> None:
        """Пауза для зрителя: экран должен успеть прочитаться."""
        self.page.wait_for_timeout(seconds * 1000)

    def open(self) -> None:
        self.say("открываю интерфейс")
        self.page.goto(self.url, wait_until="networkidle")
        self.page.add_style_tag(content="*{scrollbar-width:thin}")
        self.pause(2.5)

    def set_model(self) -> None:
        if not self.fast:
            return
        self.say("репетиция: выключаю модель")
        self.page.get_by_label("Выключить модель").click()
        self.pause(0.5)

    def choose_template(self) -> None:
        self.say("выбираю шаблон организаторов")
        self.page.get_by_role("tab", name="Свои").click()
        self.pause(1.5)
        preview = self.page.get_by_role("button",
                                        name="Предварительный просмотр: VK Education").first
        preview.hover()
        self.pause(1)
        preview.click()
        self.pause(4)                      # предпросмотр макетов шаблона
        self.page.get_by_role("button", name="Использовать стиль").click()
        self.pause(1.5)

    def fill_request(self) -> None:
        self.say("бриф и контент-пакет")
        box = self.page.get_by_placeholder("Опишите тему")
        box.click()
        box.type(self.brief, delay=28)
        self.pause(1)
        self.page.set_input_files("input[type=file]", str(CONTENT))
        self.pause(1.5)
        slides = self.page.get_by_label("Сколько слайдов")
        slides.click()
        slides.press("Control+a")
        slides.type(str(self.slides), delay=120)       # поле контролируемое: печатаем, а не подставляем
        self.page.get_by_placeholder("Опишите тему").click()
        self.pause(1.5)

    def outline(self) -> None:
        self.say("структура истории")
        self.page.get_by_label("Собрать структуру").click()
        self.page.get_by_text("Структура готова").wait_for(timeout=240_000)
        self.say("структура готова")
        self.pause(6)

    def build(self) -> None:
        self.say("сборка трёх вариантов")
        self.page.get_by_role("button", name="Создать слайды").click()
        self.page.get_by_role("tab", name="Сбалансированно").wait_for(timeout=420_000)
        self.say("колода собрана")
        self.pause(4)

    def browse(self) -> None:
        self.say("листаю слайды")
        for _ in range(2):
            self.page.get_by_label("Следующий слайд").click()
            self.pause(2.2)

    def variants(self) -> None:
        self.say("три варианта вёрстки")
        for name in ("Сжато", "Просторно", "Сбалансированно"):
            self.page.get_by_role("tab", name=name).click()
            self.pause(2.5)

    def audit(self) -> None:
        self.say("аудит и ремонт по выбору")
        self.page.get_by_role("button", name="Аудит").click()
        self.pause(5)
        boxes = self.page.get_by_role("checkbox")
        if boxes.count() == 0:
            self.say("исправимых находок нет — показываю список и иду дальше")
            self.pause(3)
            return
        boxes.first.check()
        self.pause(1.5)
        if not self.repair:
            self.say("ремонт в этой записи не запускаем — он есть в полном прогоне")
            self.pause(2)
            return
        self.page.get_by_role("button", name="Исправить выбранное").click()
        self.say("пересборка выбранных слайдов")
        # Сначала дожидаемся, что ремонт действительно начался — интерфейс
        # выключает скачивание, — и только потом, что колода снова готова.
        self.wait_busy(timeout=30_000)
        self.wait_ready(timeout=300_000)
        self.say("слайды пересобраны")
        self.pause(4)

    def wait_busy(self, timeout: int = 30_000) -> None:
        """Ждёт начала пересборки: кнопка скачивания гаснет."""
        button = self.page.get_by_role("button", name="Скачать .pptx")
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            if not button.is_enabled():
                return
            self.page.wait_for_timeout(250)
        self.say("ремонт не отметился в интерфейсе — иду дальше")

    def wait_ready(self, timeout: int = 300_000) -> None:
        """Ждёт, пока колода снова готова: кнопка скачивания включается."""
        button = self.page.get_by_role("button", name="Скачать .pptx")
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            if button.is_enabled():
                return
            self.page.wait_for_timeout(1000)
        raise TimeoutError("колода так и не стала готовой")

    def export(self) -> None:
        self.say("экспорт")
        self.wait_ready(timeout=180_000)
        with self.page.expect_download(timeout=120_000) as download:
            self.page.get_by_role("button", name="Скачать .pptx").click()
        target = ROOT / "data" / "out" / "demo" / "презентация.pptx"
        target.parent.mkdir(parents=True, exist_ok=True)
        download.value.save_as(str(target))
        self.say(f"файл сохранён: {target}")
        self.pause(3)

    def run(self) -> None:
        self.open()
        self.set_model()
        self.choose_template()
        self.fill_request()
        self.outline()
        self.build()
        self.browse()
        self.variants()
        self.audit()
        self.export()
        self.say("прогон закончен")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/out/demo", help="куда положить видео")
    parser.add_argument("--url", default="http://127.0.0.1:8021/", help="адрес сервиса")
    parser.add_argument("--fast", action="store_true", help="репетиция без модели")
    parser.add_argument("--slides", type=int, default=12, help="сколько слайдов просить")
    parser.add_argument("--skip-repair", action="store_true",
                        help="показать аудит, но не ждать пересборку (короткая запись)")
    parser.add_argument("--brief", default=BRIEF, help="текст запроса")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=810)
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False,
                                             args=[f"--window-size={args.width},{args.height + 120}"])
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            record_video_dir=str(out),
            record_video_size={"width": args.width, "height": args.height},
            accept_downloads=True,
            locale="ru-RU",
        )
        context.add_init_script(CURSOR)
        page = context.new_page()
        demo = Demo(page, args.fast, args.url, slides=args.slides,
                    repair=not args.skip_repair, brief=args.brief)
        code = 0
        try:
            demo.run()
        except PlaywrightTimeout as error:
            demo.say(f"шаг не дождался: {error}")
            code = 1
        except Exception as error:                    # noqa: BLE001 — журнал прогона
            demo.say(f"сорвалось: {error}")
            code = 1
        finally:
            video = page.video
            context.close()                            # видео пишется на закрытии
            browser.close()
            if video is not None:
                print("видео:", video.path(), flush=True)
        return code


if __name__ == "__main__":
    sys.exit(main())
