import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { cpSync, mkdirSync } from 'node:fs'
export default defineConfig(({ mode }) => {
 const env = loadEnv(mode, process.cwd(), '')
 const target = env.BACKEND_URL || 'http://localhost:5000'
 const proxy = Object.fromEntries(['/api', '/messages', '/conversation_key', '/public_key', '/send', '/upload_file', '/upload_image', '/upload_audio', '/uploads', '/static'].map(path => [path, { target, changeOrigin: false }]))
 proxy['/ws'] = { target, ws: true, changeOrigin: false }
 return {
  plugins: [vue(), {
   name: 'preserve-existing-assets',
   closeBundle() {
    mkdirSync('dist/static/assets', { recursive: true })
    for (const folder of ['css', 'images']) cpSync('static/assets/' + folder, 'dist/static/assets/' + folder, { recursive: true })
   }
  }],
  publicDir: false,
  build: { outDir: 'dist' },
  server: { proxy }
 }
})
