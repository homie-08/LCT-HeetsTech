/** Проверки интерфейса: экраны, ветки отказа и путь от запроса до структуры. */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => vi.restoreAllMocks());

const LIBRARY = {
  templates: [
    { id: "html:11 Neon Lime.dc.html", label: "Neon Lime", kind: "html",
      cover: "/api/covers/html-11-Neon-Lime-dc-html.png", origin: "library" },
    { id: "pptx:Pitchbook.potx", label: "Pitchbook", kind: "pptx", origin: "library" },
    { id: "mine:Фирменный.dc.html", label: "Фирменный", kind: "html", origin: "user" },
  ],
  pending: 0,
};

function stubFetch(handler: (url: string) => Response | Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
    Promise.resolve(handler(String(input)))));
}

function ok(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function base(url: string): Response | null {
  if (url.endsWith("/api/library")) return ok(LIBRARY);
  if (url.includes("/api/library/preview")) {
    return ok({ images: ["/p/slide-001.png", "/p/slide-002.png"], pending: 0 });
  }
  if (url.endsWith("/api/status")) return ok({ llm: "", renderers: [] });
  return null;
}

async function askFor(prompt: string) {
  const field = screen.getByPlaceholderText(/Опишите тему/);
  fireEvent.change(field, { target: { value: prompt } });
  fireEvent.click(screen.getByRole("button", { name: "Собрать структуру" }));
}

describe("главный экран", () => {
  it("показывает заголовок, поле запроса и шаблоны", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    expect(screen.getByRole("heading",
      { name: "VK Slides — впечатляйте с первого слайда" })).toBeTruthy();
    expect(screen.getByPlaceholderText(/Опишите тему/)).toBeTruthy();
    // Имя выбранного шаблона видно дважды: в чипе у поля ввода и на карточке.
    await waitFor(() => expect(screen.getAllByText("Neon Lime").length)
      .toBeGreaterThanOrEqual(2));
    expect(screen.getByText("Pitchbook")).toBeTruthy();
  });

  it("не отправляет пустой запрос", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    const send = screen.getByRole("button", { name: "Собрать структуру" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
  });

  it("держит число слайдов в границах 3–30", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    const field = screen.getByLabelText("Сколько слайдов");
    fireEvent.change(field, { target: { value: "99" } });
    fireEvent.blur(field);
    await waitFor(() => expect((field as HTMLInputElement).value).toBe("30"));
  });
});

describe("структура", () => {
  const OUTLINE = {
    source: "heuristic",
    title: "Поток",
    warnings: [],
    slides: [
      { n: 1, intent: "cover", key_message: "Платформа «Поток»", notes: "" },
      { n: 2, intent: "metrics", key_message: "", notes: "" },
    ],
  };

  it("показывает пункты и переводит служебные названия", async () => {
    stubFetch((url) => {
      if (url.endsWith("/api/outline")) return ok(OUTLINE);
      return base(url) ?? ok({});
    });
    render(<App />);
    await askFor("Платформа для документов");

    await waitFor(() => expect(screen.getByText("Структура готова")).toBeTruthy(),
      { timeout: 4000 });
    expect(screen.getByText("Платформа «Поток»")).toBeTruthy();
    // Пустой key_message заменяется человеческим названием замысла, а не «metrics».
    await waitFor(() => expect(screen.getByText("Цифры")).toBeTruthy(), { timeout: 4000 });
    expect(screen.queryByText("metrics")).toBeNull();
  });

  it("сообщает, если структуру собрать не удалось", async () => {
    stubFetch((url) => {
      if (url.endsWith("/api/outline")) {
        return new Response(JSON.stringify({ detail: "нужен текст запроса" }), { status: 400 });
      }
      return base(url) ?? ok({});
    });
    render(<App />);
    await askFor("что-то");
    await waitFor(() => expect(screen.getByText("нужен текст запроса")).toBeTruthy());
  });
});

describe("панель", () => {
  it("прячется и возвращается", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Скрыть панель" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Показать панель" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Показать панель" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Показать панель" })).toBeNull());
  });

  it("не показывает раздел «Недавние», пока ничего не собрано", () => {
    localStorage.clear();
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    expect(screen.queryByText("Недавние")).toBeNull();
  });
});

describe("горячая клавиша", () => {
  it("Ctrl+K начинает новую презентацию с чистого листа", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    const field = screen.getByPlaceholderText(/Опишите тему/) as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: "черновик" } });
    expect(field.value).toBe("черновик");

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    await waitFor(() => expect(
      (screen.getByPlaceholderText(/Опишите тему/) as HTMLTextAreaElement).value,
    ).toBe(""));
  });
});

