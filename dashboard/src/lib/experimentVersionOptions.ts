// Author: Max Stoddard
import type { ModelRunSnapshotOption } from '../../shared/types';
import { formatModelVersionBaseLabel } from './versionLabels';

const OPTIMISED_2011_VERSION = 'v0o7';
const OPTIMISED_2024_VERSION = 'v5o3';
const LEGACY_2011_VERSION_IDS = ['v0o', 'v0oo', 'v0o1', 'v0o2', 'v0o3', 'v0o6', OPTIMISED_2011_VERSION] as const;
const ORIGINAL_2011_VERSION = 'v0';
const LEGACY_2011_VERSIONS = new Set([...LEGACY_2011_VERSION_IDS, ORIGINAL_2011_VERSION]);

function statusSuffix(snapshot: ModelRunSnapshotOption): string {
  return snapshot.status === 'in_progress' ? ', In progress' : '';
}

function formatCanonicalExperimentBaseLabel(baseLabel: string, version: string): string | null {
  if (baseLabel === 'Original 2011 model' || baseLabel === 'Optimised 2011 model') {
    return baseLabel;
  }

  if (baseLabel === `Optimised 2024 model ${version}`) {
    return 'Optimised 2024 model';
  }

  if (baseLabel === `Latest 2024 model ${version}`) {
    return 'Latest 2024 model';
  }

  return null;
}

export function orderExperimentModelOptions(snapshots: readonly ModelRunSnapshotOption[]): ModelRunSnapshotOption[] {
  const byVersion = new Map(snapshots.map((snapshot) => [snapshot.version, snapshot]));
  const optimised2011Version = byVersion.has(OPTIMISED_2011_VERSION) ? OPTIMISED_2011_VERSION : undefined;
  const optimised2024Version = byVersion.has(OPTIMISED_2024_VERSION) ? OPTIMISED_2024_VERSION : undefined;
  const fallbackLatest2024 =
    snapshots.find((snapshot) => !LEGACY_2011_VERSIONS.has(snapshot.version) && snapshot.status !== 'in_progress') ??
    snapshots.find((snapshot) => !LEGACY_2011_VERSIONS.has(snapshot.version));
  const preferredVersions = [optimised2011Version, ORIGINAL_2011_VERSION, optimised2024Version ?? fallbackLatest2024?.version].filter(
    (version): version is string => Boolean(version)
  );
  const preferredSet = new Set(preferredVersions);

  return [
    ...preferredVersions.map((version) => byVersion.get(version)).filter((snapshot): snapshot is ModelRunSnapshotOption => Boolean(snapshot)),
    ...snapshots.filter((snapshot) => !preferredSet.has(snapshot.version))
  ];
}

export function formatExperimentModelOption(snapshot: ModelRunSnapshotOption, snapshots: readonly ModelRunSnapshotOption[]): string {
  const optimised2024 = snapshots.find((item) => item.version === OPTIMISED_2024_VERSION);
  const fallbackLatest2024 =
    snapshots.find((item) => !LEGACY_2011_VERSIONS.has(item.version) && item.status !== 'in_progress') ??
    snapshots.find((item) => !LEGACY_2011_VERSIONS.has(item.version));
  const latest2024 = optimised2024 ?? fallbackLatest2024;
  const baseLabel = formatModelVersionBaseLabel(snapshot.version, { isLatest: latest2024?.version === snapshot.version });
  const canonicalBaseLabel = formatCanonicalExperimentBaseLabel(baseLabel, snapshot.version);
  const releaseState = LEGACY_2011_VERSIONS.has(snapshot.version) ? 'Stable' : `Beta${statusSuffix(snapshot)}`;

  if (canonicalBaseLabel) {
    return `${canonicalBaseLabel} (${releaseState}, ${snapshot.version})`;
  }

  return `${baseLabel} (${releaseState})`;
}
