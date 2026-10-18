import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

const root = new URL('../chrome-extension/', import.meta.url);

test('Chrome extension is a least-privilege Manifest V3 package', async () => {
  const manifest = JSON.parse(await readFile(new URL('manifest.json', root), 'utf8'));
  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.minimum_chrome_version, '111');
  assert.equal(manifest.background.service_worker, 'background.js');
  assert.deepEqual(manifest.optional_host_permissions, ['http://*/*', 'https://*/*']);
  assert.ok(!manifest.permissions.includes('<all_urls>'));
  assert.ok(!manifest.permissions.includes('tabs'));
  const mainWorld=manifest.content_scripts.find(script=>script.world==='MAIN');
  assert.deepEqual(mainWorld.matches,['https://x-share.net/s/*']);
  assert.deepEqual(mainWorld.js,['xshare-main.js']);
  assert.equal(mainWorld.run_at,'document_start');
});

test('Chrome extension does not persist passwords', async () => {
  const background = await readFile(new URL('background.js', root), 'utf8');
  assert.doesNotMatch(background, /storage\.local\.set\([^)]*password/s);
  assert.doesNotMatch(background, /storage\.(?:local|session)\.set\([^)]*download(?:_key|Key)/s);
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

test('popup uses the bundled official Buy Me a Coffee banner as an accessible external link', async () => {
  const [html, script, asset, notices] = await Promise.all([
    readFile(new URL('popup.html', root), 'utf8'),
    readFile(new URL('popup.js', root), 'utf8'),
    readFile(new URL('buy-me-a-coffee.png', root)),
    readFile(new URL('../THIRD_PARTY_NOTICES.md', root), 'utf8'),
  ]);
  assert.match(html, /href="https:\/\/buymeacoffee\.com\/littleweirdlab0514" target="_blank" rel="noopener noreferrer"/);
  assert.match(html, /<img src="buy-me-a-coffee\.png" width="217" height="61" alt="">/);
  assert.match(script, /Buy Me a Coffee에서 NASDrop 후원하기/);
  assert.match(script, /setAttribute\('aria-label',automatic\[3\]\)/);
  assert.equal(createHash('sha256').update(asset).digest('hex'), 'a72341bd3e0d51568e4c621bfb4bd315f6e71cf39fd3e71f7daf4a93f00425a7');
  assert.match(notices, /chrome-extension\/buy-me-a-coffee\.png/);
});
