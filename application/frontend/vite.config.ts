import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En développement, l'API FastAPI tourne sur 127.0.0.1:8765 (python -m dermia).
// Lancer le serveur avec DERMIA_ORIGINES=http://localhost:5173 pour autoriser les requêtes du serveur de dev.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 800 },
})
