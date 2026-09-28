/** Клиент к сервису. Типы повторяют то, что отдаёт FastAPI. */

export type Status = "queued" | "running" | "ready" | "failed";

export interface Slot {
  role: string;
  bbox: number[];
  style: string;
  size_pt: number | null;
  capacity: { chars: number; lines: number };
}

export interface Pattern {
  id: string;
  archetype: string;
  name: string;
  mode: string;
  confidence: number;
  evidence: string[];
  slots: Slot[];
  repeat: number | null;
  preview: string | null;
}

export interface TemplateJob {
  id: string;
  status: Status;
  stage: string;
  error?: string;
  file?: string;
  source?: { file: string; slide_size: { ratio: string }; layouts: number; example_slides: number };
  palette?: {
    theme: Record<string, string>;
    roles: Record<string, string>;
    role_provenance: Record<string, string>;
    accent_seq: string[];
    is_dark: boolean;
  };
  typography?: {
    fonts: { major: string; minor: string; embedded: string[] };
    scale_pt: number[];
    styles: Record<string, { font: string; size_pt: number; color: string }>;
  };
  geometry?: {
    margins: Record<string, number>;
    columns: { count: number; gutter: number };
    safe_area: number[];
  };
  warnings?: string[];
  patterns?: Pattern[];
}

export interface DeckSlide {
  n: number;
  intent: string;
  key_message: string;
  pattern: string;
  pattern_name: string;
  archetype: string;
  why: string;
  used_slots: number;
  total_slots: number;
  image: string | null;
}

export interface LibraryTemplate {
  id: string;
  label: string;
  kind: "html" | "pptx";
  cover?: string;
  origin?: "library" | "user";
}

export interface OutlineSlide {
  n: number;
  intent: string;
  key_message: string;
  notes: string;
}

export interface Outline {
  source: string;
  title: string;
  slides: OutlineSlide[];
  warnings: string[];
}

/** Находка аудита по чек-листу: где, что и можно ли починить пересборкой. */
export interface DeckDefect {
  id: string;
  kind: string;
  check: string;
  group: string;
  nature: "deterministic" | "contextual";
  severity: "error" | "warning" | "info";
  slide: number;
  message: string;
  fixable: boolean;
  fix: string;
}

/** Один из трёх вариантов вёрстки: тот же шаблон и контент, другая плотность. */
export interface DeckVariant {
  id: "compact" | "balanced" | "spacious";
  label: string;
  tagline: string;
  slides: DeckSlide[];
  metrics?: Record<string, number>;
  defects?: DeckDefect[];
  checks?: string[];
  skipped_checks?: Record<string, string>;
  repaired?: number[];
  notes?: string[];
  download: string | null;
  pdf?: string | null;
  /** Страница варианта: ссылка «Поделиться». */
  html?: string | null;
}

export interface DeckJob {
  id: string;
  status: Status;
  stage: string;
  error?: string;
  template?: string;
  plan_source?: string;
  variant?: string;
  variants?: DeckVariant[];
  /** Файлы части вариантов ещё готовятся — опрос продолжается. */
  exporting?: boolean;
  slides?: DeckSlide[];
  metrics?: Record<string, number>;
  defects?: DeckDefect[];
  notes?: string[];
  mode_counts?: Record<string, number>;
  download?: string | null;
  pdf?: string | null;
  html?: string | null;
}

/** Причина отказа человеческим языком: FastAPI кладёт её в поле `detail`. */
export async function errorMessage(response: Response): Promise<string> {
  const body = await response.text();
  try {
    const parsed = JSON.parse(body);
    const detail = parsed?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) return detail.map((d) => d.msg ?? "").join("; ");
  } catch {
    /* не JSON — покажем как есть */
  }
  return body.slice(0, 300) || `ошибка ${response.status}`;
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json() as Promise<T>;
}

