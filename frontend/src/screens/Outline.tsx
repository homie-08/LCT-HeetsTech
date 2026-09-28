/** Экран структуры: что за презентация получится, до её сборки. */

import { useEffect, useState } from "react";
import { plural } from "./Home";
import { Check, FileIcon, Spinner } from "../ui";

export interface OutlineItem {
  n: number;
  title: string;
  note: string;
}

export interface OutlineProps {
  prompt: string;
  fileName: string | null;
  items: OutlineItem[];
  loading: boolean;
  error: string;
  templateName: string;
  busy: boolean;
  onBack: () => void;
  onBuild: () => void;
}

// Пункты появляются по одному: структура читается как рассуждение, а не
// вываливается списком. Шаг взят из хендоффа.
const STEP_MS = 380;

export function Outline(props: OutlineProps) {
  const { items, loading, error } = props;
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (loading || items.length === 0) {
      setShown(0);
      return;
    }
    setShown(0);
    const timer = window.setInterval(() => {
      setShown((value) => {
        if (value >= items.length) {
          window.clearInterval(timer);
          return value;
        }
        return value + 1;
      });
    }, STEP_MS);
    return () => window.clearInterval(timer);
  }, [items, loading]);

  const done = !loading && shown >= items.length && items.length > 0;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[640px] flex-col gap-5 px-8 py-14">
        <div className="flex justify-end">
          <div className="max-w-[80%] rounded-[16px_16px_4px_16px] bg-white/[0.07] px-4 py-3
                          text-[14.5px] leading-relaxed text-ink-primary">
            {props.prompt}
          </div>
        </div>

        {props.fileName && (
          <div className="flex justify-end">
            <span
              className="inline-flex items-center gap-2 rounded-pill border px-3 py-1.5 text-[12.5px]"
              style={{
                background: "rgba(0,119,255,0.12)",
                borderColor: "rgba(0,119,255,0.32)",
                color: "#C9DFFF",
              }}
            >
              <FileIcon size={13} className="text-vk-light" />
              {props.fileName}
            </span>
          </div>
        )}

        <div className="flex items-center gap-2.5 text-[13.5px] text-ink-muted">
          {done ? <Check size={16} className="text-vk-light" /> : <Spinner />}
          {error ? (
            <span className="text-[#FF6B6B]">{error}</span>
          ) : (
            <span>{done ? "Структура готова" : "Собираю структуру…"}</span>
          )}
        </div>

        {items.length > 0 && (
          <div className="rounded-outline border border-edge-panel bg-outline">
            {items.slice(0, shown).map((item, index) => (
              <div
                key={item.n}
                className="animate-fadeUp px-5 py-4"
                style={{
                  borderTop: index === 0 ? "none" : "1px solid rgba(255,255,255,0.06)",
                }}
              >
                <div className="flex gap-3">
                  <span className="pt-[1px] text-[12.5px] font-semibold text-vk-light">
                    {String(item.n).padStart(2, "0")}
                  </span>
                  <div>
                    <div className="text-[14.5px] font-semibold text-ink-primary">
                      {item.title}
                    </div>
                    {item.note && (
                      <div className="mt-1 text-[13px] leading-relaxed text-ink-muted">
                        {item.note}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {done && (
          <div className="flex animate-fadeUp items-center gap-3">
            <span className="text-[13px] text-ink-label">
              {items.length} {plural(items.length, ["слайд", "слайда", "слайдов"])}
              {props.templateName ? ` · ${props.templateName}` : ""}
            </span>
            <button type="button" onClick={props.onBack} className="pill-ghost ml-auto">
              Изменить запрос
            </button>
            <button
              type="button"
              onClick={props.onBuild}
              disabled={props.busy}
              className="pill-primary"
            >
              {props.busy ? "Собираю…" : "Создать слайды"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
