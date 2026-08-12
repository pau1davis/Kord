import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind the IPv4 loopback explicitly. Vite defaults to [::1], which leaves
    // http://127.0.0.1:5173 unreachable — and 127.0.0.1 is the address Spotify
    // requires, so the OAuth round trip has to land somewhere that answers.
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
