// Author: Max Stoddard
import fs from 'node:fs';
import path from 'node:path';
import type { RuntimePaths } from './runtimePaths';

export interface DesktopSupportBundleOptions {
  runtimePaths: RuntimePaths;
  runtimeDiagnostics: unknown;
  generatedAt?: Date;
  maxLogBytes?: number;
}

export interface DesktopSupportBundleResult {
  bundlePath: string;
  files: string[];
}

const DEFAULT_MAX_LOG_BYTES = 256 * 1024;
const LOG_FILE_NAMES = ['app.log', 'server.log', 'model.log'] as const;

function timestampForPath(generatedAt: Date): string {
  return generatedAt.toISOString().replace(/[:.]/g, '-');
}

function requireElectronUserDataRoot(runtimePaths: RuntimePaths): string {
  if (runtimePaths.mode !== 'desktop' || !runtimePaths.electronUserDataRoot) {
    throw new Error('Support bundle export is only available in desktop runtime mode.');
  }
  return runtimePaths.electronUserDataRoot;
}

function writeJson(filePath: string, value: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

function readTailText(filePath: string, maxBytes: number): string {
  const stat = fs.statSync(filePath);
  const start = Math.max(0, stat.size - maxBytes);
  const length = stat.size - start;
  const file = fs.openSync(filePath, 'r');
  try {
    const buffer = Buffer.alloc(length);
    fs.readSync(file, buffer, 0, length, start);
    return buffer.toString('utf-8');
  } finally {
    fs.closeSync(file);
  }
}

function copyReleaseManifest(bundlePath: string, runtimePaths: RuntimePaths, files: string[]): void {
  const manifestPath = runtimePaths.appResourcesRoot
    ? path.join(runtimePaths.appResourcesRoot, 'release-manifest.json')
    : null;
  if (manifestPath && fs.existsSync(manifestPath) && fs.statSync(manifestPath).isFile()) {
    const targetPath = path.join(bundlePath, 'release-manifest.json');
    fs.copyFileSync(manifestPath, targetPath);
    files.push(path.relative(bundlePath, targetPath).replace(/\\/g, '/'));
    return;
  }

  const missingPath = path.join(bundlePath, 'release-manifest.missing.json');
  writeJson(missingPath, {
    error: 'release-manifest.json was not found.',
    expectedPath: manifestPath
  });
  files.push(path.relative(bundlePath, missingPath).replace(/\\/g, '/'));
}

function copyRecentLogs(bundlePath: string, runtimePaths: RuntimePaths, maxLogBytes: number, files: string[]): void {
  const logsTargetRoot = path.join(bundlePath, 'logs');
  fs.mkdirSync(logsTargetRoot, { recursive: true });

  for (const fileName of LOG_FILE_NAMES) {
    const sourcePath = path.join(runtimePaths.logsRoot, fileName);
    const targetPath = path.join(logsTargetRoot, fileName);
    if (fs.existsSync(sourcePath) && fs.statSync(sourcePath).isFile()) {
      fs.writeFileSync(targetPath, readTailText(sourcePath, maxLogBytes), 'utf-8');
    } else {
      fs.writeFileSync(targetPath, `Log file was not found: ${sourcePath}\n`, 'utf-8');
    }
    files.push(path.relative(bundlePath, targetPath).replace(/\\/g, '/'));
  }
}

export function exportDesktopSupportBundle(options: DesktopSupportBundleOptions): DesktopSupportBundleResult {
  const userDataRoot = requireElectronUserDataRoot(options.runtimePaths);
  const generatedAt = options.generatedAt ?? new Date();
  const maxLogBytes = Math.max(1, Math.trunc(options.maxLogBytes ?? DEFAULT_MAX_LOG_BYTES));
  const bundlePath = path.join(userDataRoot, 'support-bundles', `support-bundle-${timestampForPath(generatedAt)}`);
  const files: string[] = [];

  fs.mkdirSync(bundlePath, { recursive: true });

  const metadataPath = path.join(bundlePath, 'metadata.json');
  writeJson(metadataPath, {
    generatedAt: generatedAt.toISOString(),
    runtimeMode: options.runtimePaths.mode,
    appResourcesRoot: options.runtimePaths.appResourcesRoot ?? null,
    electronUserDataRoot: options.runtimePaths.electronUserDataRoot ?? null,
    dataRoot: options.runtimePaths.dataRoot,
    resultsRoot: options.runtimePaths.resultsRoot,
    logsRoot: options.runtimePaths.logsRoot
  });
  files.push(path.relative(bundlePath, metadataPath).replace(/\\/g, '/'));

  copyReleaseManifest(bundlePath, options.runtimePaths, files);

  const diagnosticsPath = path.join(bundlePath, 'runtime-diagnostics.json');
  writeJson(diagnosticsPath, options.runtimeDiagnostics);
  files.push(path.relative(bundlePath, diagnosticsPath).replace(/\\/g, '/'));

  copyRecentLogs(bundlePath, options.runtimePaths, maxLogBytes, files);

  return {
    bundlePath,
    files: files.sort((left, right) => left.localeCompare(right))
  };
}
