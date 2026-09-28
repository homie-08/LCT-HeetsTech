/** Главный экран: запрос, параметры и выбор шаблона. */

import { useRef, useState } from "react";
import { TemplateCover } from "../covers";
import { ArrowUp, Check, ChevronDown, Eye, FileIcon, Paperclip, Plus, X } from "../ui";

export function plural(count: number, forms: [string, string, string]): string {
  const tens = count % 100;
  const ones = count % 10;
  if (tens > 10 && tens < 20) return forms[2];
  if (ones === 1) return forms[0];
  if (ones >= 2 && ones <= 4) return forms[1];
  return forms[2];
}

export interface TemplateCard {
  name: string;
  label: string;
  /** Обложка, отрисованная сервером из самого шаблона. */
  cover?: string;
  /** Откуда шаблон: из библиотеки или загружен пользователем. */
  origin?: "library" | "user";
}

export interface HomeProps {
  prompt: string;
  file: File | null;
  count: number;
  templates: TemplateCard[];
  template: number;
  busy: boolean;
  /** Пока открыта модалка, лента под ней стоит на месте. */
  scrollLocked?: boolean;
  onPrompt: (value: string) => void;
  onFile: (file: File | null) => void;
  onCount: (value: number) => void;
  onTemplate: (index: number) => void;
  onPreview: (index: number) => void;
  onUpload: (file: File) => void;
  onSubmit: () => void;
}

/** Пустая вкладка «Свои»: иллюстрация, подпись и кнопка загрузки.

    Рисунок повторяет референс: карточки с картинкой и текстом «слетаются»
    стрелками в холст с плюсом. Всё инлайн-SVG в приглушённых тонах темы —
    картинка не должна кричать громче настоящих обложек. */
