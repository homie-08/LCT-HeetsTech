/** VK Slides — генератор презентаций.
 *
 * Три экрана и одно состояние на всё приложение: запрос → структура → колода.
 * Структура показывается до сборки не для красоты: сборка занимает минуты, и
 * ошибку в замысле дешевле поймать на восьми строчках, чем на готовом файле.
 */

import { useEffect, useRef, useState } from "react";
import { api, poll, type DeckJob, type LibraryTemplate, type TemplateJob } from "./api";
import { Sidebar, type RecentDeck } from "./Sidebar";
import { Deck } from "./screens/Deck";
import { Home } from "./screens/Home";
import { Outline, type OutlineItem } from "./screens/Outline";
import { TemplatePreview } from "./screens/TemplatePreview";
import { PanelLeft, Toast } from "./ui";

type Screen = "home" | "outline" | "deck";

// Недавние — это то, что пользователь действительно собрал на этой машине.
// Придуманного списка здесь нет: пустой раздел честнее выдуманного.
const RECENT_KEY = "vk-slides-recent";
const RECENT_LIMIT = 8;

function loadRecent(): RecentDeck[] {
  try {
    const stored = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    if (!Array.isArray(stored)) return [];
    // Записи старого формата — просто строки: у них нет привязки к колоде,
    // клик по ним подставляет тему в запрос, как раньше.
    return stored
      .map((item) => (typeof item === "string" ? { id: "", title: item } : item))
      .filter((item): item is RecentDeck =>
        !!item && typeof item.title === "string" && typeof item.id === "string");
  } catch {
    return [];
  }
}

