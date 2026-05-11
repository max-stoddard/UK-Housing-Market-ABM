import fs from 'node:fs';
import path from 'node:path';
import { resolveRuntimePaths, type RuntimePathInput } from './runtimePaths';

export function parseConfigFile(configPath: string): Map<string, string> {
  const out = new Map<string, string>();
  const lines = fs.readFileSync(configPath, 'utf-8').split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    const match = /^([A-Z0-9_]+)\s*=\s*(.+)$/.exec(trimmed);
    if (!match) {
      continue;
    }

    const key = match[1];
    const raw = match[2].trim();
    const value = raw.replace(/^"|"$/g, '');
    out.set(key, value);
  }

  return out;
}

export function resolveVersionPath(pathsInput: RuntimePathInput, version: string): string {
  const paths = resolveRuntimePaths(pathsInput);
  return path.join(paths.dataRoot, version);
}

export function getConfigPath(pathsInput: RuntimePathInput, version: string): string {
  return path.join(resolveVersionPath(pathsInput, version), 'config.properties');
}

export function resolveConfigDataFilePath(
  pathsInput: RuntimePathInput,
  version: string,
  configValue: string
): string {
  const paths = resolveRuntimePaths(pathsInput);
  const fileName = path.basename(configValue);
  return path.join(paths.dataRoot, version, fileName);
}

export function readNumericCsvRows(filePath: string): number[][] {
  const rows: number[][] = [];
  const lines = fs.readFileSync(filePath, 'utf-8').split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    const values = trimmed.split(',').map((token) => token.trim());
    const numbers = values.map((token) => Number.parseFloat(token));

    if (numbers.some((value) => Number.isNaN(value))) {
      continue;
    }

    rows.push(numbers);
  }

  return rows;
}

export function getNumericConfigValue(config: Map<string, string>, key: string): number {
  const raw = config.get(key);
  if (raw === undefined) {
    throw new Error(`Missing config key: ${key}`);
  }
  const value = Number.parseFloat(raw);
  if (Number.isNaN(value)) {
    throw new Error(`Config key ${key} is not numeric: ${raw}`);
  }
  return value;
}
