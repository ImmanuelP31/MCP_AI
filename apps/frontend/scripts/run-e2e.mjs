/* global fetch */

import { spawn } from "node:child_process";
import process from "node:process";
import { setTimeout as delay } from "node:timers/promises";

const preview = spawn(
  process.execPath,
  ["./node_modules/vite/bin/vite.js", "preview", "--host", "127.0.0.1", "--port", "4173"],
  { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] },
);

const previewOutput = [];
const remember = (chunk) => {
  previewOutput.push(chunk.toString());
  if (previewOutput.length > 80) previewOutput.shift();
};
preview.stdout.on("data", remember);
preview.stderr.on("data", remember);

async function waitForPreview() {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      // Node 18+ exposes fetch globally; the project runtime is Node 22.
      const response = await fetch("http://127.0.0.1:4173/login");
      if (response.ok) return;
    } catch {
      await delay(500);
    }
  }
  throw new Error(`Vite preview did not become ready:\n${previewOutput.join("")}`);
}

function runPlaywright() {
  return new Promise((resolve) => {
    const child = spawn(
      process.execPath,
      ["./node_modules/playwright/cli.js", "test"],
      { cwd: process.cwd(), stdio: "inherit" },
    );
    child.on("exit", (code) => resolve(code ?? 1));
  });
}

function stopPreview() {
  if (!preview.pid || preview.killed) return Promise.resolve();
  if (process.platform !== "win32") {
    preview.kill("SIGTERM");
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const killer = spawn("taskkill", ["/pid", String(preview.pid), "/T", "/F"], {
      stdio: "ignore",
    });
    killer.on("exit", () => resolve());
    killer.on("error", () => resolve());
  });
}

let exitCode = 1;
try {
  await waitForPreview();
  exitCode = await runPlaywright();
} finally {
  await stopPreview();
}
process.exit(exitCode);
