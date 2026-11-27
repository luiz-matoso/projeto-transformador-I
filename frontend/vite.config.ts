import { defineConfig, loadEnv } from "vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const base = env.VITE_BASE_PATH || "/";
  const proxyPath = base + "api";
  return {
    plugins: [react(), tailwindcss()],
    base,
    server: {
      proxy: {
        [proxyPath]: {
          target: env.VITE_API_URL || "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.slice(proxyPath.length) || "/",
        },
      },
    },
  };
});
