#!/usr/bin/env node
// Author: Max Stoddard
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..', '..');
const dashboardRoot = path.join(repoRoot, 'dashboard');
const defaultResourcesRoot = path.join(dashboardRoot, 'release', 'windows', 'resources');

function parseArgs(argv) {
  const options = {
    resourcesRoot: defaultResourcesRoot,
    timeoutMs: 30_000
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--resources-root') {
      const value = argv[i + 1];
      if (!value) {
        throw new Error('--resources-root requires a path.');
      }
      options.resourcesRoot = path.resolve(process.cwd(), value);
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

function assertFile(filePath, label) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    throw new Error(`Missing ${label}: ${filePath}`);
  }
}

function assertDirectory(dirPath, label) {
  if (!fs.existsSync(dirPath) || !fs.statSync(dirPath).isDirectory()) {
    throw new Error(`Missing ${label}: ${dirPath}`);
  }
}

function npmCommand() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm';
}

function runElectronSmoke(options) {
  assertFile(path.join(options.resourcesRoot, 'release-manifest.json'), 'release manifest');
  assertDirectory(path.join(options.resourcesRoot, 'release-data', 'input-data-versions'), 'release-data root');
  assertDirectory(path.join(options.resourcesRoot, 'java', 'bin'), 'staged Java bin directory');
  assertFile(
    path.join(options.resourcesRoot, 'model', 'housing-model-1.0-SNAPSHOT-windows-release.jar'),
    'staged model jar'
  );

  const env = {
    ...process.env,
    DASHBOARD_APP_RESOURCES_ROOT: options.resourcesRoot,
    DASHBOARD_DESKTOP_SMOKE_QUIT_AFTER_LOAD: 'true'
  };
  delete env.ELECTRON_RUN_AS_NODE;

  return new Promise((resolve, reject) => {
    const child = spawn(
      npmCommand(),
      ['--prefix', 'electron', 'run', 'dev', '--', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
      {
        cwd: dashboardRoot,
        env,
        stdio: 'inherit',
        shell: process.platform === 'win32'
      }
    );
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error(`Electron desktop release-resource smoke timed out after ${options.timeoutMs}ms.`));
    }, options.timeoutMs);

    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`Electron desktop release-resource smoke failed with code ${code} signal ${signal ?? 'none'}.`));
    });
  });
}

try {
  const options = parseArgs(process.argv.slice(2));
  await runElectronSmoke(options);
  console.log(`[desktop-release-smoke] passed with resources root ${options.resourcesRoot}`);
} catch (error) {
  console.error(`[desktop-release-smoke] ${(error instanceof Error ? error.message : String(error))}`);
  process.exitCode = 1;
}
