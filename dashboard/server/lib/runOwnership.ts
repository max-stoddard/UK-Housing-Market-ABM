import fs from 'node:fs';
import path from 'node:path';

export const MANAGED_RUN_MARKER = '.dashboard-managed-run.json';

export interface DashboardManagedRunMarkerInput {
  jobId: string;
  runId: string;
  baseline: string;
  title?: string | null;
  createdAt: string;
}

interface DashboardManagedRunMarker {
  managedBy: 'dashboard';
  jobId: string;
  runId: string;
  baseline: string;
  title: string | null;
  createdAt: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isValidCreatedAt(value: unknown): value is string {
  return isNonEmptyString(value) && Number.isFinite(Date.parse(value));
}

function isValidDashboardManagedRunMarker(
  value: unknown,
  expectedRunId?: string
): value is DashboardManagedRunMarker {
  if (!isRecord(value)) {
    return false;
  }

  if (value.managedBy !== 'dashboard') {
    return false;
  }
  if (!isNonEmptyString(value.jobId) || !isNonEmptyString(value.runId) || !isNonEmptyString(value.baseline)) {
    return false;
  }
  if (value.title !== null && typeof value.title !== 'string') {
    return false;
  }
  if (!isValidCreatedAt(value.createdAt)) {
    return false;
  }

  return expectedRunId === undefined || value.runId === expectedRunId;
}

export function isDashboardManagedRun(runPath: string, expectedRunId?: string): boolean {
  const markerPath = path.join(runPath, MANAGED_RUN_MARKER);
  try {
    if (!fs.existsSync(markerPath) || !fs.statSync(markerPath).isFile()) {
      return false;
    }

    const marker = JSON.parse(fs.readFileSync(markerPath, 'utf-8')) as unknown;
    return isValidDashboardManagedRunMarker(marker, expectedRunId);
  } catch {
    return false;
  }
}

export function writeDashboardManagedRunMarker(
  runPath: string,
  input: DashboardManagedRunMarkerInput
): void {
  const marker: DashboardManagedRunMarker = {
    managedBy: 'dashboard',
    jobId: input.jobId,
    runId: input.runId,
    baseline: input.baseline,
    title: input.title ?? null,
    createdAt: input.createdAt
  };

  if (!isValidDashboardManagedRunMarker(marker, input.runId)) {
    throw new Error('Invalid dashboard-managed run marker metadata.');
  }

  fs.writeFileSync(path.join(runPath, MANAGED_RUN_MARKER), JSON.stringify(marker, null, 2), 'utf-8');
}
