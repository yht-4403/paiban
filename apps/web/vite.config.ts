import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';
import { previewBoundary } from '../../tools/preview-boundary.mjs';

const previewHost = process.env.ACCORD_PREVIEW_HOST;
const previewIsLocal = process.env.ACCORD_PREVIEW_MODE === 'lan' || previewHost === '127.0.0.1' || previewHost === 'localhost';
const boundary = previewHost ? previewBoundary(fileURLToPath(new URL('../..', import.meta.url)), previewHost, { secure: !previewIsLocal, cloudflare: !previewIsLocal }) : undefined;

export default defineConfig({
  plugins: [boundary?.plugin, react(), tailwindcss()],
  cacheDir: previewHost ? '../../node_modules/.vite-preview' : process.env.ACCORD_API_PROXY ? '../../.local/vite-validation' : '../../.local/vite-web',
  server: {
    ...(previewHost ? {
      allowedHosts: [previewHost], cors: { origin: previewIsLocal ? `http://${previewHost}:5188` : `https://${previewHost}` },
      hmr: { protocol: previewIsLocal ? 'ws' : 'wss', host: previewHost, clientPort: previewIsLocal ? 5188 : 443, overlay: false },
      fs: boundary!.fs,
    } : {}),
    proxy: { '/api': {
      target: process.env.ACCORD_API_PROXY || 'http://127.0.0.1:8786', changeOrigin: false,
      ...(boundary ? { configure: boundary.configureProxy } : {}),
    } },
  },
});
