import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { webcrypto } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../apps/web/src/shared/browser.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
function load(overrides = {}) {
  const scope = { exports: {}, crypto: { getRandomValues: value => webcrypto.getRandomValues(value) }, ...overrides };
  runInNewContext(compiled, scope);
  return scope.exports;
}

test('LAN requests get unique UUIDs without secure-context randomUUID', () => {
  const { newOperationId } = load();
  const ids = Array.from({ length: 1000 }, () => newOperationId());
  assert.equal(new Set(ids).size, ids.length);
  for (const id of ids) assert.match(id, /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
});

test('LAN copy works without navigator.clipboard and reports failed copy', async () => {
  let selected = false, removed = false, restored = false, copied = '';
  class Element { focus() { restored = true; } }
  const field = { style: {}, value: '', select() { selected = true; }, remove() { removed = true; } };
  const document = { activeElement: new Element(), createElement: () => field, body: { appendChild() {} }, execCommand: name => { assert.equal(name, 'copy'); copied = field.value; return true; } };
  const { copyText } = load({ navigator: {}, document, HTMLElement: Element });
  await copyText('local copy');
  assert.equal(copied, 'local copy');
  assert.ok(selected && removed && restored);
  document.execCommand = () => false;
  await assert.rejects(copyText('cannot copy'), /复制失败/);
});
