import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import type { IncomingMessage, ServerResponse } from 'http'

/**
 * code-server proxy 환경 대응:
 * - code-server는 /proxy/5173/* → localhost:5173/* 로 프록시 (prefix strip)
 * - 브라우저 URL은 /proxy/5173/* 이므로, HTML 내 asset 경로도 /proxy/5173/* 이어야 함
 * - Vite base='/proxy/5173/' 설정하면 HTML이 /proxy/5173/ 에서만 서빙됨
 * - code-server가 prefix를 strip하므로 localhost:5173/ 로 요청이 오면 404
 * - 해결: 플러그인으로 / 요청을 /proxy/5173/ 로 내부 리라이트
 */
function codeServerProxy(): Plugin {
  const prefix = process.env.VITE_PROXY_BASE
  if (!prefix) return { name: 'noop' }

  return {
    name: 'code-server-proxy',
    configureServer(server) {
      server.middlewares.use((req: IncomingMessage, _res: ServerResponse, next: () => void) => {
        // Rewrite: strip된 경로를 base path 아래로 리라이트 (API는 제외)
        if (req.url && !req.url.startsWith(prefix) && !req.url.startsWith('/api')) {
          req.url = prefix + req.url.replace(/^\//, '')
        }
        next()
      })
    },
  }
}

const base = process.env.VITE_PROXY_BASE || '/'

export default defineConfig({
  plugins: [react(), codeServerProxy()],
  base,
  server: {
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
