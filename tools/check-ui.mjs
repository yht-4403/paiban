import { readdir, readFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';

async function files(path) {
  const entries = await readdir(path, { withFileTypes: true });
  return (await Promise.all(entries.map(e => e.isDirectory() ? files(join(path,e.name)) : [join(path,e.name)]))).flat();
}
const errors=[];
for (const path of await files(resolve('apps/web/src'))) {
  const source=await readFile(path,'utf8');
  if (/(?:#[a-f\d]{3,8}\b|\b(?:rgb|rgba|hsl|oklch)\()/i.test(source)) errors.push(`${path}: raw palette value`);
  if (/@tutti-os\/ui-system\/(?:src|dist)\//.test(source)) errors.push(`${path}: private runtime import`);
  if (/<svg\b/.test(source)) errors.push(`${path}: inline icon outside shared library`);
}
if (errors.length) { console.error(errors.join('\n')); process.exitCode=1; }
else console.log('UI boundaries valid: shared semantic colors, public imports, shared icons.');
