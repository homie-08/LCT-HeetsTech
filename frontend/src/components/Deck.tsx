import type { DeckJob } from "../api";

const METRIC_LABELS: Record<string, string> = {
  font_conformance: "шрифты",
  palette_conformance: "палитра",
  grid_alignment: "сетка",
  contrast_pass: "контраст",
  coverage: "покрытие",
  pattern_diversity: "разнообразие",
};

/** Результат сборки: слайды с объяснением выбора макета и отчёт нормоконтроля. */
export function DeckView({ deck }: { deck: DeckJob }) {
  const metrics = deck.metrics ?? {};
  const errors = (deck.defects ?? []).filter((defect) => defect.severity === "error");
  const notices = (deck.defects ?? []).filter((defect) => defect.severity !== "error");

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-x-6 gap-y-3 p-4">
        {Object.entries(METRIC_LABELS).map(([key, label]) => (
          <div key={key}>
            <div className="label">{label}</div>
            <div className="text-lg font-semibold tabular-nums">
              {metrics[key] === undefined ? "—" : `${Math.round(metrics[key] * 100)}%`}
            </div>
          </div>
        ))}
        <div>
          <div className="label">переполнений</div>
          <div className="text-lg font-semibold tabular-nums">
            {metrics.overflow_slides ?? 0}
          </div>
        </div>
        <div>
          <div className="label">коллизий</div>
          <div className="text-lg font-semibold tabular-nums">
            {metrics.collision_slides ?? 0}
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span
            className={`chip ${errors.length === 0 ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}
          >
            {errors.length === 0 ? "дефектов нет" : `дефектов: ${errors.length}`}
          </span>
          {deck.download && (
            <a className="btn-primary" href={deck.download} download>
              Скачать .pptx
            </a>
          )}
        </div>
      </div>

      {errors.length > 0 && (
        <ul className="card space-y-1 p-4 text-sm text-amber-800">
          {errors.map((defect, index) => (
            <li key={index}>
              ⚠ слайд {defect.slide}: {defect.message}
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {(deck.slides ?? []).map((slide) => (
          <article key={slide.n} className="card overflow-hidden">
            <div className="bg-neutral-100" style={{ aspectRatio: "4 / 3" }}>
              {slide.image ? (
                <img src={slide.image} alt="" className="h-full w-full object-contain" />
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-neutral-400">
                  рендер недоступен
                </div>
              )}
            </div>
            <div className="space-y-1 p-3">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-semibold">
                  {slide.n}. {slide.intent}
                </span>
                <span className="chip">{slide.archetype}</span>
              </div>
              <div className="line-clamp-2 text-sm text-neutral-700">
                {slide.key_message || <span className="text-neutral-400">без заголовка</span>}
              </div>
              <div className="truncate font-mono text-xs text-neutral-500">
                {slide.pattern_name} · слотов {slide.used_slots}/{slide.total_slots}
              </div>
              <div className="text-[11px] leading-4 text-neutral-400">{slide.why}</div>
            </div>
          </article>
        ))}
      </div>

      {(notices.length > 0 || (deck.notes ?? []).length > 0) && (
        <details className="card p-4 text-sm text-neutral-600">
          <summary className="cursor-pointer font-medium">
            Замечания ({notices.length + (deck.notes ?? []).length})
          </summary>
          <ul className="mt-2 space-y-1 text-xs">
            {notices.map((defect, index) => (
              <li key={`d${index}`}>
                · [{defect.kind}] слайд {defect.slide}: {defect.message}
              </li>
            ))}
            {(deck.notes ?? []).map((note, index) => (
              <li key={`n${index}`}>· {note}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
