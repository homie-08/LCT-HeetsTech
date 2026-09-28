import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
  server: {
    port: 5173,
    // Бэкенд поднимается отдельно: uvicorn sd.api:app --port 8021.
    // Порты 8000 и 8010 в этом репозитории заняты соседними проектами.
    proxy: { "/api": { target: "http://127.0.0.1:8021", changeOrigin: true } },
  },
});
