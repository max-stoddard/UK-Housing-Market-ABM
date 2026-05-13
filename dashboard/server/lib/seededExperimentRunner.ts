// Author: Max Stoddard
import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import os from 'node:os';
import type {
  ExperimentJobStatus,
  ExperimentProgressSnapshot
} from '../../shared/types';
import type { ModelLauncher } from './modelLauncher';
import type { RuntimePaths } from './runtimePaths';

export const FORCED_STARTING_SEED = 1;
export const DEFAULT_MAX_WORKERS_CAP = 20;

export type SeededExperimentKind = 'manual' | 'sensitivity';
export type SeededRunStatus = 'succeeded' | 'failed' | 'canceled';
export type SeededTaskStatus = 'queued' | 'running' | SeededRunStatus;

export interface SeededProgressTask {
  taskId: string;
  pointId: string;
  pointLabel: string;
  seed: number;
  workerIndex: number | null;
  nSteps: number | null;
  lastModelTime: number | null;
  startedAtMs: number | null;
  endedAtMs: number | null;
  status: SeededTaskStatus;
}

export interface SeededProgressState {
  kind: SeededExperimentKind;
  totalRuns: number;
  totalWorkers: number;
  tasks: Map<string, SeededProgressTask>;
  workerTaskIds: Map<number, string>;
  startedAtMs: number | null;
  endedAtMs: number | null;
  updatedAtMs: number;
}

export interface SeededProgressOwner {
  progress: SeededProgressState;
  progressSink?: (progress: ExperimentProgressSnapshot) => void;
  lastProgressSinkAtMs: number;
}

export interface SeededProcessOwner extends SeededProgressOwner {
  launcher: ModelLauncher;
  activeProcesses: Set<ChildProcessWithoutNullStreams>;
  killTimer?: NodeJS.Timeout;
  cancelRequested: boolean;
}

export interface SeededTaskIdentity {
  pointId: string;
  pointLabel: string;
  seed: number;
  taskId?: string;
}

export interface SeededModelExecutionResult {
  status: SeededRunStatus;
  error?: string;
}

interface ParsedJvmProgressLine {
  simulation: number;
  modelTime: number;
}

export function seededTaskId(pointId: string, seed: number): string {
  return `${pointId}\0${seed}`;
}

export function buildSeeds(seedCount: number): number[] {
  return Array.from({ length: seedCount }, (_unused, index) => FORCED_STARTING_SEED + index);
}

export function parseSeedCount(rawValue: unknown, label: string): number {
  const rawSeedCount = Number(rawValue ?? 1);
  if (!Number.isFinite(rawSeedCount) || !Number.isInteger(rawSeedCount) || rawSeedCount < 1) {
    throw new Error(`${label} must be a positive integer.`);
  }
  return rawSeedCount;
}

export function defaultWorkerCount(totalRuns: number): number {
  const availableWorkers =
    typeof os.availableParallelism === 'function' ? os.availableParallelism() : os.cpus().length;
  return Math.max(1, Math.min(totalRuns, Math.max(1, availableWorkers), DEFAULT_MAX_WORKERS_CAP));
}

export function parseMaxWorkers(rawValue: unknown, totalRuns: number): number {
  if (totalRuns < 1) {
    return 1;
  }

  if (rawValue === undefined || rawValue === null || rawValue === '') {
    return defaultWorkerCount(totalRuns);
  }

  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 1) {
    throw new Error('maxWorkers must be a positive integer.');
  }

  return Math.max(1, Math.min(parsed, totalRuns));
}

