/** Панель аудита: находки по чек-листу, выбор того, что чинить. */

import { useEffect, useMemo, useState } from "react";

import type { DeckDefect } from "../api";
import { Check as CheckIcon, Spinner, X } from "../ui";

export interface AuditProps {
  defects: DeckDefect[];
  checks?: string[];
  skipped?: Record<string, string>;
  repaired?: number[];
  busy: boolean;
  /** Открыть слайд, к которому относится находка (индекс с нуля). */
  onSlide: (index: number) => void;
  /** Починить выбранные — адреса находок. */
  onRepair: (ids: string[]) => void;
  onClose: () => void;
}

const NATURE: Record<string, string> = {
  deterministic: "детерминированная",
  contextual: "контекстуальная",
};

const SEVERITY: Record<string, string> = {
  error: "#FF6B6B",
  warning: "#F5B84A",
  info: "#8C96A6",
};

export function Audit({ defects, checks = [], skipped = {}, repaired, busy, ...props }: AuditProps) {
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  // Сбрасываем выбор, только когда меняется сам состав находок. Сравнивать
  // массивы по ссылке нельзя: пока колода дособирает файлы, опрос приносит
  // новый массив каждую секунду — и галочки пропадали прямо под курсором.
  const signature = useMemo(() => defects.map((defect) => defect.id).join("|"), [defects]);
  useEffect(() => setChosen(new Set()), [signature]);

  const groups = useMemo(() => {
    const map = new Map<string, DeckDefect[]>();
    defects.forEach((defect) => {
      const key = defect.group || "прочее";
      map.set(key, [...(map.get(key) ?? []), defect]);
    });
    return [...map.entries()];
  }, [defects]);

  const fixable = defects.filter((defect) => defect.fixable);
  const toggle = (id: string) => {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <aside
      aria-label="Аудит"
      className="flex w-[340px] shrink-0 flex-col border-l border-edge-panel bg-panel"
    >
      <header className="flex h-12 items-center gap-2 border-b border-edge-panel px-4">
        <span className="text-[13px] font-semibold text-ink-primary">Аудит</span>
        <span className="text-[12px] text-ink-label">
          {checks.length} проверок · {defects.length} находок
        </span>
        <button
          type="button"
          aria-label="Закрыть аудит"
          onClick={props.onClose}
          className="icon-button ml-auto h-8 w-8 rounded-[8px] border-transparent"
        >
          <X size={14} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 text-[12.5px]">
        {defects.length === 0 && (
          <p className="text-ink-muted">По чек-листу находок нет.</p>
        )}
        {groups.map(([group, items]) => (
          <section key={group} className="mb-4">
            <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-label">
              {group}
            </h3>
            <ul className="flex flex-col gap-1.5">
              {items.map((defect) => (
                <li key={defect.id} className="flex items-start gap-2">
                  {defect.fixable ? (
                    <input
                      type="checkbox"
                      aria-label={`Починить: ${defect.message}`}
                      checked={chosen.has(defect.id)}
                      onChange={() => toggle(defect.id)}
                      disabled={busy}
                      className="mt-[3px] accent-vk"
                    />
                  ) : (
                    <span className="mt-[3px] block h-[13px] w-[13px] shrink-0" aria-hidden />
                  )}
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => defect.slide && props.onSlide(defect.slide - 1)}
                      className="text-left text-ink-primary hover:underline"
                    >
                      <span
                        className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle"
                        style={{ background: SEVERITY[defect.severity] ?? SEVERITY.info }}
                        aria-hidden
                      />
                      {defect.slide ? `Слайд ${defect.slide}: ` : ""}
                      {defect.message}
                    </button>
                    <div className="text-[11px] text-ink-label">
                      {NATURE[defect.nature] ?? defect.nature}
                      {defect.fixable ? ` · ${defect.fix}` : " · сборка это не меняет"}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}

        {Object.keys(skipped).length > 0 && (
          <p className="mt-2 text-[11px] text-ink-label">
            Пропущено: {Object.entries(skipped).map(([id, why]) => `${id} (${why})`).join(", ")}.
          </p>
        )}
        {repaired && repaired.length > 0 && (
          <p className="mt-2 flex items-center gap-1 text-[11px] text-ink-label">
            <CheckIcon size={12} /> Пересобраны слайды {repaired.join(", ")}.
          </p>
        )}
      </div>

      <footer className="border-t border-edge-panel p-3">
        <button
          type="button"
          onClick={() => props.onRepair([...chosen])}
          disabled={busy || chosen.size === 0}
          className="pill-primary h-[34px] w-full justify-center"
        >
          {busy ? <Spinner size={14} /> : <CheckIcon size={14} />}
          {busy ? "Пересобираю…" : `Исправить выбранное (${chosen.size} из ${fixable.length})`}
        </button>
      </footer>
    </aside>
  );
}
