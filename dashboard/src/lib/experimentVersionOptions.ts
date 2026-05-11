// Author: Max Stoddard
import type { ModelRunSnapshotOption } from '../../shared/types';

const OPTIMISED_2011_VERSION = 'v0oo';
const ORIGINAL_2011_VERSION = 'v0';
const LEGACY_2011_VERSIONS = new Set([OPTIMISED_2011_VERSION, ORIGINAL_2011_VERSION, 'v0o']);

function statusSuffix(snapshot: ModelRunSnapshotOption): string {
  return snapshot.status === 'in_progress' ? ', In progress' : '';
}

export function orderExperimentModelOptions(snapshots: readonly ModelRunSnapshotOption[]): ModelRunSnapshotOption[] {
  const byVersion = new Map(snapshots.map((snapshot) => [snapshot.version, snapshot]));
  const latest2024 =
    snapshots.find((snapshot) => !LEGACY_2011_VERSIONS.has(snapshot.version) && snapshot.status !== 'in_progress') ??
    snapshots.find((snapshot) => !LEGACY_2011_VERSIONS.has(snapshot.version));
  const preferredVersions = [OPTIMISED_2011_VERSION, ORIGINAL_2011_VERSION, latest2024?.version].filter(
    (version): version is string => Boolean(version)
  );
  const preferredSet = new Set(preferredVersions);

  return [
    ...preferredVersions.map((version) => byVersion.get(version)).filter((snapshot): snapshot is ModelRunSnapshotOption => Boolean(snapshot)),
    ...snapshots.filter((snapshot) => !preferredSet.has(snapshot.version))
  ];
}

export function formatExperimentModelOption(snapshot: ModelRunSnapshotOption, snapshots: readonly ModelRunSnapshotOption[]): string {
  if (snapshot.version === OPTIMISED_2011_VERSION) {
    return 'Optimised 2011 model (v0oo, Stable)';
  }
  if (snapshot.version === ORIGINAL_2011_VERSION) {
    return '2011 model (v0, Stable)';
  }

  const latest2024 =
    snapshots.find((item) => !LEGACY_2011_VERSIONS.has(item.version) && item.status !== 'in_progress') ??
    snapshots.find((item) => !LEGACY_2011_VERSIONS.has(item.version));
  if (latest2024?.version === snapshot.version) {
    return `Latest 2024 model (${snapshot.version}, Beta${statusSuffix(snapshot)})`;
  }

  return `${snapshot.version} model (Beta${statusSuffix(snapshot)})`;
}