function EmptyOwn({ onCreate }: { onCreate: () => void }) {
  const card = "#1E2127";
  const line = "#3A3F49";
  const stroke = "#4A505C";
  return (
    <div className="mt-10 flex flex-col items-center gap-6 py-8 text-center">
      <svg width="260" height="140" viewBox="0 0 260 140" fill="none" aria-hidden="true">
        {/* Холст с плюсом, в который собирается стиль. */}
        <rect x="78" y="26" width="104" height="88" rx="8" fill="rgba(255,255,255,0.10)" />
        <path d="M130 62v16M122 70h16" stroke="rgba(255,255,255,0.35)" strokeWidth="2"
              strokeLinecap="round" />
        {/* Карточка с фотографией, наклонена. */}
        <g transform="rotate(-8 47 52)">
          <rect x="12" y="30" width="70" height="44" rx="6" fill={card} />
          <circle cx="60" cy="42" r="5" fill={line} />
          <path d="M20 66l14-14 10 9 8-7 12 12H20z" fill={line} />
        </g>
        {/* Карточка с текстом. */}
        <rect x="24" y="86" width="64" height="34" rx="6" fill={card} />
        <rect x="31" y="94" width="42" height="4" rx="2" fill={line} />
        <rect x="31" y="103" width="50" height="4" rx="2" fill={line} />
        <rect x="31" y="112" width="30" height="4" rx="2" fill={line} />
        {/* Карточка-раскладка справа. */}
        <rect x="162" y="10" width="86" height="52" rx="6" fill={card} />
        <rect x="169" y="18" width="34" height="10" rx="2" fill={line} />
        <rect x="169" y="32" width="34" height="22" rx="2" fill={line} />
        <rect x="209" y="18" width="32" height="10" rx="2" fill={line} />
        <rect x="209" y="32" width="32" height="10" rx="2" fill={line} />
        <rect x="209" y="46" width="32" height="8" rx="2" fill={line} />
        {/* Стрелки: из карточек — в холст, из холста — к раскладке. */}
        <path d="M62 18c28-14 52-6 60 12" stroke={stroke} strokeWidth="1.6"
              strokeLinecap="round" fill="none" />
        <path d="m118 22 5 9-11-1" fill={stroke} />
        <path d="M196 116c14-8 20-22 18-40" stroke={stroke} strokeWidth="1.6"
              strokeLinecap="round" fill="none" />
        <path d="m212 86 3-10 6 9" fill={stroke} />
      </svg>

      <p className="max-w-[420px] text-[14px] leading-relaxed text-ink-muted">
        Загрузите свой шаблон — и презентации соберутся в вашем уникальном стиле
      </p>

      <button
        type="button"
        onClick={onCreate}
        className="h-[36px] rounded-pill bg-[#F2F4F8] px-5 text-[13.5px] font-medium
                   text-[#16181C] transition-opacity duration-150 hover:opacity-90"
      >
        Создать сейчас
      </button>
      <span className="-mt-4 text-[12px] text-ink-label">.pptx, .potx или .dc.html</span>
    </div>
  );
}

export function Home(props: HomeProps) {
  const { prompt, file, count, templates, template, busy } = props;
  const picker = useRef<HTMLInputElement>(null);
  const templatePicker = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<"all" | "mine">("all");
  const ready = prompt.trim().length > 0 && !busy;
  const templateName = templates[template]?.label ?? "";

  // Индексы сохраняются от полного списка: выбор и предпросмотр адресуют
  // шаблон в нём, независимо от того, какая вкладка открыта.
  const visible = templates
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => tab === "all" || item.origin === "user");

  return (
    <div className={`relative flex-1 ${props.scrollLocked ? "overflow-hidden" : "overflow-y-auto"}`}>
      {/* Декоративное свечение: пульсирует, но ничего не перехватывает. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 animate-glowPulse"
        style={{
          background:
            "radial-gradient(1100px 560px at 50% -140px, rgba(0,92,255,0.30), rgba(0,92,255,0.05) 55%, transparent 75%)",
        }}
      />

      <div className="relative mx-auto flex w-full max-w-[680px] flex-col gap-7 px-6 pb-16 pt-[72px]">
        {/* Начертание — по брендовому референсу VK: широкая геометрия
            Unbounded, лёгкий штрих, по центру, ровный перенос строк. */}
        <h1 className="display title-glow text-balance text-center text-[34px]
                       font-light leading-[1.25] text-ink-primary">
          VK Slides — впечатляйте с первого слайда
        </h1>

        {/* Карточка закреплена: при прокрутке списка шаблонов она прилипает к
            верху экрана и остаётся под рукой, а сетка уезжает под неё. Фон у
            карточки почти непрозрачный, размытие прячет проезжающие обложки. */}
        <div className="sticky top-3 z-20 rounded-card border border-edge-panel bg-card p-4
                        shadow-input backdrop-blur-md">
          <textarea
            rows={3}
            value={prompt}
            onChange={(event) => props.onPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (ready) props.onSubmit();
              }
            }}
            placeholder="Опишите тему — подготовлю структуру и слайды…"
            className="w-full resize-none border-0 bg-transparent text-[15px] leading-[1.55]
                       text-ink-primary outline-none placeholder:text-ink-weak"
          />

          {file && (
            <div
              className="mb-3 inline-flex items-center gap-2 rounded-pill border px-3 py-1.5
                         text-[12.5px]"
              style={{
                background: "rgba(0,119,255,0.12)",
                borderColor: "rgba(0,119,255,0.32)",
                color: "#C9DFFF",
              }}
            >
              <FileIcon size={13} className="text-vk-light" />
              {file.name}
              <button
                type="button"
                aria-label="Убрать файл"
                onClick={() => props.onFile(null)}
                className="text-vk-light transition-opacity hover:opacity-70"
              >
                <X size={12} />
              </button>
            </div>
          )}

          <div className="flex items-center gap-2">
            <input
              ref={picker}
              type="file"
              accept=".md,.txt,.docx,.pdf,.xlsx,.csv"
              className="hidden"
              onChange={(event) => props.onFile(event.target.files?.[0] ?? null)}
            />
            <button
              type="button"
              aria-label="Прикрепить файл"
              onClick={() => picker.current?.click()}
              className="icon-button h-[34px] w-[34px]"
            >
              <Paperclip size={15} />
            </button>

            <label className="pill cursor-text">
              <input
                value={count}
                inputMode="numeric"
                maxLength={2}
                onChange={(event) => {
                  const digits = event.target.value.replace(/\D/g, "").slice(0, 2);
                  props.onCount(digits === "" ? 0 : Number(digits));
                }}
                onBlur={() => props.onCount(Math.min(30, Math.max(3, count || 8)))}
                className="w-[2ch] border-0 bg-transparent p-0 text-center text-[13px]
                           font-semibold text-vk-light outline-none"
                aria-label="Сколько слайдов"
              />
              {plural(count, ["слайд", "слайда", "слайдов"])}
            </label>

            <button
              type="button"
              onClick={() => props.onTemplate((template + 1) % Math.max(1, templates.length))}
              className="pill max-w-[240px]"
              disabled={templates.length === 0}
            >
              <span className="truncate">{templateName || "шаблон"}</span>
              <ChevronDown size={13} />
            </button>

            <button
              type="button"
              aria-label="Собрать структуру"
              disabled={!ready}
              onClick={props.onSubmit}
              className={`ml-auto flex h-9 w-9 items-center justify-center rounded-pill
                          transition-colors duration-150 ${
                            ready
                              ? "bg-vk text-white hover:bg-vk-hover"
                              : "cursor-not-allowed bg-white/[0.08] text-ink-label"
                          }`}
            >
              <ArrowUp size={16} />
            </button>
          </div>
        </div>

        <div>
          {/* Вкладки: вся библиотека и загруженные пользователем шаблоны. */}
          <div className="flex items-center gap-2" role="tablist" aria-label="Шаблоны">
            {([["all", "Все"], ["mine", "Свои"]] as const).map(([key, title]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={`h-[34px] rounded-pill px-4 text-[13.5px] font-medium
                            transition-colors duration-150 ${
                              tab === key
                                ? "bg-white/[0.10] text-ink-primary"
                                : "text-ink-muted hover:text-ink-secondary"
                            }`}
              >
                {title}
              </button>
            ))}
          </div>

          <input
            ref={templatePicker}
            type="file"
            accept=".pptx,.potx,.html"
            className="hidden"
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              if (chosen) props.onUpload(chosen);
              event.target.value = "";
            }}
          />

          {tab === "mine" && visible.length === 0 ? (
            <EmptyOwn onCreate={() => templatePicker.current?.click()} />
          ) : (
          <div className="mt-4 grid grid-cols-3 gap-x-4 gap-y-[18px]">
            {visible.map(({ item, index }) => {
              const active = index === template;
              return (
                <button
                  key={item.name}
                  type="button"
                  onClick={() => props.onTemplate(index)}
                  className="group text-left"
                  title={item.label}
                >
                  <span
                    className="relative block overflow-hidden rounded-[10px] p-[2px]
                               transition-colors duration-150"
                    style={{
                      border: active
                        ? "2px solid #0077FF"
                        : "2px solid rgba(255,255,255,0.10)",
                    }}
                  >
                    {item.cover ? (
                      <img
                        src={item.cover}
                        alt=""
                        loading="lazy"
                        className="block aspect-[16/9] w-full rounded-[10px] object-cover"
                      />
                    ) : (
                      // Пока сервер рисует обложку, показываем набросок в
                      // стиле подборки — не пустую дыру в сетке.
                      <TemplateCover index={index} />
                    )}

                    {/* Выбранный стиль помечен всегда; при наведении бейдж
                        уступает место кнопке просмотра. */}
                    {active && (
                      <span
                        className="absolute inset-0 flex items-center justify-center
                                   transition-opacity duration-150 group-hover:opacity-0"
                      >
                        <span className="flex items-center gap-2 whitespace-nowrap
                                         rounded-pill bg-black/70 px-3.5 py-2 text-[12px]
                                         font-medium text-white">
                          <Check size={14} />
                          Выбрано
                        </span>
                      </span>
                    )}

                    {/* Просмотр — отдельное действие поверх карточки: клик по
                        самой карточке выбирает шаблон, и путать их нельзя. */}
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={`Предварительный просмотр: ${item.label}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onPreview(index);
                      }}
                      onKeyDown={(event) => {
                        if (event.key !== "Enter" && event.key !== " ") return;
                        event.preventDefault();
                        event.stopPropagation();
                        props.onPreview(index);
                      }}
                      className="absolute inset-0 flex cursor-pointer items-center
                                 justify-center bg-black/35 opacity-0 transition-opacity
                                 duration-150 focus-visible:opacity-100
                                 group-hover:opacity-100"
                    >
                      <span className="flex items-center gap-2 whitespace-nowrap
                                       rounded-pill bg-black/70 px-3.5 py-2 text-[12px]
                                       font-medium text-white">
                        <Eye size={14} />
                        Предварительный просмотр
                      </span>
                    </span>
                  </span>
                  <span
                    className={`mt-2 block truncate text-[13px] font-medium ${
                      active ? "text-ink-primary" : "text-ink-muted"
                    }`}
                  >
                    {item.label}
                  </span>
                </button>
              );
            })}

            {/* Свой шаблон добавляется здесь же — карточкой в сетке. */}
            {tab === "mine" && (
              <button
                type="button"
                onClick={() => templatePicker.current?.click()}
                className="text-left"
              >
                <span
                  className="flex aspect-[16/9] w-full flex-col items-center justify-center
                             gap-2 rounded-[10px] border-2 border-dashed border-edge-control
                             text-ink-muted transition-colors duration-150
                             hover:border-edge-hover hover:text-vk-light"
                >
                  <Plus size={18} />
                  <span className="text-[12.5px] font-medium">Загрузить шаблон</span>
                </span>
                <span className="mt-2 block text-[12px] text-ink-label">
                  .pptx, .potx или .dc.html
                </span>
              </button>
            )}
          </div>
          )}
        </div>
      </div>
    </div>
  );
}
