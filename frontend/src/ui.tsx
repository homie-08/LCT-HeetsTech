/** Иконки и мелкие примитивы интерфейса.
 *
 * Иконки нарисованы инлайном в стиле Lucide (stroke 2–2.4): пакет ради
 * четырнадцати значков тянуть незачем, а инлайн наследует цвет от текста и не
 * добавляет ни запроса, ни зависимости.
 */

import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 16, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const Plus = (p: IconProps) => (
  <Icon {...p}><path d="M12 5v14M5 12h14" /></Icon>
);
export const Paperclip = (p: IconProps) => (
  <Icon {...p}>
    <path d="M21.4 11.05 12.25 20.2a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.67 3.67 0 1 1 5.19 5.19l-9.2 9.19a1.83 1.83 0 1 1-2.59-2.59l8.49-8.48" />
  </Icon>
);
export const ChevronDown = (p: IconProps) => (
  <Icon {...p}><path d="m6 9 6 6 6-6" /></Icon>
);
export const ChevronLeft = (p: IconProps) => (
  <Icon {...p}><path d="m15 18-6-6 6-6" /></Icon>
);
export const ChevronRight = (p: IconProps) => (
  <Icon {...p}><path d="m9 18 6-6-6-6" /></Icon>
);
export const ArrowUp = (p: IconProps) => (
  <Icon {...p}><path d="M12 19V5M5 12l7-7 7 7" /></Icon>
);
export const ArrowLeft = (p: IconProps) => (
  <Icon {...p}><path d="M19 12H5M12 19l-7-7 7-7" /></Icon>
);
export const FileIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5z" />
    <path d="M14 2v6h6" />
  </Icon>
);
export const X = (p: IconProps) => (
  <Icon {...p}><path d="M18 6 6 18M6 6l12 12" /></Icon>
);
export const Check = (p: IconProps) => (
  <Icon {...p}><path d="M20 6 9 17l-5-5" /></Icon>
);
export const Download = (p: IconProps) => (
  <Icon {...p}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <path d="M7 10l5 5 5-5M12 15V3" />
  </Icon>
);
export const Settings = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 8.6a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </Icon>
);
export const PanelLeft = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M9 3v18" />
  </Icon>
);
export const Share = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7" />
    <path d="M16 6l-4-4-4 4M12 2v13" />
  </Icon>
);

export const Trash = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
    <path d="M10 11v6M14 11v6" />
  </Icon>
);

export const Eye = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" />
    <circle cx="12" cy="12" r="3" />
  </Icon>
);

/** Логотип VK: суперэллипс и знак. */
export function VkLogo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-label="VK" role="img">
      <path
        fill="#0077FF"
        d="M0 11.52C0 6.09 0 3.374 1.687 1.687 3.374 0 6.09 0 11.52 0h.96c5.43 0 8.146 0 9.833 1.687C24 3.374 24 6.09 24 11.52v.96c0 5.43 0 8.146-1.687 9.833C20.626 24 17.91 24 12.48 24h-.96c-5.43 0-8.146 0-9.833-1.687C0 20.626 0 17.91 0 12.48Z"
      />
      <path
        fill="#fff"
        d="M12.77 17.3c-5.47 0-8.59-3.75-8.72-9.99h2.74c.09 4.58 2.11 6.52 3.71 6.92V7.31h2.58v3.95c1.58-.17 3.24-1.97 3.8-3.95h2.58a7.62 7.62 0 0 1-3.51 4.99 7.9 7.9 0 0 1 4.11 4.99h-2.84c-.66-2.06-2.18-3.66-4.14-3.86v3.86z"
      />
    </svg>
  );
}

/** Кольцо-спиннер из спецификации: 16px, верх подсвечен. */
export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2"
      style={{
        width: size,
        height: size,
        borderColor: "rgba(77,159,255,0.3)",
        borderTopColor: "#4D9FFF",
      }}
    />
  );
}

/** Всплывающее сообщение внизу экрана. */
export function Toast({ text }: { text: string }) {
  if (!text) return null;
  return (
    <div
      role="status"
      className="fixed bottom-7 left-1/2 z-50 -translate-x-1/2 animate-fadeUp rounded-pill
                 bg-[#F2F4F8] px-4 py-2 text-[13px] font-medium text-[#16181C] shadow-lg"
    >
      {text}
    </div>
  );
}
