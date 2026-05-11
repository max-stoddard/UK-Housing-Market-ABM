// Author: Max Stoddard
import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import type { RuntimePaths } from './runtimePaths';

export interface RuntimeDependencyResult {
  available: boolean;
  versionOutput: string;
  error?: string;
  vendor?: string | null;
  majorVersion?: number | null;
}

export interface RuntimePathDiagnostic {
  path: string;
  exists: boolean;
  writable?: boolean;
  error?: string;
}

export interface ModelArtifactDiagnostic {
  path: string | null;
  exists: boolean;
  sha256: string | null;
  error?: string;
}

export interface RuntimeDependencyStatus {
  java: RuntimeDependencyResult;
  maven: RuntimeDependencyResult;
  javaBin: string;
  mavenBin: string;
  modelArtifact: ModelArtifactDiagnostic;
  runtimePaths?: {
    mode: RuntimePaths['mode'];
    dataRoot: RuntimePathDiagnostic;
    resultsRoot: RuntimePathDiagnostic;
    tempRoot: RuntimePathDiagnostic;
    logsRoot: RuntimePathDiagnostic;
  };
}

export interface RuntimeDependencyOptions {
  runtimePaths?: RuntimePaths;
  javaBin?: string;
  mavenBin?: string;
  modelJar?: string | null;
}

function shouldUseShellForCommand(command: string): boolean {
  return process.platform === 'win32' && /\.(?:cmd|bat)$/i.test(command);
}

function runVersionCheck(command: string, args: string[]): RuntimeDependencyResult {
  const result = spawnSync(command, args, {
    encoding: 'utf-8',
    shell: shouldUseShellForCommand(command)
  });
  if (result.error) {
    return {
      available: false,
      versionOutput: '',
      error: result.error.message
    };
  }

  const combinedOutput = `${result.stdout ?? ''}\n${result.stderr ?? ''}`.trim();
  if (result.status !== 0) {
    return {
      available: false,
      versionOutput: combinedOutput,
      error: `Command exited with status ${result.status ?? 'unknown'}.`
    };
  }

  return {
    available: true,
    versionOutput: combinedOutput
  };
}

function defaultMavenWrapperBin(repoRoot?: string): string {
  const wrapperName = process.platform === 'win32' ? 'mvnw.cmd' : 'mvnw';
  return repoRoot ? path.join(repoRoot, wrapperName) : `.${path.sep}${wrapperName}`;
}

export function getConfiguredMavenBin(repoRoot?: string): string {
  return process.env.DASHBOARD_MAVEN_BIN?.trim() || defaultMavenWrapperBin(repoRoot);
}

export function getConfiguredJavaBin(): string {
  return process.env.DASHBOARD_JAVA_BIN?.trim() || process.env.DASHBOARD_PACKAGED_JAVA_EXE?.trim() || 'java';
}

export function getConfiguredModelJar(): string | null {
  return process.env.DASHBOARD_MODEL_JAR?.trim() || null;
}

export function parseJavaMajorVersion(versionOutput: string): number | null {
  const versionMatch = /version\s+"([^"]+)"/i.exec(versionOutput);
  const rawVersion = versionMatch?.[1] ?? '';
  if (!rawVersion) {
    return null;
  }
  if (rawVersion.startsWith('1.')) {
    const legacyMajor = Number.parseInt(rawVersion.split('.')[1] ?? '', 10);
    return Number.isFinite(legacyMajor) ? legacyMajor : null;
  }
  const major = Number.parseInt(rawVersion.split('.')[0] ?? '', 10);
  return Number.isFinite(major) ? major : null;
}

function parseJavaVendor(versionOutput: string): string | null {
  const normalized = versionOutput.toLowerCase();
  if (normalized.includes('openjdk')) {
    return 'OpenJDK';
  }
  if (normalized.includes('oracle')) {
    return 'Oracle';
  }
  if (normalized.includes('temurin')) {
    return 'Eclipse Temurin';
  }
  if (versionOutput.trim()) {
    return versionOutput.split(/\r?\n/)[0]?.trim() || null;
  }
  return null;
}

