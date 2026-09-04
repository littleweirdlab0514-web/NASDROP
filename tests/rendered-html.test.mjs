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
  assert.doesNotMatch(html, /qrcode\.js/);
  assert.match(html, /href="https:\/\/github\.com\/sponsors\/littleweirdlab0514-web"/);
  assert.match(html, /target="_blank" rel="noopener noreferrer"/);
  assert.ok(html.indexOf("account-card") < html.indexOf("sponsor-card"));
  assert.ok(html.indexOf("sponsor-card") < html.indexOf("download-behavior-card"));
  assert.match(html, /folder-card[^]*id="setting-target"[^]*id="service-user"/);
  for (const key of ["username", "password", "accountHint", "currentPassword", "newPassword", "confirmPassword", "saveAccount", "resetAccount", "resetAccountHint", "accountSaved", "logout", "sponsorTitle", "sponsorHint", "sponsorAction", "accessMethodHint", "currentAccessAddress", "launcherAddress", "launcherPort", "launcherPortHint", "connectionRouteTitle", "connectionRoute", "connectionRouteHint", "saveLauncherPort", "launcherPortSaved", "reverseProxyMode", "reverseProxyHint", "proxyDetectedTitle", "proxyDetectedWarning", "proxyEnabledWarning", "confirmReverseProxy", "saveConnectionSettings", "connectionSettingsSaved", "downloadMethod", "singleMode", "segmentedMode", "singleModeWarning", "saveDownloadMethod", "downloadBehavior", "downloadBehaviorHint", "combinedDownloadWarning", "saveDownloadBehavior", "downloadBehaviorSaved", "processingTitle", "temporaryFolder", "archiveEngine", "autoExtract", "diskProtection", "extractThisJob", "archivePassword", "retryExtraction", "httpWarningTitle", "httpWarningBody", "error_auth_required", "error_invalid_credentials", "error_invalid_username", "error_invalid_password", "error_too_many_attempts", "error_permission_denied", "error_password_required", "error_rate_limited", "error_link_expired", "error_integrity_failed", "error_archive_error", "error_invalid_link", "error_invalid_job_state", "error_internal_error", "error_generic_error"]) {
    assert.equal((i18n.match(new RegExp(`\\b${key}:`, "g")) || []).length, 4);
  }
  assert.match(i18n, /function error\(code, fallback/);
  assert.match(app, /serverError\(payload\.code/);
  assert.match(app, /payload\.params/);
  assert.match(app, /serverError\(job\.error_code, job\.error\)/);
  assert.match(html, /data-i18n="accessMethodHint"/);
  assert.match(html, /id="launcher-port"[^>]*min="1"[^>]*max="65535"/);
  assert.match(html, /id="save-service-settings"/);
  assert.match(html, /id="reverse-proxy-mode"/);
  assert.match(html, /id="proxy-detected-warning"[^>]*role="alert"/);
  assert.match(app, /launcher_port:port,reverse_proxy_mode:reverseProxyMode/);
  assert.match(app, /connectionRoute.*publicPort:port.*appPort:8791/);
  assert.match(html, /id="download-mode"/);
  assert.match(html, /value="segmented"/);
  assert.match(html, /value="single"/);
  assert.match(app, /download_mode:mode/);
  assert.match(html, /id="extract-download"/);
  assert.match(html, /id="archive-password"/);
  assert.match(html, /id="save-processing"/);
  assert.match(app, /auto_extract_archives:enabled,disk_protection:diskProtection/);
  assert.match(app, /location\.hash\.slice\(1\)/);
  assert.match(app, /history\.replaceState/);
  assert.match(html, /id="login-http-warning"[^>]*role="alert"/);
  assert.match(html, /id="app-http-warning"[^>]*role="alert"/);
  assert.match(app, /location\.protocol === "http:" && !isPrivateHost\(location\.hostname\)/);
  assert.match(app, /octets\[0\] === 192 && octets\[1\] === 168/);
  assert.match(html, /id="login-username"[^>]*autocomplete="username"/);
  assert.match(html, /id="login-password"[^>]*autocomplete="current-password"/);
  assert.match(html, /id="account-form"/);
  assert.match(app, /\/api\/login/);
  assert.match(app, /\/api\/account/);
  assert.doesNotMatch(app, /nas-download-token|\/api\/pairing|\/api\/token\/rotate/);
  assert.match(info, /description_enu=/);
  assert.match(info, /description_krn=/);
  assert.match(info, /description_jpn=/);
  assert.match(info, /description_chs=/);
  assert.match(uiConfig, /"title": "NASDrop"/);
  assert.doesNotMatch(uiConfig, /"title": "nasdrop:title"/);
  assert.match(uiConfig, /"texts": "texts"/);
  assert.match(uiConfig, /"allUsers": false/);
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

test("HTTP transport warning distinguishes public hosts from private NAS addresses", async () => {
  const app = await readFile(new URL("synology/web/app.js", root), "utf8");
  const start = app.indexOf("  function isPrivateHost(");
  const end = app.indexOf("  function renderTransportWarning()", start);
  assert.ok(start >= 0 && end > start);
  const context = {};
  vm.runInNewContext(`${app.slice(start, end)}\nthis.isPrivateHost = isPrivateHost;`, context);

  for (const host of ["localhost", "diskstation", "nas.local", "127.0.0.1", "10.0.0.2", "172.16.0.2", "172.31.255.254", "192.168.1.157", "169.254.10.2", "::1", "fd00::157", "fe80::1"]) {
    assert.equal(context.isPrivateHost(host), true, host);
  }
  for (const host of ["nas.example.com", "example.com", "172.15.0.2", "172.32.0.2", "192.169.1.1", "2001:db8::20"]) {
    assert.equal(context.isPrivateHost(host), false, host);
  }
});

test("client connection and Sponsor cards share the top row equally", async () => {
  const html = await readFile(new URL("synology/web/index.html", root), "utf8");
  const style = await readFile(new URL("synology/web/style.css", root), "utf8");
  assert.match(style, /grid-template-columns:repeat\(6,minmax\(0,1fr\)\)/);
  assert.match(style, /\.account-card\{grid-column:span 3\}/);
  assert.match(style, /\.download-behavior-card,\.processing-card,\.folder-card,\.service-card\{grid-column:span 3\}/);
  assert.match(style, /\.download-behavior-controls\{display:grid/);
  assert.doesNotMatch(html, /download-behavior-grid/);
  assert.match(style, /\.download-options\{display:grid;grid-template-columns:max-content minmax\(0,1fr\);align-items:center/);
  assert.match(style, /\.download-options \.password-setting\{display:grid;grid-template-columns:max-content minmax\(180px,360px\)/);
  assert.match(style, /@media\(max-width:760px\)[^]*\.settings-grid\{grid-template-columns:1fr\}/);
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

test("DSM launcher preserves the protocol used to open DSM", async () => {
  const html = await readFile(new URL("synology/package-inner/ui/launcher.html", root), "utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);

  function redirectFor(hostname, protocol) {
    let redirected = "";
    vm.runInNewContext(script, { location: { hostname, protocol, replace: value => { redirected = value; } } });
    return redirected;
  }

  assert.equal(redirectFor("192.168.1.20", "http:"), "http://192.168.1.20:8791/");
  assert.equal(redirectFor("diskstation", "https:"), "https://diskstation:8791/");
  assert.equal(redirectFor("nas.example.com", "http:"), "http://nas.example.com:8791/");
  assert.equal(redirectFor("nas.example.com", "https:"), "https://nas.example.com:8791/");
  assert.equal(redirectFor("[2001:db8::20]", "http:"), "http://[2001:db8::20]:8791/");
});

test("web UI exchanges DSM launcher handoffs instead of using them as API sessions", async () => {
  const app = await readFile(new URL("synology/web/app.js", root), "utf8");
  assert.match(app, /publicApi\("\/api\/launcher\/session"/);
  assert.doesNotMatch(app, /token:\s*launchedToken\s*\|\|/);
});
