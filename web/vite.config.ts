import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// O build vai para dentro do pacote Python (carregado por file:// pelo pywebview).
// base './' porque a página abre por file://, sem servidor.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../src/gf_ui_editor/web_dist',
    emptyOutDir: true,
  },
  server: { port: 5173, strictPort: true },
})
