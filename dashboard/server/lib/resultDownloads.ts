// Author: Max Stoddard
import fs from 'node:fs';
import path from 'node:path';
import { Readable } from 'node:stream';
import zlib from 'node:zlib';
import type { RuntimePathInput } from './runtimePaths';
import { resolveRuntimePaths } from './runtimePaths';

const TAR_BLOCK_SIZE = 512;
const SENSITIVITY_RESULTS_DIR = path.join('experiments', 'sensitivity');

interface ArchiveEntry {
  name: string;
  size: number;
  content: () => AsyncIterable<Buffer>;
  modifiedAt?: Date;
}

export interface ResultArchive {
  fileName: string;
  contentType: string;
  stream: Readable;
}

export interface RemoteArchiveObject {
  key: string;
  sizeBytes: number;
}

export interface RemoteArchiveInput {
  archiveRootName: string;
  fileName: string;
  prefix: string;
  objects: RemoteArchiveObject[];
  readObjectBytes: (key: string) => Promise<Buffer | null>;
}

function normalizeId(value: string, label: string): string {
  const normalized = value.trim();
  if (!normalized || normalized === '.' || normalized === '..' || normalized.includes('/') || normalized.includes('\\')) {
    throw new Error(`${label} must be a single path segment.`);
  }
  return normalized;
}

function sanitizeArchiveName(value: string): string {
  return value
    .trim()
    .replace(/[^A-Za-z0-9._=-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '') || 'results';
}

function ensureInside(root: string, candidate: string): void {
  const relative = path.relative(path.resolve(root), path.resolve(candidate));
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error('Resolved result path escapes the configured results root.');
  }
}

function ensureDirectory(root: string, candidate: string, label: string): void {
  ensureInside(root, candidate);
  if (!fs.existsSync(candidate) || !fs.statSync(candidate).isDirectory()) {
    throw new Error(`Unknown ${label}.`);
  }
}

function normalizeArchiveRelativePath(relativePath: string): string | null {
  const normalized = relativePath.replace(/\\/g, '/').replace(/^\/+/, '');
  if (!normalized || normalized.split('/').some((part) => part === '' || part === '.' || part === '..')) {
    return null;
  }
  return normalized;
}

function listLocalArchiveEntries(rootPath: string, archiveRootName: string): ArchiveEntry[] {
  const entries: ArchiveEntry[] = [];
  const stack = [''];

  while (stack.length > 0) {
    const relativeDir = stack.pop() as string;
    const absoluteDir = path.join(rootPath, relativeDir);
    for (const dirent of fs.readdirSync(absoluteDir, { withFileTypes: true })) {
      const relativePath = path.join(relativeDir, dirent.name);
      const absolutePath = path.join(rootPath, relativePath);
      const stats = fs.lstatSync(absolutePath);
      if (stats.isSymbolicLink()) {
        continue;
      }
      if (stats.isDirectory()) {
        stack.push(relativePath);
        continue;
      }
      if (!stats.isFile()) {
        continue;
      }

      const archiveRelativePath = normalizeArchiveRelativePath(relativePath);
      if (!archiveRelativePath) {
        continue;
      }
      entries.push({
        name: `${archiveRootName}/${archiveRelativePath}`,
        size: stats.size,
        modifiedAt: stats.mtime,
        content: async function* () {
          for await (const chunk of fs.createReadStream(absolutePath)) {
            yield Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
          }
        }
      });
    }
  }

  entries.sort((left, right) => left.name.localeCompare(right.name));
  return entries;
}

function writeOctal(buffer: Buffer, value: number, offset: number, length: number): void {
  const octal = Math.trunc(value).toString(8).padStart(length - 1, '0').slice(-(length - 1));
  buffer.write(octal, offset, length - 1, 'ascii');
  buffer[offset + length - 1] = 0;
}

function splitTarName(name: string): { name: string; prefix: string } {
  const normalized = name.replace(/\\/g, '/');
  if (Buffer.byteLength(normalized) <= 100) {
    return { name: normalized, prefix: '' };
  }

  const parts = normalized.split('/');
  for (let index = 1; index < parts.length; index += 1) {
    const candidatePrefix = parts.slice(0, index).join('/');
    const candidateName = parts.slice(index).join('/');
    if (Buffer.byteLength(candidatePrefix) <= 155 && Buffer.byteLength(candidateName) <= 100) {
      return { name: candidateName, prefix: candidatePrefix };
    }
  }

  throw new Error(`Archive path is too long for ustar header: ${normalized}`);
}

