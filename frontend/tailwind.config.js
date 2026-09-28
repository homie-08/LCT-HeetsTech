/** @type {import('tailwindcss').Config} */

// Токены из дизайн-хендоффа «VK Slides». Значения не приблизительные:
// вёрстка делается пиксель-в-пиксель, поэтому все цвета, радиусы и тени
// лежат здесь по именам из спецификации, а не проставляются по месту.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "#0A0B0E",
        panel: "#0E1014",
        stage: "#08090B",
        card: "rgba(18,20,26,0.92)",
        outline: "rgba(18,20,26,0.6)",
        vk: {
          DEFAULT: "#0077FF",
          hover: "#1E85FF",
          pressed: "#0066DB",
          light: "#4D9FFF",
          link: "#79B8FF",
          deep: "#12253F",
        },
        ink: {
          primary: "#F2F4F8",
          secondary: "#C3C9D4",
          muted: "#9BA3B0",
          weak: "#6B7280",
          label: "#5C6470",
        },
        edge: {
          panel: "rgba(255,255,255,0.08)",
          control: "rgba(255,255,255,0.12)",
          hover: "rgba(77,159,255,0.55)",
        },
        slide: {
          bg: "#FFFFFF",
          title: "#16181C",
          text: "#3C4250",
          caption: "#7A828E",
        },
      },
      fontFamily: {
        sans: ["Onest", "system-ui", "sans-serif"],
        // VK Sans Display Expanded — проприетарный; ближайшая открытая замена
        // по брендовому референсу — Unbounded.
        display: ["Unbounded", "Onest", "system-ui", "sans-serif"],
      },
      borderRadius: {
        pill: "999px",
        card: "20px",
        outline: "16px",
        slide: "12px",
      },
      boxShadow: {
        input: "0 12px 56px rgba(0,80,255,0.16), 0 2px 10px rgba(0,0,0,0.45)",
        slide: "0 16px 64px rgba(0,60,200,0.22), 0 4px 16px rgba(0,0,0,0.5)",
        title: "0 0 60px rgba(0,119,255,0.35)",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        glowPulse: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        fadeUp: "fadeUp .28s ease both",
        glowPulse: "glowPulse 6.5s ease-in-out infinite",
        spin: "spin .7s linear infinite",
      },
      transitionTimingFunction: {
        panel: "cubic-bezier(.4,0,.2,1)",
      },
    },
  },
  plugins: [],
};
