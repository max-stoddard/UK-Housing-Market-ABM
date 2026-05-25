// Author: Max Stoddard
export type VersionLabelKind = 'in_progress' | 'latest' | 'original';

export interface VersionLabelState {
  version: string;
  isInProgress: boolean;
  isLatest: boolean;
  isOriginal: boolean;
  kinds: VersionLabelKind[];
}

const RESULTS_RUN_VERSION_PATTERN = /^(v\d+(?:\.\d+)*(?:o+|o\d+)?)-output$/i;
const LEGACY_2011_VERSIONS = new Set(['v0', 'v0o', 'v0oo', 'v0o1', 'v0o2', 'v0o3', 'v0o6']);
const BEST_2024_VERSION = 'v4.4';
const FIRST_2024_VERSION = 'v1.0';
const LAST_PREFIXED_2024_VERSION = 'v4.18';

function parseVersionParts(version: string): number[] {
  const normalized = version.replace(/^v/i, '').toLowerCase();
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

function compareVersionIds(left: string, right: string): number {
  const leftParts = parseVersionParts(left);
  const rightParts = parseVersionParts(right);
  const maxLength = Math.max(leftParts.length, rightParts.length);

  for (let index = 0; index < maxLength; index += 1) {
    const leftPart = leftParts[index] ?? 0;
    const rightPart = rightParts[index] ?? 0;
    if (leftPart !== rightPart) {
      return leftPart - rightPart;
    }
  }

  if (leftParts.length !== rightParts.length) {
    return leftParts.length - rightParts.length;
  }

  return left.localeCompare(right);
}

function is2024PrefixedVersion(version: string): boolean {
  return compareVersionIds(version, FIRST_2024_VERSION) >= 0 && compareVersionIds(version, LAST_PREFIXED_2024_VERSION) <= 0;
}

export function getLatestStableVersion(versions: readonly string[], inProgressVersions: readonly string[]): string {
  const inProgressSet = new Set(inProgressVersions);
  for (let index = versions.length - 1; index >= 0; index -= 1) {
    const version = versions[index] ?? '';
    if (version && !inProgressSet.has(version)) {
      return version;
    }
  }
  return '';
}

export function buildVersionLabelState(
  version: string,
  latestStableVersion: string,
  inProgressVersions: ReadonlySet<string>
): VersionLabelState {
  const isInProgress = inProgressVersions.has(version);
  const isLatest = Boolean(version) && version === latestStableVersion && !isInProgress;
  const isOriginal = version === 'v0';
  const kinds: VersionLabelKind[] = [];

  if (isInProgress) {
    kinds.push('in_progress');
  }
  if (isLatest) {
    kinds.push('latest');
  }
  if (isOriginal) {
    kinds.push('original');
  }

  return {
    version,
    isInProgress,
    isLatest,
    isOriginal,
    kinds
  };
}

export function extractVersionFromResultsRunId(runId: string): string {
  const match = RESULTS_RUN_VERSION_PATTERN.exec(runId.trim());
  return match?.[1] ?? '';
}

export function buildResultsRunVersionLabelState(
  runId: string,
  versions: readonly string[],
  inProgressVersions: readonly string[]
): VersionLabelState | null {
  const version = extractVersionFromResultsRunId(runId);
  if (!version || versions.length === 0 || !versions.includes(version)) {
    return null;
  }

  return buildVersionLabelState(version, getLatestStableVersion(versions, inProgressVersions), new Set(inProgressVersions));
}

export function formatModelVersionBaseLabel(version: string, state?: Pick<VersionLabelState, 'isLatest'>): string {
  if (version === 'v0') {
    return 'Original 2011 model';
  }

  if (version === 'v0oo') {
    return 'Optimised 2011 model';
  }

  if (version === 'v0o2' || version === 'v0o3' || version === 'v0o6') {
    return 'Optimised 2011 model';
  }

  if (LEGACY_2011_VERSIONS.has(version)) {
    return version;
  }

  if (version === BEST_2024_VERSION) {
    return `Best 2024 model ${version}`;
  }

  if (state?.isLatest) {
    return `Latest 2024 model ${version}`;
  }

  if (is2024PrefixedVersion(version)) {
    return `2024 model ${version}`;
  }

  return version;
}

export function formatCalibrationVersionTitleLabel(version: string, state?: Pick<VersionLabelState, 'isLatest'>): string {
  if (version === 'v0') {
    return 'Original 2011 model';
  }

  if (version === 'v0oo') {
    return 'Optimised 2011 model';
  }

  if (version === 'v0o2' || version === 'v0o3' || version === 'v0o6') {
    return 'Optimised 2011 model';
  }

  if (version === BEST_2024_VERSION) {
    return 'Best 2024 model';
  }

  if (state?.isLatest) {
    return 'Latest 2024 model';
  }

  return formatModelVersionBaseLabel(version, state);
}

function formatKind(kind: VersionLabelKind): string {
  switch (kind) {
    case 'in_progress':
      return 'In progress';
    case 'latest':
      return 'Latest';
    case 'original':
      return 'Original';
  }
}

export function formatVersionOptionLabel(version: string, state: VersionLabelState): string {
  const baseLabel = formatModelVersionBaseLabel(version, state);
  if (state.kinds.length === 0) {
    return baseLabel;
  }
  return `${baseLabel} (${state.kinds.map(formatKind).join(', ')})`;
}