function createTarHeader(entry: ArchiveEntry): Buffer {
  const header = Buffer.alloc(TAR_BLOCK_SIZE, 0);
  const splitName = splitTarName(entry.name);
  header.write(splitName.name, 0, 100, 'utf-8');
  writeOctal(header, 0o644, 100, 8);
  writeOctal(header, 0, 108, 8);
  writeOctal(header, 0, 116, 8);
  writeOctal(header, entry.size, 124, 12);
  writeOctal(header, Math.floor((entry.modifiedAt ?? new Date()).getTime() / 1000), 136, 12);
  header.fill(0x20, 148, 156);
  header[156] = '0'.charCodeAt(0);
  header.write('ustar', 257, 6, 'ascii');
  header.write('00', 263, 2, 'ascii');
  if (splitName.prefix) {
    header.write(splitName.prefix, 345, 155, 'utf-8');
  }

  let checksum = 0;
  for (const byte of header) {
    checksum += byte;
  }
  const checksumText = checksum.toString(8).padStart(6, '0');
  header.write(checksumText, 148, 6, 'ascii');
  header[154] = 0;
  header[155] = 0x20;
  return header;
}

async function* buildTarStream(entries: ArchiveEntry[]): AsyncGenerator<Buffer> {
  for (const entry of entries) {
    yield createTarHeader(entry);
    let written = 0;
    for await (const chunk of entry.content()) {
      written += chunk.length;
      yield chunk;
    }
    if (written !== entry.size) {
      throw new Error(`Archive entry size changed while streaming: ${entry.name}`);
    }
    const remainder = entry.size % TAR_BLOCK_SIZE;
    if (remainder > 0) {
      yield Buffer.alloc(TAR_BLOCK_SIZE - remainder, 0);
    }
  }
  yield Buffer.alloc(TAR_BLOCK_SIZE * 2, 0);
}

function createArchive(fileName: string, entries: ArchiveEntry[]): ResultArchive {
  if (entries.length === 0) {
    throw new Error('No files are available to download for this result artifact.');
  }
  return {
    fileName,
    contentType: 'application/gzip',
    stream: Readable.from(buildTarStream(entries)).pipe(zlib.createGzip())
  };
}

export function createManualResultArchive(pathsInput: RuntimePathInput, runIdRaw: string): ResultArchive {
  const paths = resolveRuntimePaths(pathsInput);
  const runId = normalizeId(runIdRaw, 'runId');
  const runPath = path.join(paths.resultsRoot, runId);
  ensureDirectory(paths.resultsRoot, runPath, 'manual result run');
  const archiveRootName = sanitizeArchiveName(runId);
  return createArchive(`${archiveRootName}.tar.gz`, listLocalArchiveEntries(runPath, archiveRootName));
}

export function createSensitivityResultArchive(pathsInput: RuntimePathInput, experimentIdRaw: string): ResultArchive {
  const paths = resolveRuntimePaths(pathsInput);
  const experimentId = normalizeId(experimentIdRaw, 'experimentId');
  const sensitivityRoot = path.join(paths.resultsRoot, SENSITIVITY_RESULTS_DIR);
  const experimentPath = path.join(sensitivityRoot, experimentId);
  ensureDirectory(sensitivityRoot, experimentPath, 'sensitivity experiment');
  const archiveRootName = sanitizeArchiveName(experimentId);
  return createArchive(`${archiveRootName}.tar.gz`, listLocalArchiveEntries(experimentPath, archiveRootName));
}

export function createRemoteResultArchive(input: RemoteArchiveInput): ResultArchive {
  const archiveRootName = sanitizeArchiveName(input.archiveRootName);
  const prefix = input.prefix.endsWith('/') ? input.prefix : `${input.prefix}/`;
  const entries: ArchiveEntry[] = [];

  for (const object of input.objects) {
    if (!object.key.startsWith(prefix)) {
      continue;
    }
    const relativePath = normalizeArchiveRelativePath(object.key.slice(prefix.length));
    if (!relativePath) {
      continue;
    }
    entries.push({
      name: `${archiveRootName}/${relativePath}`,
      size: object.sizeBytes,
      content: async function* () {
        const bytes = await input.readObjectBytes(object.key);
        if (bytes === null) {
          throw new Error(`Remote artifact object disappeared while streaming: ${object.key}`);
        }
        yield bytes;
      }
    });
  }

  entries.sort((left, right) => left.name.localeCompare(right.name));

  return createArchive(input.fileName, entries);
}
