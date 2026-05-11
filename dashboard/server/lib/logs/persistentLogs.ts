// Author: Max Stoddard
import fs from 'node:fs';
import path from 'node:path';

export type PersistentLogCategory = 'app' | 'server' | 'model';

export interface RotatingLogOptions {
  maxBytes?: number;
  maxFiles?: number;
}

export interface RotatingLogWriter {
  filePath: string;
  writeLine: (line: string) => void;
}

export interface PersistentLoggers {
  app: RotatingLogWriter;
  server: RotatingLogWriter;
  model: RotatingLogWriter;
}

export const DEFAULT_ROTATING_LOG_MAX_BYTES = 5 * 1024 * 1024;
export const DEFAULT_ROTATING_LOG_MAX_FILES = 5;

function coercePositiveInteger(value: number | undefined, fallback: number): number {
  if (!Number.isFinite(value as number)) {
    return fallback;
  }
  const integer = Math.trunc(value as number);
  return integer > 0 ? integer : fallback;
}

function rotatedPath(filePath: string, index: number): string {
  return `${filePath}.${index}`;
}

function rotateFiles(filePath: string, maxFiles: number): void {
  if (maxFiles <= 1) {
    fs.rmSync(filePath, { force: true });
    return;
  }

  const oldestPath = rotatedPath(filePath, maxFiles - 1);
  fs.rmSync(oldestPath, { force: true });

  for (let index = maxFiles - 1; index >= 1; index -= 1) {
    const sourcePath = index === 1 ? filePath : rotatedPath(filePath, index - 1);
    if (!fs.existsSync(sourcePath)) {
      continue;
    }
    fs.renameSync(sourcePath, rotatedPath(filePath, index));
  }
}

function normalizeLogLines(line: string): string[] {
  const lines = line.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  return lines.length === 0 ? [''] : lines;
}

export function createRotatingLogWriter(
  logsRoot: string,
  category: PersistentLogCategory,
  options: RotatingLogOptions = {}
): RotatingLogWriter {
  const maxBytes = coercePositiveInteger(options.maxBytes, DEFAULT_ROTATING_LOG_MAX_BYTES);
  const maxFiles = coercePositiveInteger(options.maxFiles, DEFAULT_ROTATING_LOG_MAX_FILES);
  const filePath = path.join(logsRoot, `${category}.log`);

  fs.mkdirSync(logsRoot, { recursive: true });

  const writeLine = (line: string): void => {
    for (const normalizedLine of normalizeLogLines(line)) {
      const payload = `${new Date().toISOString()} ${normalizedLine}\n`;
      const payloadBytes = Buffer.byteLength(payload, 'utf-8');
      const currentBytes = fs.existsSync(filePath) ? fs.statSync(filePath).size : 0;
      if (currentBytes > 0 && currentBytes + payloadBytes > maxBytes) {
        rotateFiles(filePath, maxFiles);
      }
      fs.appendFileSync(filePath, payload, 'utf-8');
    }
  };

  return {
    filePath,
    writeLine
  };
}

export function createPersistentLoggers(logsRoot: string, options: RotatingLogOptions = {}): PersistentLoggers {
  return {
    app: createRotatingLogWriter(logsRoot, 'app', options),
    server: createRotatingLogWriter(logsRoot, 'server', options),
    model: createRotatingLogWriter(logsRoot, 'model', options)
  };
}