export function createSeededProgressState(
  kind: SeededExperimentKind,
  taskIdentities: SeededTaskIdentity[],
  maxWorkers: number,
  startedAt?: string,
  endedAt?: string
): SeededProgressState {
  const tasks = new Map<string, SeededProgressTask>();
  for (const identity of taskIdentities) {
    const taskId = identity.taskId ?? seededTaskId(identity.pointId, identity.seed);
    tasks.set(taskId, {
      taskId,
      pointId: identity.pointId,
      pointLabel: identity.pointLabel,
      seed: identity.seed,
      workerIndex: null,
      nSteps: null,
      lastModelTime: null,
      startedAtMs: null,
      endedAtMs: null,
      status: 'queued'
    });
  }

  const startedAtMs = startedAt ? Date.parse(startedAt) : Number.NaN;
  const endedAtMs = endedAt ? Date.parse(endedAt) : Number.NaN;

  return {
    kind,
    totalRuns: tasks.size,
    totalWorkers: Math.max(1, maxWorkers),
    tasks,
    workerTaskIds: new Map(),
    startedAtMs: Number.isFinite(startedAtMs) ? startedAtMs : null,
    endedAtMs: Number.isFinite(endedAtMs) ? endedAtMs : null,
    updatedAtMs: Date.now()
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function taskProgressFraction(task: SeededProgressTask): number {
  if (task.status === 'succeeded' || task.status === 'failed' || task.status === 'canceled') {
    return 1;
  }
  if (task.status !== 'running' || task.nSteps === null || task.nSteps <= 0 || task.lastModelTime === null) {
    return 0;
  }
  return clamp(task.lastModelTime / task.nSteps, 0, 0.999);
}

export function createProgressSnapshot(
  owner: SeededProgressOwner,
  status: ExperimentJobStatus,
  nowMs = Date.now()
): ExperimentProgressSnapshot {
  const tasks = [...owner.progress.tasks.values()];
  const succeededRuns = tasks.filter((task) => task.status === 'succeeded').length;
  const failedRuns = tasks.filter((task) => task.status === 'failed').length;
  const canceledRuns = tasks.filter((task) => task.status === 'canceled').length;
  const completedRuns = succeededRuns + failedRuns + canceledRuns;
  const activeRuns = tasks.filter((task) => task.status === 'running').length;
  const completedRunEquivalents = tasks.reduce((sum, task) => sum + taskProgressFraction(task), 0);
  const startedAtMs = owner.progress.startedAtMs;
  const endedAtMs = owner.progress.endedAtMs;
  const elapsedMs = startedAtMs === null ? 0 : Math.max(0, (endedAtMs ?? nowMs) - startedAtMs);
  const elapsedMinutes = elapsedMs / 60_000;
  const throughputRunsPerMinute = elapsedMinutes > 0 ? completedRunEquivalents / elapsedMinutes : null;
  const completedRunsPerMinute = elapsedMinutes > 0 ? completedRuns / elapsedMinutes : null;
  const remainingRuns = Math.max(0, owner.progress.totalRuns - completedRunEquivalents);
  const canEstimateEta =
    status === 'running' &&
    throughputRunsPerMinute !== null &&
    throughputRunsPerMinute > 0 &&
    remainingRuns > 0;
  const etaSeconds = canEstimateEta ? (remainingRuns / throughputRunsPerMinute) * 60 : null;
  const estimatedFinishAt = etaSeconds === null ? null : new Date(nowMs + etaSeconds * 1000).toISOString();

  return {
    kind: owner.progress.kind,
    status,
    totalRuns: owner.progress.totalRuns,
    completedRuns,
    failedRuns,
    canceledRuns,
    activeRuns,
    totalWorkers: owner.progress.totalWorkers,
    activeWorkers: owner.progress.workerTaskIds.size,
    completedRunEquivalents,
    percentComplete: owner.progress.totalRuns === 0
      ? 0
      : clamp((completedRunEquivalents / owner.progress.totalRuns) * 100, 0, 100),
    throughputRunsPerMinute,
    completedRunsPerMinute,
    etaSeconds,
    estimatedFinishAt,
    elapsedSeconds: elapsedMs / 1000,
    ...(startedAtMs !== null ? { startedAt: new Date(startedAtMs).toISOString() } : {}),
    ...(endedAtMs !== null ? { endedAt: new Date(endedAtMs).toISOString() } : {}),
    updatedAt: new Date(nowMs).toISOString()
  };
}

export function publishProgress(
  owner: SeededProgressOwner,
  status: ExperimentJobStatus,
  force = false
): void {
  if (!owner.progressSink) {
    return;
  }
  const nowMs = Date.now();
  if (!force && nowMs - owner.lastProgressSinkAtMs < 1_000) {
    return;
  }
  owner.lastProgressSinkAtMs = nowMs;
  try {
    owner.progressSink(createProgressSnapshot(owner, status, nowMs));
  } catch {
    // Progress sinks are diagnostic; they must not affect run execution.
  }
}

export function updateProgressStarted(
  owner: SeededProgressOwner,
  status: ExperimentJobStatus,
  startedAt?: string
): void {
  const startedAtMs = startedAt ? Date.parse(startedAt) : Date.now();
  owner.progress.startedAtMs = Number.isFinite(startedAtMs) ? startedAtMs : Date.now();
  owner.progress.updatedAtMs = Date.now();
  publishProgress(owner, status, true);
}

export function updateProgressEnded(
  owner: SeededProgressOwner,
  status: ExperimentJobStatus,
  endedAt?: string
): void {
  const endedAtMs = endedAt ? Date.parse(endedAt) : Date.now();
  owner.progress.endedAtMs = Number.isFinite(endedAtMs) ? endedAtMs : Date.now();
  owner.progress.updatedAtMs = Date.now();
  publishProgress(owner, status, true);
}

export function startProgressTask(
  owner: SeededProgressOwner,
  identity: SeededTaskIdentity,
  workerIndex: number,
  nSteps: number | null,
  status: ExperimentJobStatus
): SeededProgressTask {
  const id = identity.taskId ?? seededTaskId(identity.pointId, identity.seed);
  let task = owner.progress.tasks.get(id);
  if (!task) {
    task = {
      taskId: id,
      pointId: identity.pointId,
      pointLabel: identity.pointLabel,
      seed: identity.seed,
      workerIndex: null,
      nSteps: null,
      lastModelTime: null,
      startedAtMs: null,
      endedAtMs: null,
      status: 'queued'
    };
    owner.progress.tasks.set(id, task);
    owner.progress.totalRuns = owner.progress.tasks.size;
  }
  task.status = 'running';
  task.workerIndex = workerIndex;
  task.nSteps = nSteps;
  task.lastModelTime = null;
  task.startedAtMs = Date.now();
  task.endedAtMs = null;
  owner.progress.workerTaskIds.set(workerIndex, id);
  owner.progress.updatedAtMs = Date.now();
  publishProgress(owner, status, true);
  return task;
}

export function updateProgressModelTime(
  owner: SeededProgressOwner,
  id: string,
  modelTime: number,
  status: ExperimentJobStatus
): void {
  const task = owner.progress.tasks.get(id);
  if (!task || task.status !== 'running') {
    return;
  }
  task.lastModelTime = Math.max(task.lastModelTime ?? 0, modelTime);
  owner.progress.updatedAtMs = Date.now();
  publishProgress(owner, status);
}

export function finishProgressTask(
  owner: SeededProgressOwner,
  id: string,
  taskStatus: SeededRunStatus,
  status: ExperimentJobStatus
): void {
  const task = owner.progress.tasks.get(id);
  if (!task) {
    return;
  }
  task.status = taskStatus;
  task.lastModelTime = task.nSteps;
  task.endedAtMs = Date.now();
  if (task.workerIndex !== null) {
    owner.progress.workerTaskIds.delete(task.workerIndex);
  }
  owner.progress.updatedAtMs = Date.now();
  publishProgress(owner, status, true);
}

function parseJvmProgressLine(line: string): ParsedJvmProgressLine | null {
  const match = /^Simulation:\s*(\d+),\s*time:\s*([0-9]+(?:\.[0-9]+)?)\s*$/.exec(line.trim());
  if (!match) {
    return null;
  }
  const simulation = Number.parseInt(match[1], 10);
  const modelTime = Number.parseFloat(match[2]);
  if (!Number.isFinite(simulation) || !Number.isFinite(modelTime)) {
    return null;
  }
  return { simulation, modelTime };
}

function createOutputParser(
  owner: SeededProgressOwner,
  id: string,
  status: () => ExperimentJobStatus,
  rawLogSink?: (streamName: 'stdout' | 'stderr', line: string) => void
) {
  const partials: Record<'stdout' | 'stderr', string> = {
    stdout: '',
    stderr: ''
  };

  const handleLine = (streamName: 'stdout' | 'stderr', line: string): void => {
    rawLogSink?.(streamName, line);
    if (streamName !== 'stdout') {
      return;
    }
    const parsed = parseJvmProgressLine(line);
    if (parsed) {
      updateProgressModelTime(owner, id, parsed.modelTime, status());
    }
  };

  const append = (streamName: 'stdout' | 'stderr', chunk: Buffer): void => {
    partials[streamName] += chunk.toString('utf-8').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    while (true) {
      const lineBreak = partials[streamName].indexOf('\n');
      if (lineBreak < 0) {
        break;
      }
      const line = partials[streamName].slice(0, lineBreak);
      partials[streamName] = partials[streamName].slice(lineBreak + 1);
      handleLine(streamName, line);
    }
  };

  const flush = (): void => {
    for (const streamName of ['stdout', 'stderr'] as const) {
      if (!partials[streamName]) {
        continue;
      }
      handleLine(streamName, partials[streamName]);
      partials[streamName] = '';
    }
  };

  return { append, flush };
}

export async function runSeededModelProcess(input: {
  paths: RuntimePaths;
  owner: SeededProcessOwner;
  configPath: string;
  outputPath: string;
  taskId: string;
  status: () => ExperimentJobStatus;
  rawLogSink?: (streamName: 'stdout' | 'stderr', line: string) => void;
  formatLaunchError?: (error: Error) => string;
}): Promise<SeededModelExecutionResult> {
  return new Promise<SeededModelExecutionResult>((resolve) => {
    let stderr = '';
    let stdout = '';
    let child: ChildProcessWithoutNullStreams;
    const outputParser = createOutputParser(input.owner, input.taskId, input.status, input.rawLogSink);

    try {
      child = input.owner.launcher.launch({
        repoRoot: input.paths.repoRoot,
        configPath: input.configPath,
        outputPath: input.outputPath
      });
    } catch (error) {
      const message = input.formatLaunchError
        ? input.formatLaunchError(error as Error)
        : (error as Error).message;
      resolve({ status: 'failed', error: `Failed to spawn model process: ${message}` });
      return;
    }

    input.owner.activeProcesses.add(child);

    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf-8');
      outputParser.append('stdout', chunk);
    });

    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf-8');
      outputParser.append('stderr', chunk);
    });

    child.on('error', (error: Error) => {
      stderr += `${error.message}\n`;
    });

    child.on('close', (code) => {
      input.owner.activeProcesses.delete(child);
      outputParser.flush();
      if (input.owner.killTimer && input.owner.activeProcesses.size === 0) {
        clearTimeout(input.owner.killTimer);
        input.owner.killTimer = undefined;
      }

      if (input.owner.cancelRequested) {
        resolve({ status: 'canceled', error: stderr.trim() || undefined });
        return;
      }

      if (code === 0) {
        resolve({ status: 'succeeded' });
        return;
      }

      const output = stderr.trim() || stdout.trim() || `Model run exited with code ${String(code)}`;
      resolve({ status: 'failed', error: output.slice(-2_000) });
    });
  });
}

