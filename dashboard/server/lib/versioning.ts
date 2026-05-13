import fs from 'node:fs';
import path from 'node:path';

export function parseVersionParts(version: string): number[] {
  const normalized = version
    .replace(/^v/i, '')
    .toLowerCase();
  const numberedSuffixMatch = normalized.match(/o(\d+)$/u);
  const suffixMatch = numberedSuffixMatch ? null : normalized.match(/o+$/u);
  const suffixRank = numberedSuffixMatch ? 2 + Number.parseInt(numberedSuffixMatch[1] ?? '0', 10) : suffixMatch?.[0].length ?? 0;
  const numeric = numberedSuffixMatch
    ? normalized.slice(0, numberedSuffixMatch.index ?? normalized.length)
    : suffixRank > 0
      ? normalized.slice(0, -suffixRank)
      : normalized;
  return numeric
    .split('.')
    .map((part) => Number.parseInt(part, 10))
    .concat(suffixRank);
}

export function compareVersions(a: string, b: string): number {
  const ap = parseVersionParts(a);
  const bp = parseVersionParts(b);
  const maxLen = Math.max(ap.length, bp.length);

  for (let i = 0; i < maxLen; i += 1) {
    const av = ap[i] ?? 0;
    const bv = bp[i] ?? 0;
    if (av !== bv) {
      return av - bv;
    }
  }

  if (ap.length !== bp.length) {
    return ap.length - bp.length;
  }

  return a.localeCompare(b);
}

export function listVersions(inputDataDir: string): string[] {
  return fs
    .readdirSync(inputDataDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => /^v\d+(?:\.\d+)*(?:o+|o\d+)?$/i.test(name))
    .filter((name) => name !== 'v1')
    .sort(compareVersions)
    .filter((name) => fs.existsSync(path.join(inputDataDir, name, 'config.properties')));
}
