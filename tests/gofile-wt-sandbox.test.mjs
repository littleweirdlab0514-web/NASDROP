import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const helper = fileURLToPath(new URL("../gofile_wt.mjs", import.meta.url));

function execute(script) {
  const result = spawnSync(process.execPath, [helper], {
    encoding: "utf8",
    input: JSON.stringify({
      userAgent: "NASDrop test",
      language: "en",
      token: "token",
      script,
    }),
  });
  if (result.status !== 0) throw new Error(result.stderr || `GoFile helper exited with ${result.status}`);
  return result.stdout;
}

test("GoFile scripts retain context-local Date and Math support", () => {
  const stdout = execute(
    "function generateWT(token) { return token + ':' + Math.floor(1.9) + ':' + (Date.now() > 0); }",
  );
  assert.equal(stdout, "token:1:true");
});

test("GoFile scripts cannot escape through a host Date constructor", () => {
  assert.throws(
    () => execute('function generateWT() { return Date.constructor("return process.version")(); }'),
    /Code generation from strings disallowed|EvalError/,
  );
});