export async function runSeededWorkerPool<Task, Result>(input: {
  tasks: Task[];
  maxWorkers: number;
  isCancelRequested: () => boolean;
  runTask: (task: Task, workerIndex: number) => Promise<Result>;
  onResult?: (task: Task, result: Result) => void;
  shouldStopOnResult?: (result: Result) => boolean;
}): Promise<void> {
  let nextTaskIndex = 0;
  let stopLaunching = false;

  const runWorker = async (workerIndex: number) => {
    while (!stopLaunching && !input.isCancelRequested()) {
      const task = input.tasks[nextTaskIndex];
      nextTaskIndex += 1;
      if (!task) {
        return;
      }

      const result = await input.runTask(task, workerIndex);
      input.onResult?.(task, result);

      if (input.shouldStopOnResult?.(result)) {
        stopLaunching = true;
      }
    }
  };

  const workerCount = Math.min(Math.max(1, input.maxWorkers), input.tasks.length);
  await Promise.all(Array.from({ length: workerCount }, (_unused, index) => runWorker(index + 1)));
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) {
    return 'pending';
  }
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${remainingSeconds}s`;
}

function formatEstimatedFinish(isoTimestamp: string | null): string {
  if (!isoTimestamp) {
    return 'pending';
  }
  const date = new Date(isoTimestamp);
  if (!Number.isFinite(date.getTime())) {
    return 'pending';
  }
  return date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
}

function formatRate(value: number | null): string {
  return value === null || !Number.isFinite(value) ? 'pending' : `${value.toFixed(2)}/min`;
}

export function formatProgressBrief(snapshot: ExperimentProgressSnapshot): string {
  return `progress ${snapshot.completedRunEquivalents.toFixed(1)}/${snapshot.totalRuns} (${snapshot.percentComplete.toFixed(
    1
  )}%), completed ${snapshot.completedRuns}/${snapshot.totalRuns}, active workers ${snapshot.activeWorkers}/${
    snapshot.totalWorkers
  }, throughput ${formatRate(snapshot.throughputRunsPerMinute)}, ETA ${formatDuration(snapshot.etaSeconds)}, finish ${formatEstimatedFinish(
    snapshot.estimatedFinishAt
  )}`;
}
