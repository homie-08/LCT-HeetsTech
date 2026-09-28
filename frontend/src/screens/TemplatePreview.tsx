/** Предварительный просмотр шаблона: крупный слайд, коллаж и выбор стиля.
 *
 * Окно нарочно компактное и целиком помещается в экран: крупный первый слайд,
 * под ним коллаж из следующих трёх — просто картинки, не навигация.
 * «Продолжить просмотр» возвращает к сетке стилей, «Использовать стиль»
 * фиксирует выбор.
 */

import { useEffect } from "react";
import { Spinner, X } from "../ui";

export interface TemplatePreviewProps {
  label: string;
  images: string[];
  pending: number;
  onClose: () => void;
  onUse: () => void;
}

const COLLAGE = 3;

export function TemplatePreview(props: TemplatePreviewProps) {
  const { images } = props;
  const slide = images[0];
  const collage = images.slice(1, 1 + COLLAGE);

  // Esc закрывает — иначе модалка ловит пользователя в ловушку.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") props.onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [props]);

  return (
    // Оверлей прокручивается: когда окно выше экрана, оно не обрезается по
    // краям, а скролится вместе со страницей. Пока окно влезает целиком —
    // стоит по центру, как и раньше.
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Предварительный просмотр: ${props.label}`}
      className="fixed inset-0 z-50 overflow-y-auto bg-black/70"
    >
      <div
        className="flex min-h-full items-center justify-center p-6"
        onClick={props.onClose}
      >
      <div
        className="flex w-full max-w-[760px] animate-fadeUp flex-col gap-4 rounded-[16px]
                   border border-edge-panel bg-[#14161B] p-6 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center">
          <h2 className="text-[15px] font-medium text-ink-primary">
            Предварительный просмотр
          </h2>
          <span className="ml-3 truncate text-[13px] text-ink-label">{props.label}</span>
          <button
            type="button"
            aria-label="Закрыть"
            onClick={props.onClose}
            className="icon-button ml-auto h-8 w-8 rounded-[10px] border-transparent"
          >
            <X size={17} />
          </button>
        </div>

        <div
          className="relative mx-auto w-full overflow-hidden rounded-[10px] bg-white"
          style={{ aspectRatio: "16 / 9", maxHeight: "52vh" }}
        >
          {slide ? (
            <img src={slide} alt="" className="h-full w-full object-contain" />
          ) : (
            <div className="flex h-full items-center justify-center">
              <Spinner size={20} />
            </div>
          )}
        </div>

        {(collage.length > 0 || props.pending > 0) && (
          <div className="grid grid-cols-3 gap-3">
            {collage.map((image) => (
              <img
                key={image}
                src={image}
                alt=""
                className="block aspect-[16/9] w-full rounded-[8px] border
                           border-edge-control bg-white object-cover"
              />
            ))}
            {props.pending > 0 && collage.length < COLLAGE && (
              <span className="flex aspect-[16/9] items-center justify-center gap-2
                               rounded-[8px] border border-edge-control text-[12px]
                               text-ink-label">
                <Spinner size={13} />
                готовлю
              </span>
            )}
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          {/* Возврат к сетке: пользователь смотрит стили дальше, выбор не меняется. */}
          <button type="button" onClick={props.onClose} className="pill-ghost h-[36px]">
            Продолжить просмотр
          </button>
          <button type="button" onClick={props.onUse} className="pill-primary h-[36px]">
            Использовать стиль
          </button>
        </div>
      </div>
      </div>
    </div>
  );
}
