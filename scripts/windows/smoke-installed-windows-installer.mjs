#!/usr/bin/env node
// Author: Max Stoddard
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..', '..');
const dashboardRoot = path.join(repoRoot, 'dashboard');
const defaultInstallerRoot = path.join(dashboardRoot, 'release', 'windows', 'installer');
const packageJson = JSON.parse(fs.readFileSync(path.join(dashboardRoot, 'package.json'), 'utf-8'));
const productName = 'UK Housing Model';
const defaultTimeoutMs = 300_000;

function usage() {
  return `Usage: node scripts/windows/smoke-installed-windows-installer.mjs [options]

Options:
  --installer <path>      Installer EXE path. Defaults to the Phase 11 installer artifact.
  --timeout-ms <number>   Per-process timeout. Defaults to ${defaultTimeoutMs}.
  --help                  Show this help.
`;
}

function parseArgs(argv) {
  const options = {
    installerPath: path.join(defaultInstallerRoot, `UK-Housing-Model-${packageJson.version}-Setup.exe`),
    timeoutMs: defaultTimeoutMs
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      console.log(usage());
      process.exit(0);
    }
    if (arg === '--installer') {
      const value = argv[i + 1];
      if (!value) {
        throw new Error('--installer requires a path.');
      }
      options.installerPath = path.resolve(process.cwd(), value);
      i += 1;
      continue;
    }
    if (arg === '--timeout-ms') {
      const value = Number.parseInt(argv[i + 1] ?? '', 10);
      if (!Number.isFinite(value) || value <= 0) {
        throw new Error('--timeout-ms requires a positive integer.');
      }
      options.timeoutMs = value;
      i += 1;
      continue;
    }
    throw new Error(`Unknown option: ${arg}`);
  }

  return options;
}

function log(message) {
  console.log(`[installed-installer-smoke] ${message}`);
}

function assertFile(filePath, label) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    throw new Error(`Missing ${label}: ${filePath}`);
  }
}

function sanitizedWindowsPath() {
  const systemRoot = process.env.SystemRoot ?? 'C:\\Windows';
  return [
    path.join(systemRoot, 'System32'),
    systemRoot
  ].join(path.delimiter);
}

function runChecked(command, args, options) {
  const result = spawnSync(command, args, {
    ...options,
    encoding: 'utf-8',
    windowsHide: true
  });
  if (result.error) {
    if (result.error.code === 'ETIMEDOUT') {
      throw new Error(`${command} ${args.join(' ')} timed out after ${options.timeout}ms.`);
    }
    throw new Error(`${command} failed to start: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error(
      `${command} ${args.join(' ')} exited with status ${result.status ?? 'unknown'}.\n` +
        `STDOUT:\n${result.stdout ?? ''}\nSTDERR:\n${result.stderr ?? ''}`
    );
  }
  return result;
}

function installedExeCandidates() {
  const localAppData = process.env.LOCALAPPDATA;
  const appData = process.env.APPDATA;
  const installDirectoryNames = Array.from(new Set([productName, packageJson.name].filter(Boolean)));
  const candidates = [];
  if (localAppData) {
    installDirectoryNames.forEach((directoryName) => {
      candidates.push(path.join(localAppData, 'Programs', directoryName, `${productName}.exe`));
    });
  }
  if (appData) {
    installDirectoryNames.forEach((directoryName) => {
      candidates.push(path.join(appData, directoryName, `${productName}.exe`));
    });
  }
  return candidates;
}

function findInstalledExe() {
  return installedExeCandidates().find((candidate) => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
}

function userDataRoot() {
  const appData = process.env.APPDATA;
  if (!appData) {
    throw new Error('APPDATA is not set; cannot locate Electron userData.');
  }
  return path.join(appData, productName);
}

function smokeLaunch(installedExe, timeoutMs) {
  const env = {
    ...process.env,
    PATH: sanitizedWindowsPath(),
    DASHBOARD_DESKTOP_SMOKE_QUIT_AFTER_LOAD: 'true'
  };
  delete env.ELECTRON_RUN_AS_NODE;
  runChecked(installedExe, ['--no-sandbox', '--disable-gpu'], {
    env,
    timeout: timeoutMs
  });
}

function assertPersistentLogs() {
  const logsRoot = path.join(userDataRoot(), 'logs');
  const appLog = path.join(logsRoot, 'app.log');
  const serverLog = path.join(logsRoot, 'server.log');
  assertFile(appLog, 'installed app log');
  assertFile(serverLog, 'installed server log');
  const appLogText = fs.readFileSync(appLog, 'utf-8');
  const serverLogText = fs.readFileSync(serverLog, 'utf-8');
  if (!appLogText.includes('[lifecycle] dashboard server listening')) {
    throw new Error(`Installed app log does not show a desktop server launch: ${appLog}`);
  }
  if (!serverLogText.includes('[runtime-paths] mode=desktop')) {
    throw new Error(`Installed server log does not show desktop runtime paths: ${serverLog}`);
  }
}

function main() {
  if (process.platform !== 'win32') {
    log(`skipping installed-app smoke on ${os.platform()}; this check must run on Windows.`);
    return;
  }

  const options = parseArgs(process.argv.slice(2));
  assertFile(options.installerPath, 'Windows installer');
  log(`installing ${options.installerPath}`);
  runChecked(options.installerPath, ['/S'], { timeout: options.timeoutMs });

  const installedExe = findInstalledExe();
  if (!installedExe) {
    throw new Error(`Could not find installed ${productName}. Checked: ${installedExeCandidates().join(', ')}`);
  }
  if (!installedExe.includes(' ')) {
    throw new Error(`Installed app path should contain spaces for Phase 11 validation: ${installedExe}`);
  }

  log(`launching installed app from ${installedExe}`);
  smokeLaunch(installedExe, options.timeoutMs);
  smokeLaunch(installedExe, options.timeoutMs);
  assertPersistentLogs();
  log(`installed app launched twice with persistent logs under ${userDataRoot()}`);
}

try {
  main();
} catch (error) {
  console.error(`[installed-installer-smoke] ${(error instanceof Error ? error.message : String(error))}`);
  process.exitCode = 1;
}
