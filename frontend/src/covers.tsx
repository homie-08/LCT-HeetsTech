/** Мини-обложки шаблонов для сетки выбора.
 *
 * Рисуются чистым CSS и SVG, без растровых картинок: карточка 16/9 должна
 * читаться при ширине в полторы сотни пикселей, а превью настоящего слайда на
 * таком размере превращается в кашу. Шесть обложек описаны в хендоффе, и по ним
 * же узнаётся стиль шаблона.
 */

import type { CSSProperties, ReactNode } from "react";

function Frame({ style, children }: { style: CSSProperties; children?: ReactNode }) {
  return (
    <div
      className="relative aspect-[16/9] w-full overflow-hidden rounded-[10px]"
      style={style}
    >
      {children}
    </div>
  );
}

const COVERS: Array<() => ReactNode> = [
  // 1. Apricot White Brief — белая с красной чертой справа.
  () => (
    <Frame style={{ background: "#FBFAF7" }}>
      <div className="absolute inset-0 p-[9%]">
        <div className="text-[5px] font-semibold leading-tight text-[#2A2622]">
          ANPET MEDICAL GROUP
          <br />
          M&A DUE DILIGENCE REPORT
        </div>
      </div>
      <div className="absolute bottom-[12%] right-[9%] top-[12%] w-[1.5px] bg-[#D6472B]" />
    </Frame>
  ),
  // 2. Black Gold Ledger — чёрная с золотой ломаной.
  () => (
    <Frame style={{ background: "#0B0B0B" }}>
      <div className="absolute left-[8%] top-[12%] text-[5.5px] font-semibold leading-tight text-white">
        EMBODIED AI
        <br />
        <span className="text-[#F5C518]">VC QUARTERLY MONITOR</span>
      </div>
      <div className="absolute bottom-[6%] right-[7%] text-[13px] font-bold leading-none text-white/[0.07]">
        2026
      </div>
      <svg className="absolute bottom-[16%] left-[8%] w-[55%]" viewBox="0 0 100 24" fill="none">
        <polyline
          points="0,20 18,13 34,17 52,7 70,11 100,2"
          stroke="#F5C518"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </Frame>
  ),
  // 3. Rice Paper Annual — кремовая с голубой полосой.
  () => (
    <Frame style={{ background: "#F2EFE4" }}>
      <div className="absolute left-[8%] top-[14%] w-[55%] text-[5px] font-semibold leading-tight text-[#23231F]">
        2025 GLOBAL OFFSHORE WIND
        <br />
        O&amp;M SERVICES YEARBOOK
      </div>
      <div className="absolute bottom-[14%] left-[8%] h-[2px] w-[22%] bg-[#2E7D4F]" />
      <div className="absolute bottom-0 right-0 top-0 w-[26%] bg-[#C3DCF2]" />
    </Frame>
  ),
  // 4. Prospect Annual — светлая с тёмно-синей кромкой и крупным годом.
  () => (
    <Frame style={{ background: "#F8F9FC" }}>
      <div className="absolute inset-x-0 top-0 h-[3px] bg-[#0A2A6B]" />
      <div className="absolute left-[8%] top-[16%] w-[62%] text-[5px] font-semibold leading-tight text-[#0A2A6B]">
        2026 GLOBAL SMART MANUFACTURING
        <br />
        <span className="text-[#2563EB]">FROM PILOTS TO SCALE</span>
      </div>
      <div className="absolute bottom-[4%] right-[7%] text-[15px] font-bold leading-none text-[#C7D8F2]">
        2030
      </div>
    </Frame>
  ),
  // 5. Marine Blue Research — тёмно-синяя с контурной окружностью.
  () => (
    <Frame style={{ background: "#0D1B2A" }}>
      <div className="absolute left-[8%] top-[14%] w-[58%] text-[5px] font-semibold leading-tight text-white">
        COUNTY ON-DEMAND RETAIL
        <br />
        DELIVERY NETWORK OUTLOOK
      </div>
      <div
        className="absolute -bottom-[18%] -right-[8%] aspect-square w-[46%] rounded-full border"
        style={{ borderColor: "rgba(120,170,220,0.35)" }}
      />
      <div className="absolute bottom-[8%] left-[8%] text-[9px] font-bold leading-none text-white/25">
        2030
      </div>
    </Frame>
  ),
  // 6. Red-Black Business — чёрная с красной кромкой.
  () => (
    <Frame style={{ background: "#0C0C0C" }}>
      <div className="absolute inset-x-0 top-0 h-[3px] bg-[#E03131]" />
      <div className="absolute left-[8%] top-[18%] text-[4.5px] font-semibold uppercase tracking-[0.12em] text-[#E03131]">
        Stop Loss. Retail. Replicate.
      </div>
      <div className="absolute left-[8%] top-[32%] w-[70%] text-[5.5px] font-semibold leading-tight text-white">
        Fresh Tea Chain Network Diagnostics &amp; Store Performance
      </div>
    </Frame>
  ),
];

/** Обложка по индексу шаблона. Индексы за пределами набора зацикливаются. */
export function TemplateCover({ index }: { index: number }) {
  const render = COVERS[((index % COVERS.length) + COVERS.length) % COVERS.length];
  return <>{render()}</>;
}

export const COVER_COUNT = COVERS.length;
