// Author: Max Stoddard
import type { ModelRunSnapshotOption } from '../../shared/types';
import { formatModelVersionBaseLabel } from './versionLabels';

const OPTIMISED_2011_VERSIONS = ['v0o2', 'v0oo'] as const;
const ORIGINAL_2011_VERSION = 'v0';
const LEGACY_2011_VERSIONS = new Set([...OPTIMISED_2011_VERSIONS, ORIGINAL_2011_VERSION, 'v0o', 'v0o1']);

function statusSuffix(snapshot: ModelRunSnapshotOption): string {
  return snapshot.status === 'in_progress' ? ', In progress' : '';
}

export function orderExperimentModelOptions(snapshots: readonly ModelRunSnapshotOption[]): ModelRunSnapshotOption[] {
  const byVersion = new Map(snapshots.map((snapshot) => [snapshot.version, snapshot]));
  const optimised2011Version = OPTIMISED_2011_VERSIONS.find((version) => byVersion.has(version));
  const latest2024 =
    snapshots.find((snapshot) => !LEGACY_2011_VERSIONS.has(snapshot.version) && snapshot.status !== 'in_progress') ??
    snapshots.find((snapshot) => !LEGACY_2011_VERSIONS.has(snapshot.version));
  const preferredVersions = [optimised2011Version, ORIGINAL_2011_VERSION, latest2024?.version].filter(
    (version): version is string => Boolean(version)
  );
  const preferredSet = new Set(preferredVersions);

  return [
    ...preferredVersions.map((version) => byVersion.get(version)).filter((snapshot): snapshot is ModelRunSnapshotOption => Boolean(snapshot)),
    ...snapshots.filter((snapshot) => !preferredSet.has(snapshot.version))
  ];
}

export function formatExperimentModelOption(snapshot: ModelRunSnapshotOption, snapshots: readonly ModelRunSnapshotOption[]): string {
  const latest2024 =
    snapshots.find((item) => !LEGACY_2011_VERSIONS.has(item.version) && item.status !== 'in_progress') ??
    snapshots.find((item) => !LEGACY_2011_VERSIONS.has(item.version));
  const baseLabel = formatModelVersionBaseLabel(snapshot.version, { isLatest: latest2024?.version === snapshot.version });
  const releaseState = LEGACY_2011_VERSIONS.has(snapshot.version) ? 'Stable' : `Beta${statusSuffix(snapshot)}`;

  return `${baseLabel} (${releaseState})`;
}
