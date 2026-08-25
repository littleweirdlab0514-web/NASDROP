"use strict";

import vm from "node:vm";

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const payload = JSON.parse(input);
  const sandbox = {
    navigator: {
      userAgent: String(payload.userAgent),
      language: String(payload.language),
    },
  };
  vm.createContext(sandbox, { codeGeneration: { strings: false, wasm: false } });
  vm.runInContext(payload.script, sandbox, { timeout: 2_000 });
  if (typeof sandbox.generateWT !== "function") throw new Error("generateWT is unavailable");
  process.stdout.write(String(sandbox.generateWT(payload.token)));
});
