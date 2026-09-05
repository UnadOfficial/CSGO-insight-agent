import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { runtimeManifestStatus } from "./runtime-fingerprint.mjs";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const pythonDir = join(repoRoot, "python");
const pythonExe = join(pythonDir, "python.exe");
const portablePs1 = join(repoRoot, "packaging", "windows", "package_portable.ps1");

if (process.env.CS2_INSIGHT_SKIP_PYTHON_STAGE === "1") {
  console.log("[desktop] CS2_INSIGHT_SKIP_PYTHON_STAGE=1 — skip Python staging");
  process.exit(0);
}

if (process.platform !== "win32") {
  if (!existsSync(pythonExe)) {
    console.error("[desktop] Non-Windows builds require a prepared python/python.exe runtime.");
    process.exit(1);
  }
  process.exit(0);
}

const customPython = process.env.CS2_INSIGHT_PORTABLE_PYTHON_DIR?.trim();
if (!existsSync(portablePs1)) {
  console.error(`[desktop] missing Python staging script: ${portablePs1}`);
  process.exit(1);
}

if (existsSync(pythonExe) && process.env.CS2_INSIGHT_REFRESH_PYTHON !== "1") {
  const manifest = runtimeManifestStatus(repoRoot, pythonDir);
  if (!manifest.valid) {
    console.error(
      `[desktop] existing Python runtime is stale (${manifest.reason}); rebuild with ` +
      "CS2_INSIGHT_REFRESH_PYTHON=1.",
    );
    process.exit(1);
  }
  const backendDir = join(repoRoot, "backend");
  // demoparser gate + skin-core IPC deps (cryptography). Stale python/ after
  // pyproject bumps otherwise ships and crashes at backend import.
  const verification = spawnSync(
    pythonExe,
    [
      "-c",
      [
        "import sys",
        "sys.path.insert(0, sys.argv[1])",
        // Keep this command comment-free: the statements are joined onto one
        // Python line, so an inline `#` would hide every validation after it.
        "import cryptography",
        "from app.demoparser_runtime import main",
        "raise SystemExit(main())",
      ].join("; "),
      backendDir,
    ],
    { cwd: repoRoot, env: process.env, stdio: "inherit", shell: false },
  );
  if (verification.status !== 0) {
    console.error(
      "[desktop] existing Python runtime is incompatible; rebuild with " +
      "CS2_INSIGHT_REFRESH_PYTHON=1 after building tools/csgo-demo-extract.",
    );
    process.exit(verification.status ?? 1);
  }
  console.log("[desktop] using verified python/python.exe");
  process.exit(0);
}

const args = [
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-File",
  portablePs1,
  "-ElectronStagePythonOnly",
];
if (customPython) {
  args.push("-PortablePythonDir", customPython);
}

const result = spawnSync("powershell.exe", args, {
  cwd: repoRoot,
  env: process.env,
  stdio: "inherit",
});
if (result.status !== 0) process.exit(result.status ?? 1);

if (!existsSync(pythonExe)) {
  console.error("[desktop] Python staging completed without python/python.exe");
  process.exit(1);
}

const stagedManifest = runtimeManifestStatus(repoRoot, pythonDir);
if (!stagedManifest.valid) {
  console.error(`[desktop] Python staging completed with a stale runtime manifest (${stagedManifest.reason})`);
  process.exit(1);
}
