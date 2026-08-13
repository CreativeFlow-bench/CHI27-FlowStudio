import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const target = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom"],
          "vendor-three": [
            "three",
            "three/examples/jsm/loaders/GLTFLoader.js",
            "three/examples/jsm/loaders/MTLLoader.js",
            "three/examples/jsm/loaders/OBJLoader.js",
            "three/examples/jsm/loaders/PLYLoader.js",
            "three/examples/jsm/controls/OrbitControls.js",
          ],
        },
      },
    },
  },
  server: {
    proxy: Object.fromEntries(
      ["/api", "/health", "/files", "/ws"].map((path) => [path, { target, ws: path === "/ws" }]),
    ),
  },
});
