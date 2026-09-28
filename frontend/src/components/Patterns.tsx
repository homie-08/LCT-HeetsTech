import { useState } from "react";
import type { Pattern } from "../api";

const ROLE_COLORS: Record<string, string> = {
  title: "#e5484d", subtitle: "#e07b39", body: "#3b82f6", item: "#0ea5e9",
  quote: "#8b5cf6", metric_value: "#16a34a", metric_label: "#65a30d",
  image: "#a855f7", chart: "#0891b2", table: "#0d9488", caption: "#64748b",
};

/** Библиотека паттернов с разметкой слотов поверх настоящего рендера. */
export function PatternGallery({ patterns }: { patterns: Pattern[] }) {
  const [showSlots, setShowSlots] = useState(true);

  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          Паттерны слайдов <span className="text-neutral-400">({patterns.length})</span>
        </h2>
        <label className="flex items-center gap-2 text-sm text-neutral-600">
          <input
            type="checkbox"
            checked={showSlots}
            onChange={(event) => setShowSlots(event.target.checked)}
          />
          показывать слоты
        </label>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {patterns.map((pattern) => (
          <article key={pattern.id} className="overflow-hidden rounded-lg border border-neutral-200">
            <header className="flex items-baseline justify-between gap-2 border-b border-neutral-200 px-3 py-2">
              <span className="text-sm font-semibold">{pattern.archetype}</span>
              <span className="font-mono text-xs text-neutral-400">
                {pattern.confidence.toFixed(2)}
              </span>
            </header>

            <div className="relative bg-neutral-100" style={{ aspectRatio: "4 / 3" }}>
              {pattern.preview ? (
                <img src={pattern.preview} alt="" className="h-full w-full object-contain" />
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-neutral-400">
                  превью недоступно
                </div>
              )}
              {showSlots &&
                pattern.slots.map((slot, index) => (
                  <div
                    key={index}
                    className="absolute rounded-sm border"
                    style={{
                      left: `${slot.bbox[0] * 100}%`,
                      top: `${slot.bbox[1] * 100}%`,
                      width: `${slot.bbox[2] * 100}%`,
                      height: `${slot.bbox[3] * 100}%`,
                      borderColor: ROLE_COLORS[slot.role] ?? "#888",
                    }}
                  >
                    <span
                      className="absolute left-0 top-0 whitespace-nowrap px-1 font-mono text-[9px] leading-4 text-white"
                      style={{ background: ROLE_COLORS[slot.role] ?? "#888" }}
                    >
                      {slot.role}
                    </span>
                  </div>
                ))}
            </div>

            <footer className="space-y-1 px-3 py-2 text-xs text-neutral-500">
              <div className="truncate font-mono text-neutral-700">{pattern.name}</div>
              <div>
                {pattern.mode}
                {pattern.repeat ? ` · группа ↻${pattern.repeat}` : ""}
              </div>
              <div className="line-clamp-2">{pattern.evidence.join("; ")}</div>
            </footer>
          </article>
        ))}
      </div>
    </div>
  );
}
