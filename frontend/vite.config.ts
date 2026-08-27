import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Dev proxy thay cho Next.js API route cũ: giữ URL tương đối /api để cookie
  // và SSE hoạt động như khi deploy sau nginx.
  const backendTarget = env.VITE_BACKEND_ORIGIN || "http://127.0.0.1:8023";

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      host: true,
      port: Number(env.VITE_PORT || 5173),
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          // SSE cần tắt buffering để token tới UI ngay.
          configure: (proxy) => {
            proxy.on("proxyRes", (proxyRes) => {
              if (proxyRes.headers["content-type"]?.includes("text/event-stream")) {
                proxyRes.headers["cache-control"] = "no-cache, no-transform";
              }
            });
          },
        },
        "/health": { target: backendTarget, changeOrigin: true },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: mode !== "production",
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: true,
    },
  };
});
