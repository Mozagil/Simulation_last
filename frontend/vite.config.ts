import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 0.0.0.0'a bağlan — Codespaces/Docker port yönlendirmesi için şart.
    host: true,
    // Port doluysa sessizce 5174'e kayma; hata ver. Aksi halde PORTS'ta
    // 5173'e bakılırken sunucu başka portta çalışıyor ve 404 sanılıyor.
    strictPort: true,
  },
});
