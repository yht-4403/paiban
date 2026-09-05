import { realpathSync, existsSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { isIP } from 'node:net';

// Public HMR only needs browser modules. Never expose the repository workspace.
export function previewBoundary(root, hostname, { secure = true, cloudflare = true } = {}) {
  const web = resolve(root, 'apps/web');
  const roots = ['apps/web/src', 'apps/web/public', 'node_modules'].map(p => {
    const path = resolve(root, p);
    return existsSync(path) ? realpathSync(path) : path;
  });
  const within = (path, parent) => path === parent || path.startsWith(parent + sep);
  const fileAllowed = path => {
    try { return roots.some(parent => within(realpathSync(path), parent)); } catch { return false; }
  };
  function allows(rawUrl) {
    let path;
    try { path = decodeURIComponent(rawUrl.split('?')[0]); } catch { return false; }
    if (/[\\\0%]/.test(path) || path.includes('//') || path.split('/').some(p => p === '..' || p === '.')) return false;
    if (path.split('/').some(p => /^\.env(?:\.|$)|^\.git$|^\.local$/.test(p)) || /\.(?:db|sqlite3?|pem|key)(?:$|\/)/i.test(path)) return false;
    if (/^\/api\/auth\/setup\/?$/.test(path)) return false;
    if (path.startsWith('/api/')) return true;
    if (['/', '/index.html', '/@vite/client', '/@react-refresh'].includes(path)) return true;
    if (path.startsWith('/@fs/')) return fileAllowed(path.slice(4));
    if (path.startsWith('/src/') || path.startsWith('/node_modules/')) return fileAllowed(resolve(web, '.' + path));
    if (path.startsWith('/@id/')) return false;
    return existsSync(resolve(web, 'public')) && fileAllowed(resolve(web, 'public', '.' + path));
  }
  return {
    allows,
    plugin: {
      name: 'accord-preview-boundary',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          res.setHeader('X-Robots-Tag', 'noindex, nofollow');
          res.setHeader('Cache-Control', 'no-store');
          res.setHeader('X-Content-Type-Options', 'nosniff');
          const host = req.headers.host?.split(':')[0];
          if (![hostname, '127.0.0.1', 'localhost'].includes(host) || !allows(req.url || '/')) {
            res.writeHead(403, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify({ detail: '此路径不能通过团队预览访问。' }));
            return;
          }
          next();
        });
      },
    },
    fs: { strict: true, allow: [...roots, resolve(web, 'index.html')], deny: ['**/.env*', '**/.git/**', '**/.local/**', '**/*.{db,sqlite,sqlite3,pem,key}'] },
    configureProxy(proxy) {
      proxy.on('proxyReq', (outgoing, incoming) => {
        // Cloudflare overwrites this header. Ignore client-supplied forwarding chains.
        const ip = cloudflare ? incoming.headers['cf-connecting-ip'] : incoming.socket?.remoteAddress;
        outgoing.removeHeader('x-forwarded-for');
        outgoing.removeHeader('x-forwarded-host');
        if (typeof ip === 'string' && isIP(ip)) outgoing.setHeader('x-forwarded-for', ip);
        outgoing.setHeader('x-forwarded-proto', secure ? 'https' : 'http');
      });
      proxy.on('proxyRes', response => {
        if (secure && response.headers['set-cookie']) response.headers['set-cookie'] = response.headers['set-cookie'].map(cookie => /;\s*secure(?:;|$)/i.test(cookie) ? cookie : cookie + '; Secure');
      });
    },
  };
}