export function checkJavaRuntime(javaBin = getConfiguredJavaBin()): RuntimeDependencyResult {
  const result = runVersionCheck(javaBin, ['-version']);
  return {
    ...result,
    vendor: result.available ? parseJavaVendor(result.versionOutput) : null,
    majorVersion: result.available ? parseJavaMajorVersion(result.versionOutput) : null
  };
}

function hashFileSha256(filePath: string): string | null {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return null;
  }
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function checkModelArtifact(modelJar: string | null): ModelArtifactDiagnostic {
  if (!modelJar) {
    return {
      path: null,
      exists: false,
      sha256: null,
      error: 'Model artifact path is not configured.'
    };
  }

  const sha256 = hashFileSha256(modelJar);
  return {
    path: modelJar,
    exists: Boolean(sha256),
    sha256,
    ...(sha256 ? {} : { error: `Model artifact is missing or unreadable: ${modelJar}` })
  };
}

function checkPathExists(root: string): RuntimePathDiagnostic {
  if (!fs.existsSync(root)) {
    return {
      path: root,
      exists: false,
      error: `Path does not exist: ${root}`
    };
  }

  return {
    path: root,
    exists: true
  };
}

function nearestExistingParent(root: string): string | null {
  let current = path.resolve(root);
  while (!fs.existsSync(current)) {
    const parent = path.dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
  return current;
}

function checkWritableRoot(root: string): RuntimePathDiagnostic {
  const exists = fs.existsSync(root);
  const directoryToProbe = exists ? root : nearestExistingParent(root);
  if (!directoryToProbe) {
    return {
      path: root,
      exists,
      writable: false,
      error: `No existing parent directory is available for writability check: ${root}`
    };
  }

  try {
    const probePath = path.join(directoryToProbe, `.dashboard-writable-check-${process.pid}-${Date.now()}`);
    fs.writeFileSync(probePath, 'ok', 'utf-8');
    fs.rmSync(probePath, { force: true });
    return {
      path: root,
      exists,
      writable: true,
      ...(exists ? {} : { error: `Path does not exist yet; existing parent is writable: ${directoryToProbe}` })
    };
  } catch (error) {
    return {
      path: root,
      exists,
      writable: false,
      error: `Path is not writable: ${(error as Error).message}`
    };
  }
}

function checkRuntimePaths(runtimePaths: RuntimePaths): RuntimeDependencyStatus['runtimePaths'] {
  return {
    mode: runtimePaths.mode,
    dataRoot: checkPathExists(runtimePaths.dataRoot),
    resultsRoot: checkWritableRoot(runtimePaths.resultsRoot),
    tempRoot: checkWritableRoot(runtimePaths.tempRoot),
    logsRoot: checkWritableRoot(runtimePaths.logsRoot)
  };
}

export function checkRuntimeDependencies(options: RuntimeDependencyOptions | string = {}): RuntimeDependencyStatus {
  const normalizedOptions = typeof options === 'string' ? { mavenBin: options } : options;
  const javaBin = normalizedOptions.javaBin ?? getConfiguredJavaBin();
  const mavenBin = normalizedOptions.mavenBin ?? getConfiguredMavenBin(normalizedOptions.runtimePaths?.repoRoot);
  const modelJar = normalizedOptions.modelJar ?? getConfiguredModelJar();
  return {
    java: checkJavaRuntime(javaBin),
    maven: runVersionCheck(mavenBin, ['-v']),
    javaBin,
    mavenBin,
    modelArtifact: checkModelArtifact(modelJar),
    ...(normalizedOptions.runtimePaths ? { runtimePaths: checkRuntimePaths(normalizedOptions.runtimePaths) } : {})
  };
}
