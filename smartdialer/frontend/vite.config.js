import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/seed": "http://localhost:8000",
      "/simulation": "http://localhost:8000",
      "/dashboard": "http://localhost:8000",
      "/agents": "http://localhost:8000",
      "/borrowers": "http://localhost:8000",
      "/calls": "http://localhost:8000",
      "/decisions": "http://localhost:8000",
      "/demo": "http://localhost:8000",
    },
  },
});
