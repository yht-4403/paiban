import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { previewBoundary } from './preview-boundary.mjs';

test('public HMR permits browser assets but blocks workspace files and bootstrap', () => {
  const root = mkdtempSync(join(tmpdir(), 'accord-preview-'));
  try {
    for (const dir of ['apps/web/src', 'apps/web/node_modules/.vite-preview', 'node_modules/package', '.local']) mkdirSync(join(root, dir), { recursive: true });
    writeFileSync(join(root, 'apps/web/src/main.tsx'), 'export {}');
    writeFileSync(join(root, 'node_modules/package/index.js'), 'export {}');
    writeFileSync(join(root, '.local/private.txt'), 'private');
    symlinkSync(join(root, '.local'), join(root, 'node_modules/escape'));
    const boundary = previewBoundary(root, 'accord-test.trycloudflare.com');
    for (const path of ['/', '/@vite/client', '/src/main.tsx', '/api/auth/login', '/api/state', '/@fs' + join(root, 'node_modules/package/index.js')]) assert.equal(boundary.allows(path), true, path);
    for (const path of ['/.env', '/.env?raw', '/vite.config.ts', '/api/auth/setup', '/api/auth/setup/', '/api//auth/setup', '/api/auth/%73etup', '/api/auth/%2573etup', '/src/../.env', '/src/%2e%2e/.env', '/src\\..\\.env', '/@fs' + join(root, '.local/private.txt'), '/@fs' + join(root, 'node_modules/escape/private.txt'), '/@fs/etc/passwd', '/@id/__x00__/etc/passwd']) assert.equal(boundary.allows(path), false, path);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('public proxy sets secure cookies and replaces spoofed forwarding headers', () => {
  const handlers = {};
  previewBoundary('/tmp/accord', 'accord-test.trycloudflare.com').configureProxy({ on: (event, fn) => { handlers[event] = fn; } });
  const headers = { 'x-forwarded-for': 'spoofed', 'x-forwarded-host': 'spoofed' };
  const outgoing = { removeHeader: key => delete headers[key], setHeader: (key, value) => { headers[key] = value; } };
  handlers.proxyReq(outgoing, { headers: { 'cf-connecting-ip': '203.0.113.7' } });
  assert.deepEqual(headers, { 'x-forwarded-for': '203.0.113.7', 'x-forwarded-proto': 'https' });
  const response = { headers: { 'set-cookie': ['session=value; HttpOnly; SameSite=lax', 'already=value; Secure'] } };
  handlers.proxyRes(response);
  assert.equal(response.headers['set-cookie'][0], 'session=value; HttpOnly; SameSite=lax; Secure');
  assert.equal(response.headers['set-cookie'][1], 'already=value; Secure');
});

test('LAN proxy uses the socket IP, keeps HTTP cookies usable and ignores Cloudflare spoofing', () => {
  const handlers = {};
  previewBoundary('/tmp/accord', '192.168.18.225', { secure: false, cloudflare: false }).configureProxy({ on: (event, fn) => { handlers[event] = fn; } });
  const headers = { 'x-forwarded-for': 'spoofed', 'x-forwarded-host': 'spoofed' };
  handlers.proxyReq({ removeHeader: key => delete headers[key], setHeader: (key, value) => { headers[key] = value; } }, { headers: { 'cf-connecting-ip': '203.0.113.7' }, socket: { remoteAddress: '192.168.18.10' } });
  assert.deepEqual(headers, { 'x-forwarded-for': '192.168.18.10', 'x-forwarded-proto': 'http' });
  const response = { headers: { 'set-cookie': ['session=value; HttpOnly; SameSite=lax'] } };
  handlers.proxyRes(response);
  assert.equal(response.headers['set-cookie'][0], 'session=value; HttpOnly; SameSite=lax');
});
