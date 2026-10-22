import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The backend needs a shared secret. The proxy adds it server-side, so it never reaches the browser.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 4340,
      strictPort: true,
      proxy: {
        "/api": {
          // DEV_BACKEND=https://... points the dev screen at the deployed backend, so the local one can stay off
          target: process.env.DEV_BACKEND ?? "http://localhost:8000",
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
          headers: { "x-api-key": env.AGENT_SHARED_SECRET ?? "" },
        },
      },
    },
  };
});