describe("шаблоны", () => {
  it("показывает обложки, отрисованные из наших шаблонов", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    await waitFor(() => {
      expect(document.querySelector('main img[src*="Neon-Lime"]')).toBeTruthy();
    });
  });

  it("современные колоды идут раньше заготовок PowerPoint", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    await waitFor(() => expect(document.querySelectorAll("main .grid > button").length).toBe(3));
    const titles = [...document.querySelectorAll("main .grid > button")]
      .map((node) => node.getAttribute("title"));
    expect(titles).toEqual(["Neon Lime", "Pitchbook", "Фирменный"]);
  });

  it("пустая вкладка «Свои» зовёт создать свой стиль", async () => {
    // Библиотека без единого загруженного шаблона.
    stubFetch((url) => {
      if (url.endsWith("/api/library")) {
        return ok({ templates: LIBRARY.templates.filter((t) => t.origin !== "user"),
                    pending: 0 });
      }
      return base(url) ?? ok({});
    });
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "Свои" })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "Свои" }));

    // Вместо сетки — иллюстрация, подпись и кнопка загрузки.
    expect(await screen.findByText(/уникальном стиле/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Создать сейчас" })).toBeTruthy();
    expect(document.querySelectorAll("main .grid > button").length).toBe(0);
  });

  it("вкладка «Свои» показывает только загруженные и карточку загрузки", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "Свои" })).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: "Свои" }));

    await waitFor(() => {
      const titles = [...document.querySelectorAll("main .grid > button")]
        .map((node) => node.getAttribute("title"));
      // Свой шаблон плюс безымянная карточка «Загрузить шаблон».
      expect(titles).toEqual(["Фирменный", null]);
    });
    expect(screen.getByText("Загрузить шаблон")).toBeTruthy();
    expect(screen.queryByTitle("Pitchbook")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "Все" }));
    await waitFor(() => expect(screen.getByTitle("Pitchbook")).toBeTruthy());
  });
});

describe("предпросмотр шаблона", () => {
  it("открывает модалку и даёт выбрать стиль", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);

    const overlay = await screen.findByLabelText("Предварительный просмотр: Pitchbook");
    fireEvent.click(overlay);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeTruthy();
    // Коллаж — просто картинки, не кнопки навигации.
    await waitFor(() =>
      expect(dialog.querySelectorAll(".grid img").length).toBeGreaterThanOrEqual(1));
    expect(dialog.querySelectorAll(".grid button").length).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: "Использовать стиль" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Выбор зафиксирован: бейдж на карточке и имя в чипе у поля ввода.
    const chosen = screen.getByTitle("Pitchbook");
    expect(chosen.textContent).toContain("Выбрано");
    await waitFor(() => expect(screen.getAllByText("Pitchbook").length)
      .toBeGreaterThanOrEqual(2));
  });

  it("«Продолжить просмотр» закрывает модалку, не трогая выбор", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);

    fireEvent.click(await screen.findByLabelText("Предварительный просмотр: Pitchbook"));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Продолжить просмотр" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Выбранным остался шаблон по умолчанию — первый, а не просмотренный.
    expect(screen.getByTitle("Neon Lime").textContent).toContain("Выбрано");
    expect(screen.getByTitle("Pitchbook").textContent).not.toContain("Выбрано");
  });

  it("закрывается по Esc", async () => {
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);
    fireEvent.click(await screen.findByLabelText("Предварительный просмотр: Neon Lime"));
    expect(await screen.findByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("недавние проекты", () => {
  const RECENT = [{ id: "d1", title: "Питч платформы" }];

  function seed() {
    localStorage.setItem("vk-slides-recent", JSON.stringify(RECENT));
  }

  it("клик по проекту открывает его презентацию", async () => {
    seed();
    stubFetch((url) => {
      if (url.endsWith("/api/decks/d1")) {
        return ok({ id: "d1", status: "ready", stage: "готово",
                    plan_source: "llm", download: "/api/decks/d1/file",
                    slides: [{ n: 1, intent: "cover", key_message: "Питч",
                               pattern: "", pattern_name: "", archetype: "cover",
                               why: "", used_slots: 1, total_slots: 1,
                               image: "/api/decks/d1/slide/1" }] });
      }
      return base(url) ?? ok({});
    });
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Питч платформы" }));
    // Открылся экран презентации: заголовок, слайд и кнопка скачивания.
    await waitFor(() => expect(screen.getByRole("button", { name: /Скачать/ })).toBeTruthy());
    await waitFor(() => expect(document.querySelector('img[src="/api/decks/d1/slide/1"]')).toBeTruthy());
  });

  it("корзина удаляет проект из списка и с сервера", async () => {
    seed();
    const deleted: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "DELETE") {
        deleted.push(url);
        return Promise.resolve(ok({ ok: true }));
      }
      return Promise.resolve(base(url) ?? ok({}));
    }));
    render(<App />);

    fireEvent.click(await screen.findByLabelText("Удалить «Питч платформы»"));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Питч платформы" })).toBeNull());
    expect(deleted).toEqual(["/api/decks/d1"]);
    expect(JSON.parse(localStorage.getItem("vk-slides-recent") ?? "[]")).toEqual([]);
  });

  it("записи старого формата подставляют тему в запрос", async () => {
    localStorage.setItem("vk-slides-recent", JSON.stringify(["Просто тема"]));
    stubFetch((url) => base(url) ?? ok({}));
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Просто тема" }));
    await waitFor(() => expect(
      (screen.getByPlaceholderText(/Опишите тему/) as HTMLTextAreaElement).value,
    ).toBe("Просто тема"));
  });
});