export const api = {
  status: () => fetch("/api/status").then(json<{ llm: string; renderers: string[] }>),

  uploadTemplate(file: File) {
    const body = new FormData();
    body.append("file", file);
    return fetch("/api/templates", { method: "POST", body }).then(json<{ id: string }>);
  },

  template: (id: string) => fetch(`/api/templates/${id}`).then(json<TemplateJob>),

  buildDeck(templateId: string, files: File[], brief: string, slides: string, useLlm: boolean) {
    const body = new FormData();
    body.append("template_id", templateId);
    body.append("brief", brief);
    body.append("slides", slides);
    body.append("use_llm", String(useLlm));
    files.forEach((file) => body.append("files", file));
    return fetch("/api/decks", { method: "POST", body }).then(json<{ id: string }>);
  },

  deck: (id: string) => fetch(`/api/decks/${id}`).then(json<DeckJob>),

  /** Починить выбранные находки аудита: их слайды пересобираются ужатым бюджетом. */
  repairDeck(id: string, variant: string, defectIds: string[]) {
    const body = new FormData();
    body.append("variant", variant);
    body.append("defects", defectIds.join(","));
    return fetch(`/api/decks/${id}/repair`, { method: "POST", body })
      .then(json<{ id: string; status: string; slides: number[] }>);
  },

  /** Удаляет проект целиком: колоду, снимки, pdf и запись на сервере. */
  deleteDeck: (id: string) =>
    fetch(`/api/decks/${id}`, { method: "DELETE" }).then(json<{ ok: boolean }>),

  demoAssets: () => fetch("/api/demo").then(json<{ templates: string[]; content: string[] }>),

  /** Библиотека шаблонов с обложками: сервер рисует их из самих шаблонов. */
  library: () => fetch("/api/library")
    .then(json<{ templates: LibraryTemplate[]; pending: number }>),

  /** Свой шаблон: файл уходит в библиотеку и появляется во вкладке «Свои». */
  uploadLibraryTemplate(file: File) {
    const body = new FormData();
    body.append("file", file);
    return fetch("/api/library/upload", { method: "POST", body })
      .then(json<LibraryTemplate>);
  },

  /** Первые слайды шаблона для предпросмотра. Готовятся лениво. */
  preview: (id: string) => fetch(`/api/library/preview?id=${encodeURIComponent(id)}`)
    .then(json<{ images: string[]; pending: number }>),

  /** Сборка в HTML-шаблоне: колода, снимки слайдов, pptx и pdf. */
  buildHtml(templateId: string, text: string, slides: number, useLlm: boolean) {
    const body = new FormData();
    body.append("template_id", templateId);
    body.append("text", text);
    body.append("slides", String(slides));
    body.append("use_llm", String(useLlm));
    return fetch("/api/decks/html", { method: "POST", body }).then(json<{ id: string }>);
  },

  demoTemplate(name: string) {
    const body = new FormData();
    body.append("name", name);
    return fetch("/api/demo/template", { method: "POST", body }).then(json<{ id: string }>);
  },

  /** Структура будущей презентации по тексту запроса — до сборки слайдов. */
  outline(text: string, slides: number, useLlm: boolean) {
    const body = new FormData();
    body.append("text", text);
    body.append("slides", String(slides));
    body.append("use_llm", String(useLlm));
    return fetch("/api/outline", { method: "POST", body }).then(json<Outline>);
  },

  /** Сборка по тексту: запрос уходит на сервер файлом, как обычный контент. */
  buildFromText(templateId: string, text: string, slides: number, useLlm: boolean,
                extra?: File | null) {
    const body = new FormData();
    body.append("template_id", templateId);
    body.append("brief", "");
    body.append("slides", String(slides));
    body.append("use_llm", String(useLlm));
    body.append("files", new File([text], "запрос.md", { type: "text/markdown" }));
    if (extra) body.append("files", extra);
    return fetch("/api/decks", { method: "POST", body }).then(json<{ id: string }>);
  },

  demoDeck(templateId: string, name: string, brief: string, slides: string, useLlm: boolean) {
    const body = new FormData();
    body.append("template_id", templateId);
    body.append("name", name);
    body.append("brief", brief);
    body.append("slides", slides);
    body.append("use_llm", String(useLlm));
    return fetch("/api/demo/deck", { method: "POST", body }).then(json<{ id: string }>);
  },
};

/** Опрос состояния фоновой задачи.
 *
 * Одна неудачная попытка — это моргнувшая сеть, и молчать о ней правильно.
 * Но если сервер не отвечает подряд, интерфейс не должен крутить «идёт сборка»
 * бесконечно: после `giveUpAfter` попыток зовём `onError`.
 */
function exportsPending(value: { status: Status }): boolean {
  return Boolean((value as { exporting?: boolean }).exporting);
}

export function poll<T extends { status: Status }>(
  load: () => Promise<T>,
  onUpdate: (value: T) => void,
  interval = 1200,
  onError?: (message: string) => void,
  giveUpAfter = 3,
): () => void {
  let stopped = false;
  let failures = 0;
  const tick = async () => {
    if (stopped) return;
    try {
      const value = await load();
      failures = 0;
      onUpdate(value);
      if (value.status === "failed") return;
      // Готовая колода может ещё доэкспортировать варианты вёрстки: файлы
      // сбалансированного есть сразу, остальных — чуть позже. Пока у какого-то
      // варианта нет ссылки на скачивание, продолжаем спрашивать.
      if (value.status === "ready" && !exportsPending(value)) return;
    } catch (error) {
      failures += 1;
      if (failures >= giveUpAfter) {
        onError?.(error instanceof Error ? error.message : "сервис не отвечает");
        return;
      }
    }
    setTimeout(tick, interval);
  };
  void tick();
  return () => {
    stopped = true;
  };
}
