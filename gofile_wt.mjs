"use strict";

import vm from "node:vm";

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const payload = JSON.parse(input);
  const context = vm.createContext(Object.create(null), {
    codeGeneration: { strings: false, wasm: false },
  });
  vm.runInContext(
    `globalThis.navigator = Object.freeze({userAgent:${JSON.stringify(String(payload.userAgent))},language:${JSON.stringify(String(payload.language))}});`,
    context,
    { timeout: 2_000 },
  );
  vm.runInContext(String(payload.script), context, { timeout: 2_000 });
  const result = vm.runInContext(
    `typeof generateWT === "function" ? String(generateWT(${JSON.stringify(String(payload.token))})) : null`,
    context,
    { timeout: 2_000 },
  );
  if (result === null) throw new Error("generateWT is unavailable");
  process.stdout.write(result);
});
