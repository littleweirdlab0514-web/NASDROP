import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

const root = new URL('../chrome-extension/', import.meta.url);

test('Chrome extension is a least-privilege Manifest V3 package', async () => {
  const manifest = JSON.parse(await readFile(new URL('manifest.json', root), 'utf8'));
  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.background.service_worker, 'background.js');
  assert.deepEqual(manifest.optional_host_permissions, ['http://*/*', 'https://*/*']);
  assert.ok(!manifest.permissions.includes('<all_urls>'));
  assert.ok(!manifest.permissions.includes('tabs'));
});

test('Chrome extension does not persist passwords', async () => {
  const background = await readFile(new URL('background.js', root), 'utf8');
  assert.doesNotMatch(background, /storage\.local\.set\([^)]*password/s);
  assert.match(background, /\/api\/inspect/);
  assert.match(background, /\/api\/start/);
});

test('popup avoids inline scripts and requests origin permission interactively', async () => {
  const html = await readFile(new URL('popup.html', root), 'utf8');
  const script = await readFile(new URL('popup.js', root), 'utf8');
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)/i);
  assert.match(script, /chrome\.permissions\.request/);
  assert.match(script, /function supportedProvider/);
  assert.match(script, /useCurrentTab\(false\)/);
});
