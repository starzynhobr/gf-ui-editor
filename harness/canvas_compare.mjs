import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { build } from '../web/node_modules/vite/dist/node/index.js'

const root = fileURLToPath(new URL('..', import.meta.url))
await build({
  root,
  configFile: resolve(root, 'web/vite.config.ts'),
  build: {
    outDir: resolve(process.argv[2]),
    emptyOutDir: false,
    rollupOptions: { input: resolve(root, 'harness/canvas_compare.html') },
  },
})
