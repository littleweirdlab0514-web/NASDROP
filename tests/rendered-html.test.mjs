import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const root = new URL("../", import.meta.url);

test("keeps local credentials and runtime state out of Git", async () => {
  const [ignore, example, backend] = await Promise.all([
    readFile(new URL(".gitignore", root), "utf8"),
    readFile(new URL("config.example.json", root), "utf8"),
    readFile(new URL("backend.py", root), "utf8"),
  ]);

  assert.match(ignore, /^runtime\/$/m);
  assert.doesNotMatch(example, /\/Users\/|192\.168\.1\.157|openclaw@/);
  assert.doesNotMatch(backend, /NAS_PORTAL_NAS_HOST|NAS_PORTAL_NAS_KEY|NAS_PORTAL_NAS_KNOWN_HOSTS/);
  assert.doesNotMatch(example, /NAS_PORTAL_EXISTING_TOKEN_FILE/);
  assert.doesNotMatch(backend, /NAS_PORTAL_EXISTING_TOKEN_FILE|NAS_PORTAL_FRONTEND|def proxy\(/);
  assert.doesNotMatch(backend, /StrictHostKeyChecking|UserKnownHostsFile|DIRECT_MODE/);
  assert.match(backend, /command = \["sh", "-s"\]/);
});

test("Synology UI defaults to English and supports Korean, Japanese, and Chinese", async () => {
  const [html, i18n, app, info, uiConfig] = await Promise.all([
    readFile(new URL("synology/web/index.html", root), "utf8"),
    readFile(new URL("synology/web/i18n.js", root), "utf8"),
    readFile(new URL("synology/web/app.js", root), "utf8"),
    readFile(new URL("synology/package/INFO", root), "utf8"),
    readFile(new URL("synology/package-inner/ui/config", root), "utf8"),
  ]);

  assert.match(html, /<html lang="en">/);
  assert.match(html, /data-language-select/);
  assert.match(html, /\/i18n\.js/);
  for (const language of ["en", "ko", "ja", "zh"]) assert.match(i18n, new RegExp(`\\b${language}: \\{`));
  assert.match(i18n, /navigator\.languages/);
  assert.match(i18n, /localStorage\.getItem\("nasdrop-language"\)/);
  assert.match(i18n, /return "en"/);
  assert.match(app, /NASDropI18n\.t/);
  const packageVersion = info.match(/^version="([0-9.]+)-[0-9]+"$/m)[1];
  assert.ok(html.includes(`/app.js?v=${packageVersion}`));
  assert.ok(html.includes(`/qrcode.js?v=${packageVersion}`));
  assert.match(html, /href="https:\/\/github\.com\/sponsors\/littleweirdlab0514-web"/);
  assert.match(html, /target="_blank" rel="noopener noreferrer"/);
  assert.ok(html.indexOf("pairing-card") < html.indexOf("sponsor-card"));
  assert.ok(html.indexOf("sponsor-card") < html.indexOf("concurrency-card"));
  assert.match(html, /folder-card[^]*id="setting-target"[^]*id="service-user"/);
  for (const key of ["sponsorTitle", "sponsorHint", "sponsorAction"]) {
    assert.equal((i18n.match(new RegExp(`\\b${key}:`, "g")) || []).length, 4);
  }
  assert.match(info, /description_enu=/);
  assert.match(info, /description_krn=/);
  assert.match(info, /description_jpn=/);
  assert.match(info, /description_chs=/);
  assert.match(uiConfig, /"title": "NASDrop"/);
  assert.match(uiConfig, /nasdrop:desc/);
  assert.match(uiConfig, /"preloadTexts": \["nasdrop:desc"\]/);
  for (const locale of ["enu", "krn", "jpn", "chs"]) {
    const strings = await readFile(new URL(`synology/package-inner/ui/texts/${locale}/strings`, root), "utf8");
    assert.match(strings, /\[nasdrop\]/);
    assert.match(strings, /desc=/);
  }
});

test("every Synology UI element referenced by app.js exists in index.html", async () => {
  const [html, app] = await Promise.all([
    readFile(new URL("synology/web/index.html", root), "utf8"),
    readFile(new URL("synology/web/app.js", root), "utf8"),
  ]);
  const ids = new Set([...html.matchAll(/\bid="([A-Za-z0-9_-]+)"/g)].map(match => match[1]));
  const selectors = new Set([...app.matchAll(/\$\("#([A-Za-z0-9_-]+)"\)/g)].map(match => match[1]));
  assert.deepEqual([...selectors].filter(id => !ids.has(id)), []);
});

test("static Synology UI responses cannot mix cached versions", async () => {
  const backend = await readFile(new URL("backend.py", root), "utf8");
  assert.match(backend, /self\.send_header\("cache-control", "no-store"\)/);
  assert.doesNotMatch(backend, /public, max-age/);
});

test("Synology language detection falls back to English and persists manual choice", async () => {
  const source = await readFile(new URL("synology/web/i18n.js", root), "utf8");
  const storage = new Map();
  const window = { dispatchEvent() {} };
  vm.runInNewContext(source, {
    window,
    navigator: { languages: ["fr-FR"], language: "fr-FR" },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    document: { documentElement: {}, querySelectorAll: () => [] },
    CustomEvent: class CustomEvent {},
  });

  assert.equal(window.NASDropI18n.language, "en");
  assert.equal(window.NASDropI18n.t("downloads"), "Downloads");
  window.NASDropI18n.setLanguage("ja");
  assert.equal(window.NASDropI18n.language, "ja");
  assert.equal(storage.get("nasdrop-language"), "ja");
  assert.equal(window.NASDropI18n.t("downloads"), "ダウンロード");
});

test("DSM launcher keeps LAN HTTP and external HTTPS on port 8791", async () => {
  const html = await readFile(new URL("synology/package-inner/ui/launcher.html", root), "utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);

  function redirectFor(hostname) {
    let redirected = "";
    vm.runInNewContext(script, { location: { hostname, replace: value => { redirected = value; } } });
    return redirected;
  }

  assert.equal(redirectFor("192.168.1.20"), "http://192.168.1.20:8791/");
  assert.equal(redirectFor("diskstation"), "http://diskstation:8791/");
  assert.equal(redirectFor("nas.example.com"), "https://nas.example.com:8791/");
  assert.equal(redirectFor("[2001:db8::20]"), "https://[2001:db8::20]:8791/");
});
