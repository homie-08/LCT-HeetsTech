/** Экран просмотра готовой колоды: рейка миниатюр, полотно, экспорт. */

import { useEffect, useState } from "react";

import type { DeckJob, DeckSlide, DeckVariant } from "../api";
import { ArrowLeft, ChevronLeft, ChevronRight, Download, Share, Spinner } from "../ui";
import { Audit } from "./Audit";

export interface DeckProps {
  title: string;
  deck: DeckJob | undefined;
  current: number;
  onCurrent: (index: number) => void;
  onBack: () => void;
  /** Скачать .pptx; ссылка зависит от выбранного варианта вёрстки. */
  onDownload: (url: string) => void;
  onDownloadPdf: (url: string) => void;
  onShare: (url: string | null) => void;
  /** Починить выбранные находки аудита в текущем варианте. */
  onRepair?: (variant: string, defectIds: string[]) => void;
}

export function Deck({ title, deck, current, onCurrent, ...props }: DeckProps) {
  const variants = deck?.variants ?? [];
  const [variantId, setVariantId] = useState<string>(deck?.variant ?? "balanced");
  useEffect(() => {
    // Новая колода — снова сбалансированный вариант, и с первого слайда.
    setVariantId(deck?.variant ?? "balanced");
  }, [deck?.id, deck?.variant]);

  const variant: DeckVariant | undefined = variants.find((item) => item.id === variantId);
  const slides = variant?.slides ?? deck?.slides ?? [];
  const download = variant?.download ?? deck?.download;
  // Файлы — строго выбранного варианта: пока его pdf готовится, чужой не
  // подсовываем. Поля колоды — только для старых задач без вариантов.
  const pdf = variant ? variant.pdf ?? null : deck?.pdf ?? null;
  const htmlPage = variant ? variant.html ?? null : deck?.html ?? null;
  const defects = variant?.defects ?? deck?.defects ?? [];
  const active = slides[current];
  const ready = deck?.status === "ready";
  const repairing = deck?.status === "running" && (deck.stage ?? "").startsWith("ремонт");
  const [auditOpen, setAuditOpen] = useState(false);
  const errors = defects.filter((defect) => defect.severity === "error").length;

  const pickVariant = (id: string) => {
    setVariantId(id);
    onCurrent(0);
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-edge-panel
                         bg-panel px-4">
        <button
          type="button"
          aria-label="Назад"
          onClick={props.onBack}
          className="icon-button h-9 w-9 rounded-[10px] border-transparent"
        >
          <ArrowLeft size={17} />
        </button>
        <span className="truncate text-[14px] font-medium text-ink-primary">
          {title.length > 48 ? `${title.slice(0, 48)}…` : title}
        </span>
        <span className="rounded-pill bg-white/[0.06] px-2 py-0.5 text-[11px] text-ink-label">
          черновик
        </span>

        {variants.length > 1 && (
          <div
            role="tablist"
            aria-label="Вариант вёрстки"
            className="ml-3 flex items-center gap-1 rounded-pill bg-white/[0.06] p-0.5"
          >
            {variants.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={item.id === variantId}
                title={item.tagline}
                onClick={() => pickVariant(item.id)}
                className={`rounded-pill px-3 py-1 text-[12px] transition-colors ${
                  item.id === variantId
                    ? "bg-vk text-white"
                    : "text-ink-muted hover:text-ink-primary"
                }`}
              >
                {item.label}
                <span className="ml-1.5 text-[11px] opacity-70">{item.slides.length}</span>
              </button>
            ))}
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          {(defects.length > 0 || (variant?.checks?.length ?? 0) > 0) && (
            <button
              type="button"
              onClick={() => setAuditOpen((open) => !open)}
              aria-pressed={auditOpen}
              className="pill-ghost h-[34px]"
            >
              Аудит
              <span
                className="rounded-pill px-1.5 text-[11px]"
                style={{ background: errors ? "rgba(255,107,107,0.18)" : "rgba(255,255,255,0.08)" }}
              >
                {defects.length}
              </span>
            </button>
          )}
          <button
            type="button"
            onClick={() => props.onShare(htmlPage)}
            disabled={!htmlPage}
            title={htmlPage ? undefined : "Страница этого варианта ещё готовится"}
            className="pill-ghost h-[34px]"
          >
            <Share size={14} />
            Поделиться
          </button>
          {pdf && (
            <button type="button" onClick={() => props.onDownloadPdf(pdf)} className="pill-ghost h-[34px]">
              <Download size={14} />
              PDF
            </button>
          )}
          <button
            type="button"
            onClick={() => download && props.onDownload(download)}
            disabled={!ready || !download}
            title={ready && !download ? "Файл этого варианта ещё готовится" : undefined}
            className="pill-primary h-[34px]"
          >
            <Download size={14} />
            Скачать .pptx
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <nav className="w-[200px] shrink-0 overflow-y-auto border-r border-edge-panel
                        bg-panel p-3">
          <div className="flex flex-col gap-3">
            {slides.map((slide, index) => (
              <button
                key={slide.n}
                type="button"
                onClick={() => onCurrent(index)}
                className="flex items-start gap-2 text-left"
              >
                <span
                  className={`pt-1 text-[11px] font-semibold ${
                    index === current ? "text-vk-light" : "text-ink-label"
                  }`}
                >
                  {slide.n}
                </span>
                <span
                  className="block flex-1 overflow-hidden rounded-[8px]"
                  style={{
                    border:
                      index === current
                        ? "2px solid #0077FF"
                        : "2px solid rgba(255,255,255,0.10)",
                  }}
                >
                  <Thumb slide={slide} />
                </span>
              </button>
            ))}
          </div>
        </nav>

        <div className="flex min-w-0 flex-1 flex-col items-center justify-center gap-5
                        bg-stage p-8">
          {(!ready || repairing) && (
            <div className="flex items-center gap-2.5 text-[13.5px] text-ink-muted">
              <Spinner />
              {deck?.stage || "Собираю слайды…"}
            </div>
          )}

          {active && (
            <>
              <div
                className="w-full max-w-[860px] overflow-hidden rounded-slide bg-white
                           shadow-slide"
                style={{ aspectRatio: "16 / 9" }}
              >
                {active.image ? (
                  <img
                    src={active.image}
                    alt={`Слайд ${active.n}`}
                    className="h-full w-full object-contain"
                  />
                ) : (
                  <Placeholder title={active.key_message} kicker={active.archetype} />
                )}
              </div>

              <div className="flex items-center gap-4">
                <button
                  type="button"
                  aria-label="Предыдущий слайд"
                  onClick={() => onCurrent(Math.max(0, current - 1))}
                  className={`icon-button h-9 w-9 ${current === 0 ? "opacity-40" : ""}`}
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="text-[13px] text-ink-label">
                  {current + 1} / {slides.length}
                </span>
                <button
                  type="button"
                  aria-label="Следующий слайд"
                  onClick={() => onCurrent(Math.min(slides.length - 1, current + 1))}
                  className={`icon-button h-9 w-9 ${
                    current >= slides.length - 1 ? "opacity-40" : ""
                  }`}
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </>
          )}
        </div>

        {auditOpen && (
          <Audit
            defects={defects}
            checks={variant?.checks}
            skipped={variant?.skipped_checks}
            repaired={variant?.repaired}
            busy={repairing}
            onSlide={onCurrent}
            onRepair={(ids) => props.onRepair?.(variantId, ids)}
            onClose={() => setAuditOpen(false)}
          />
        )}
      </div>
    </div>
  );
}

function Thumb({ slide }: { slide: DeckSlide }) {
  if (slide.image) {
    return (
      <img
        src={slide.image}
        alt=""
        className="block aspect-[16/9] w-full bg-white object-contain"
      />
    );
  }
  return (
    <span className="flex aspect-[16/9] w-full flex-col justify-end bg-white p-1.5">
      <span className="mb-1 block h-1 w-6 bg-vk" />
      <span className="block truncate text-[8.5px] font-semibold text-slide-title">
        {slide.key_message}
      </span>
    </span>
  );
}

/** Пока рендерер недоступен, слайд показывается разметкой — не пустотой. */
function Placeholder({ title, kicker }: { title: string; kicker: string }) {
  return (
    <div className="flex h-full w-full flex-col justify-center px-[6.5%] py-[5.5%]">
      <span className="text-[13px] font-semibold uppercase tracking-[0.08em] text-vk">
        {kicker}
      </span>
      <span className="mt-3 text-[32px] font-bold leading-tight text-slide-title">
        {title}
      </span>
    </div>
  );
}