/** Комбинация «новая презентация»: Ctrl+K, на макбуке ⌘+K. */
function isNewDeckHotkey(event: KeyboardEvent): boolean {
  return (event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k";
}

/** Короткое имя презентации из запроса: первая осмысленная строка без разметки. */
function titleOf(prompt: string): string {
  const line = prompt.split(/\r?\n/)
    .map((item) => item.replace(/^#+\s*/, "").trim())
    .find((item) => item.length > 0) ?? "";
  return line.replace(/[*_`]/g, "").slice(0, 60);
}

/** Замысел слайда по-русски: служебным названиям архетипов в интерфейсе не место. */
const INTENT: Record<string, [string, string]> = {
  cover: ["Титул", "Тема, дата и спикер"],
  agenda: ["Содержание", "О чём пойдёт речь"],
  section: ["Раздел", "Переход к новой теме"],
  bullets: ["Тезисы", "Ключевые утверждения"],
  two_column: ["Две колонки", "Сопоставление"],
  comparison: ["Сравнение", "Было и стало"],
  metrics: ["Цифры", "Измеримый результат"],
  process: ["Этапы", "Как это работает"],
  table: ["Таблица", "Сводные данные"],
  chart: ["График", "Динамика показателей"],
  quote: ["Цитата", "Слова заказчика"],
  image_text: ["Иллюстрация", "Картинка с пояснением"],
  image_full: ["Изображение", "Кадр во весь слайд"],
  gallery: ["Галерея", "Несколько изображений"],
  team: ["Команда", "Кто делает проект"],
  contacts: ["Контакты", "Как связаться"],
  blank: ["Свободный слайд", ""],
};

function describe(intent: string, keyMessage: string, notes: string) {
  const [label, hint] = INTENT[intent] ?? [intent, ""];
  return { title: keyMessage.trim() || label, note: notes.trim() || hint };
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [sideOpen, setSideOpen] = useState(true);
  const [toast, setToast] = useState("");

  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [count, setCount] = useState(8);
  const [templates, setTemplates] = useState<LibraryTemplate[]>([]);
  const [template, setTemplate] = useState(0);
  const [recent, setRecent] = useState<RecentDeck[]>(loadRecent);
  const [preview, setPreview] = useState<number | null>(null);
  const [previewShots, setPreviewShots] = useState<{ images: string[]; pending: number }>(
    { images: [], pending: 0 });
  const [useLlm, setUseLlm] = useState(true);

  const [items, setItems] = useState<OutlineItem[]>([]);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState("");

  const [deck, setDeck] = useState<DeckJob>();
  const [current, setCurrent] = useState(0);
  const [busy, setBusy] = useState(false);
  const stopPolling = useRef<() => void>();

  useEffect(() => () => stopPolling.current?.(), []);

  // Обложки сервер рисует из самих шаблонов, и на первый раз это небыстро:
  // спрашиваем список заново, пока не отрисуются все.
  useEffect(() => {
    let stopped = false;
    const ask = async () => {
      try {
        const data = await api.library();
        if (stopped) return;
        setTemplates(data.templates);
        if (data.pending > 0) window.setTimeout(ask, 4000);
      } catch {
        /* без библиотеки сетка пуста — это видно и без сообщения */
      }
    };
    void ask();
    return () => {
      stopped = true;
    };
  }, []);

  useEffect(() => {
    if (preview === null) return;
    const chosen = templates[preview];
    if (!chosen) return;
    let stopped = false;
    setPreviewShots({ images: [], pending: 1 });

    const ask = async () => {
      try {
        const data = await api.preview(chosen.id);
        if (stopped) return;
        setPreviewShots(data);
        if (data.pending > 0) window.setTimeout(ask, 2500);
      } catch {
        if (!stopped) setPreviewShots({ images: [], pending: 0 });
      }
    };
    void ask();
    return () => {
      stopped = true;
    };
  }, [preview, templates]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!isNewDeckHotkey(event)) return;
      event.preventDefault();
      reset();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function show(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 1800);
  }

  async function onSubmit() {
    setError("");
    setItems([]);
    setPlanning(true);
    setScreen("outline");
    try {
      const outline = await api.outline(prompt, count, useLlm);
      setItems(outline.slides.map((slide) => ({
        n: slide.n,
        ...describe(slide.intent, slide.key_message, slide.notes),
      })));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPlanning(false);
    }
  }

  /** Собирает колоду. Путь зависит от шаблона: колода HTML верстается своим
   *  конвейером, заготовка PowerPoint — разбором мастеров и макетов. */
  async function onBuild() {
    const chosen = templates[template];
    if (!chosen) {
      setError("шаблоны недоступны");
      return;
    }
    setBusy(true);
    setError("");
    setDeck(undefined);
    setCurrent(0);
    setScreen("deck");
    try {
      let jobId: string;
      if (chosen.kind === "html") {
        jobId = (await api.buildHtml(chosen.id, prompt, count, useLlm)).id;
      } else {
        const { id } = await api.demoTemplate(chosen.id.replace(/^pptx:/, ""));
        const ready = await waitFor(() => api.template(id));
        if (ready.status !== "ready") throw new Error(ready.error || "шаблон не разобран");
        jobId = (await api.buildFromText(id, prompt, count, useLlm, file)).id;
      }
      remember(jobId, titleOf(prompt));
      stopPolling.current?.();
      stopPolling.current = poll(() => api.deck(jobId), setDeck, 1200,
                                 (text) => setError(`сервис не отвечает: ${text}`));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      setScreen("outline");
    } finally {
      setBusy(false);
    }
  }

  /** Загружает свой шаблон и сразу выбирает его. */
  async function onUploadTemplate(chosen: File) {
    try {
      const uploaded = await api.uploadLibraryTemplate(chosen);
      const fresh = await api.library();
      setTemplates(fresh.templates);
      const index = fresh.templates.findIndex((item) => item.id === uploaded.id);
      if (index >= 0) setTemplate(index);
      show(`Шаблон «${uploaded.label}» добавлен`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  function persistRecent(next: RecentDeck[]) {
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    } catch {
      /* приватный режим — список проживёт до перезагрузки */
    }
    return next;
  }

  /** Запоминает собранную презентацию: тема плюс идентификатор колоды. */
  function remember(id: string, title: string) {
    const trimmed = title.trim().slice(0, 80);
    if (!trimmed) return;
    setRecent((previous) => persistRecent(
      [{ id, title: trimmed },
       ...previous.filter((item) => item.id !== id && item.title !== trimmed)]
        .slice(0, RECENT_LIMIT)));
  }

  /** Открывает сохранённый проект — сразу экраном презентации. */
  function openRecent(item: RecentDeck) {
    if (!item.id) {
      setPrompt(item.title);
      setScreen("home");
      return;
    }
    setPrompt(item.title);
    setError("");
    setDeck(undefined);
    setCurrent(0);
    setScreen("deck");
    stopPolling.current?.();
    stopPolling.current = poll(() => api.deck(item.id), setDeck, 1200, () => {
      setError("презентация не найдена — возможно, проект удалён");
    });
  }

  /** Удаляет проект: из списка сразу, с сервера — следом. */
  function deleteRecent(item: RecentDeck) {
    setRecent((previous) => persistRecent(
      previous.filter((entry) => entry !== item)));
    if (item.id) void api.deleteDeck(item.id).catch(() => undefined);
    show(`Проект «${item.title}» удалён`);
  }

  /** Новая презентация: чистый лист. Шаблон и число слайдов остаются — их
   *  выбирают один раз под свою задачу, а не под каждый запрос. */
  function reset() {
    stopPolling.current?.();
    setScreen("home");
    setDeck(undefined);
    setItems([]);
    setError("");
    setPrompt("");
    setFile(null);
  }

  return (
    <div className="flex h-screen overflow-hidden bg-page">
      <Sidebar
        open={sideOpen}
        recent={recent}
        onToggle={() => setSideOpen(false)}
        onNew={reset}
        llmOn={useLlm}
        onToggleLlm={() => {
          setUseLlm((value) => {
            show(value ? "Модель выключена — работаю на эвристиках"
                       : "Модель включена");
            return !value;
          });
        }}
        onOpenRecent={openRecent}
        onDeleteRecent={deleteRecent}
      />

      {!sideOpen && (
        <button
          type="button"
          aria-label="Показать панель"
          onClick={() => setSideOpen(true)}
          className="fixed left-[13px] top-[13px] z-40 flex h-8 w-8 items-center justify-center
                     rounded-[10px] bg-[#14161B] text-ink-muted transition-colors
                     hover:text-vk-light"
        >
          <PanelLeft size={16} />
        </button>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        {screen === "home" && (
          <Home
            prompt={prompt}
            file={file}
            count={count}
            templates={templates.map((item) => ({
              name: item.id,
              label: item.label,
              cover: item.cover,
              origin: item.origin,
            }))}
            template={template}
            busy={planning}
            scrollLocked={preview !== null}
            onPrompt={setPrompt}
            onFile={setFile}
            onCount={setCount}
            onTemplate={setTemplate}
            onPreview={setPreview}
            onUpload={onUploadTemplate}
            onSubmit={onSubmit}
          />
        )}

        {screen === "outline" && (
          <Outline
            prompt={prompt}
            fileName={file?.name ?? null}
            items={items}
            loading={planning}
            error={error}
            templateName={templates[template]?.label ?? ""}
            busy={busy}
            onBack={() => setScreen("home")}
            onBuild={onBuild}
          />
        )}

        {screen === "deck" && (
          <Deck
            title={prompt}
            deck={deck}
            current={current}
            onCurrent={setCurrent}
            onBack={reset}
            onShare={async (page) => {
              if (!deck?.id || !page) return;
              const link = `${window.location.origin}${page}`;
              try {
                await navigator.clipboard.writeText(link);
                show("Ссылка скопирована");
              } catch {
                // Буфер обмена доступен не везде — показываем ссылку целиком,
                // чтобы обещание не оказалось пустым.
                show(link);
              }
            }}
            onDownloadPdf={(url) => {
              show("Готовлю файл .pdf…");
              window.location.href = url;
            }}
            onDownload={(url) => {
              show("Готовлю файл .pptx…");
              window.location.href = url;
            }}
            onRepair={async (variant, ids) => {
              if (!deck?.id) return;
              try {
                const started = await api.repairDeck(deck.id, variant, ids);
                show(`Пересобираю слайды ${started.slides.join(", ")}…`);
                stopPolling.current?.();
                stopPolling.current = poll(() => api.deck(deck.id), setDeck, 1200,
                                           (message) => setError(message));
              } catch (failure) {
                setError(failure instanceof Error ? failure.message : "ремонт не удался");
              }
            }}
          />
        )}

        {error && screen !== "outline" && (
          <div className="border-t border-edge-panel bg-panel px-4 py-2 text-[13px] text-[#FF6B6B]">
            {error}
          </div>
        )}
      </main>

      {preview !== null && templates[preview] && (
        <TemplatePreview
          label={templates[preview].label}
          images={previewShots.images}
          pending={previewShots.pending}
          onClose={() => setPreview(null)}
          onUse={() => {
            setTemplate(preview);
            setPreview(null);
            show(`Стиль «${templates[preview].label}» выбран`);
          }}
        />
      )}

      <Toast text={toast} />
    </div>
  );
}

/** Ждёт готовности фоновой задачи, опрашивая её состояние. */
function waitFor(load: () => Promise<TemplateJob>, tries = 120): Promise<TemplateJob> {
  return new Promise((resolve, reject) => {
    let left = tries;
    const tick = async () => {
      try {
        const value = await load();
        if (value.status === "ready" || value.status === "failed") return resolve(value);
        if (--left <= 0) return reject(new Error("шаблон разбирается слишком долго"));
        window.setTimeout(tick, 1000);
      } catch (failure) {
        reject(failure);
      }
    };
    void tick();
  });
}
