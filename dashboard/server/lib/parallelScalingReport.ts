// Author: Max Stoddard
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import type { ModelLauncher } from './modelLauncher';
import { createMavenModelLauncher } from './modelLauncher';
import { createDevelopmentRuntimePaths } from './runtimePaths';
import {
  createSeededProgressState,
  finishProgressTask,
  runSeededModelProcess,
  runSeededWorkerPool,
  seededTaskId,
  startProgressTask,
  type SeededProcessOwner,
  type SeededRunStatus
} from './seededExperimentRunner';

export const DEFAULT_PARALLEL_SCALING_WORKER_COUNTS = [1, 2, 4, 8, 12, 16, 20, 24, 32] as const;

export interface ParallelScalingExperimentOptions {
  repoRoot: string;
  snapshot: string;
  baseMode: string;
  outputRoot: string;
  targetPopulation: number;
  nSteps: number;
  seedCount: number;
  workerCounts: number[];
  repeats: number;
  orderingSeed: number;
  phase: 'pilot' | 'full';
  confirmExpensive?: boolean;
  javaOptions?: string[];
  policyLabel?: string;
}

export interface ParallelScalingChildResult {
  batchId: string;
  taskId: string;
  seed: number;
  workerIndex: number;
  status: 'succeeded' | 'failed' | 'canceled';
  startedAt: string;
  endedAt: string;
  wallClockSeconds: number;
  configPath: string;
  outputPath: string;
  error?: string;
}

export interface ParallelScalingBatchResult {
  batchId: string;
  phase: 'pilot' | 'full';
  workerCount: number;
  effectiveWorkerCount: number;
  repeatIndex: number;
  runOrderIndex: number;
  seedCount: number;
  status: 'succeeded' | 'failed' | 'canceled';
  startedAt: string;
  endedAt: string;
  wallClockSeconds: number;
  completedChildCount: number;
  failedChildCount: number;
  canceledChildCount: number;
  throughputRunsPerHour: number;
  children: ParallelScalingChildResult[];
}

export interface ParallelScalingBatchPlan {
  batchId: string;
  runOrderIndex: number;
  workerCount: number;
  effectiveWorkerCount: number;
  repeatIndex: number;
  seeds: number[];
}

export interface ParallelScalingExperimentResult {
  schemaVersion: 1;
  runId: string;
  status: SeededRunStatus;
  createdAt: string;
  startedAt: string;
  endedAt: string;
  wallClockSeconds: number;
  runRoot: string;
  host: {
    hostname: string;
    platform: NodeJS.Platform;
    arch: string;
    cpuCount: number;
    availableParallelism: number;
    totalMemoryBytes: number;
  };
  git: {
    commit: string | null;
    branch: string | null;
    dirty: boolean | null;
  };
  workload: {
    snapshot: string;
    baseMode: string;
    seedCount: number;
    targetPopulation: number;
    nSteps: number;
    repeats: number;
    workerCounts: number[];
    orderingSeed: number;
    phase: 'pilot' | 'full';
    javaOptions: string[];
    policyLabel: string;
  };
  runOrder: ParallelScalingBatchPlan[];
  batches: ParallelScalingBatchResult[];
  analysis: {
    status: 'ready' | 'partial' | 'empty';
    includedBatchIds: string[];
    excludedBatchIds: string[];
  };
  artifacts: {
    runRoot: string;
    childrenCsvPath: string;
    batchesCsvPath: string;
    rawJsonPath: string;
  };
}

export interface ParallelScalingConfigMaterializationOptions {
  repoRoot: string;
  snapshot: string;
  baseMode: string;
  targetPopulation: number;
  nSteps: number;
  seed: number;
  outputConfigPath: string;
  baselineConfigPath?: string;
  modeOverridePath?: string;
}

export interface ParallelScalingExperimentDependencies {
  launcher?: ModelLauncher;
  now?: (() => Date) | Date;
  logSink?: (line: string) => void;
}

interface NormalizedParallelScalingOptions {
  repoRoot: string;
  outputRoot: string;
  snapshot: string;
  baseMode: string;
  workerCounts: number[];
  seedCount: number;
  targetPopulation: number;
  nSteps: number;
  repeats: number;
  orderingSeed: string;
  orderingSeedValue: number;
  phase: 'pilot' | 'full';
  javaOptions: string[];
  policyLabel: string;
}

interface ParallelScalingSeedTask {
  batchId: string;
  taskId: string;
  runOrderIndex: number;
  seed: number;
  configPath: string;
  outputPath: string;
  logPath: string;
}

const PROPERTY_LINE_PATTERN = /^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*)$/;
const CHILD_CSV_HEADERS = [
  'run_id',
  'batch_id',
  'phase',
  'worker_count',
  'effective_worker_count',
  'repeat_index',
  'run_order_index',
  'seed',
  'task_id',
  'worker_index',
  'status',
  'started_at',
  'ended_at',
  'wall_clock_seconds',
  'config_path',
  'output_path',
  'error'
] as const;
const BATCH_CSV_HEADERS = [
  'run_id',
  'batch_id',
  'phase',
  'worker_count',
  'effective_worker_count',
  'repeat_index',
  'run_order_index',
  'seed_count',
  'status',
  'started_at',
  'ended_at',
  'wall_clock_seconds',
  'completed_child_count',
  'failed_child_count',
  'canceled_child_count',
  'throughput_runs_per_hour'
] as const;
const HEAVY_MODEL_OUTPUT_FILE_PATTERN = /^Output-run\d+\.csv$/;

export function parseWorkerCounts(raw: number[] | string | null | undefined): number[] {
  const values = raw === undefined || raw === null || raw === ''
    ? [...DEFAULT_PARALLEL_SCALING_WORKER_COUNTS]
    : Array.isArray(raw)
      ? raw
      : raw.split(',').map((value) => value.trim()).filter(Boolean).map(Number);
  if (values.length === 0) {
    throw new Error('workerCounts must include at least one positive integer.');
  }

  const seen = new Set<number>();
  for (const value of values) {
    if (!Number.isFinite(value) || !Number.isInteger(value) || value <= 0) {
      throw new Error('workerCounts must contain only positive integers.');
    }
    if (seen.has(value)) {
      throw new Error(`Duplicate worker count: ${value}`);
    }
    seen.add(value);
  }
  return [...values];
}

export function buildSeedList(seedCount: number): number[] {
  assertPositiveInteger(seedCount, 'seedCount');
  return Array.from({ length: seedCount }, (_unused, index) => index + 1);
}

export function buildBatchPlan(options: ParallelScalingExperimentOptions): ParallelScalingBatchPlan[] {
  return buildBatchPlanFromNormalized(normalizeOptions(options));
}

function buildBatchPlanFromNormalized(normalized: NormalizedParallelScalingOptions): ParallelScalingBatchPlan[] {
  const seeds = buildSeedList(normalized.seedCount);
  const batches: Omit<ParallelScalingBatchPlan, 'runOrderIndex'>[] = [];
  for (let repeatIndex = 1; repeatIndex <= normalized.repeats; repeatIndex += 1) {
    for (const workerCount of normalized.workerCounts) {
      batches.push({
        batchId: `r${repeatIndex}-w${workerCount}`,
        workerCount,
        effectiveWorkerCount: Math.min(workerCount, normalized.seedCount),
        repeatIndex,
        seeds
      });
    }
  }

  return deterministicShuffle(batches, normalized.orderingSeed).map((batch, index) => ({
    ...batch,
    runOrderIndex: index + 1,
    seeds: [...batch.seeds]
  }));
}

export function materializeParallelScalingConfig(options: ParallelScalingConfigMaterializationOptions): void {
  assertPositiveInteger(options.targetPopulation, 'targetPopulation');
  assertPositiveInteger(options.nSteps, 'nSteps');
  assertPositiveInteger(options.seed, 'seed');

  const repoRoot = path.resolve(options.repoRoot);
  const snapshotRoot = path.join(repoRoot, 'input-data-versions', options.snapshot);
  const baselineConfigPath = path.resolve(
    options.baselineConfigPath ?? path.join(snapshotRoot, 'config.properties')
  );
  const modeOverridePath = path.resolve(
    options.modeOverridePath ?? path.join(repoRoot, 'scripts', 'model', 'configs', `${options.snapshot}-${options.baseMode}.properties`)
  );
  const overrides = readPropertyOverrides(modeOverridePath);
  overrides.set('TARGET_POPULATION', String(options.targetPopulation));
  overrides.set('N_STEPS', String(options.nSteps));
  overrides.set('N_SIMS', '1');
  overrides.set('SEED', String(options.seed));

  rewriteConfig({
    baselineConfigPath,
    snapshotRoot,
    outputConfigPath: options.outputConfigPath,
    overrides
  });
}

export async function runParallelScalingExperiment(
  options: ParallelScalingExperimentOptions,
  dependencies: ParallelScalingExperimentDependencies = {}
): Promise<ParallelScalingExperimentResult> {
  const normalized = normalizeOptions(options, true);
  const now = createNowProvider(dependencies.now);
  const createdAt = now().toISOString();
  const runId = createRunId(createdAt, normalized);
  const runRoot = path.join(normalized.outputRoot, 'parallel-scaling', runId);
  const runsRoot = path.join(runRoot, 'runs');
  const artifacts = {
    runRoot,
    childrenCsvPath: path.join(runRoot, 'parallel_scaling_children.csv'),
    batchesCsvPath: path.join(runRoot, 'parallel_scaling_batches.csv'),
    rawJsonPath: path.join(runRoot, 'parallel_scaling_raw.json')
  };
  const launcher = dependencies.launcher ?? createMavenModelLauncher();
  const paths = {
    ...createDevelopmentRuntimePaths(normalized.repoRoot),
    resultsRoot: runRoot,
    tempRoot: runRoot,
    logsRoot: path.join(runRoot, 'logs')
  };
  const runOrder = buildBatchPlanFromNormalized(normalized);
  const batches: ParallelScalingBatchResult[] = [];
  const experimentStartedAt = now();
  let status: SeededRunStatus = 'succeeded';

  fs.mkdirSync(runsRoot, { recursive: true });
  launcher.prepare?.({ repoRoot: normalized.repoRoot });
  dependencies.logSink?.(`parallel scaling report ${runId} starting with ${runOrder.length} batches`);

  for (const batch of runOrder) {
    const batchResult = await runBatch({
      batch,
      normalized,
      paths,
      runsRoot,
      launcher,
      now,
      logSink: dependencies.logSink
    });
    batches.push(batchResult);
    if (batchResult.status === 'failed') {
      status = 'failed';
      break;
    } else if (batchResult.status === 'canceled') {
      status = 'canceled';
      break;
    }
  }

  const experimentEndedAt = now();
  const includedBatchIds = batches.filter((batch) => batch.status === 'succeeded').map((batch) => batch.batchId);
  const excludedBatchIds = batches.filter((batch) => batch.status !== 'succeeded').map((batch) => batch.batchId);
  const result: ParallelScalingExperimentResult = {
    schemaVersion: 1,
    runId,
    status,
    createdAt,
    startedAt: experimentStartedAt.toISOString(),
    endedAt: experimentEndedAt.toISOString(),
    wallClockSeconds: elapsedSeconds(experimentStartedAt, experimentEndedAt),
    runRoot,
    host: hostMetadata(),
    git: gitMetadata(normalized.repoRoot),
    workload: {
      snapshot: normalized.snapshot,
      baseMode: normalized.baseMode,
      seedCount: normalized.seedCount,
      targetPopulation: normalized.targetPopulation,
      nSteps: normalized.nSteps,
      repeats: normalized.repeats,
      workerCounts: [...normalized.workerCounts],
      orderingSeed: normalized.orderingSeedValue,
      phase: normalized.phase,
      javaOptions: [...normalized.javaOptions],
      policyLabel: normalized.policyLabel
    },
    runOrder,
    batches,
    analysis: {
      status: includedBatchIds.length === batches.length ? 'ready' : includedBatchIds.length === 0 ? 'empty' : 'partial',
      includedBatchIds,
      excludedBatchIds
    },
    artifacts
  };

  writeArtifacts(result);
  dependencies.logSink?.(`parallel scaling report ${runId} ended with status ${status}`);
  return result;
}

async function runBatch(input: {
  batch: ParallelScalingBatchPlan;
  normalized: NormalizedParallelScalingOptions;
  paths: ReturnType<typeof createDevelopmentRuntimePaths>;
  runsRoot: string;
  launcher: ModelLauncher;
  now: () => Date;
  logSink?: (line: string) => void;
}): Promise<ParallelScalingBatchResult> {
  const batchStartedAt = input.now();
  const batchRoot = path.join(input.runsRoot, input.batch.batchId);
  const tasks = input.batch.seeds.map((seed, index) => buildSeedTask(batchRoot, input.batch, seed, index + 1));
  const owner: SeededProcessOwner = {
    progress: createSeededProgressState(
      'manual',
      tasks.map((task) => ({
        pointId: input.batch.batchId,
        pointLabel: input.batch.batchId,
        seed: task.seed,
        taskId: task.taskId
      })),
      input.batch.effectiveWorkerCount,
      batchStartedAt.toISOString()
    ),
    progressSink: undefined,
    lastProgressSinkAtMs: 0,
    launcher: {
      mode: input.launcher.mode,
      metadata: input.launcher.metadata,
      prepare: input.launcher.prepare?.bind(input.launcher),
      buildCommand: (request) =>
        input.launcher.buildCommand({
          ...request,
          javaOptions: [...input.normalized.javaOptions]
        }),
      launch: (request) =>
        input.launcher.launch({
          ...request,
          javaOptions: [...input.normalized.javaOptions]
        })
    },
    activeProcesses: new Set(),
    cancelRequested: false
  };
  const children: ParallelScalingChildResult[] = [];

  input.logSink?.(
    `batch ${input.batch.batchId} starting with ${input.batch.effectiveWorkerCount}/${input.batch.workerCount} effective workers`
  );

  await runSeededWorkerPool({
    tasks,
    maxWorkers: input.batch.effectiveWorkerCount,
    isCancelRequested: () => owner.cancelRequested,
    runTask: (task, workerIndex) => runSeedTask({
      task,
      batch: input.batch,
      normalized: input.normalized,
      paths: input.paths,
      owner,
      workerIndex,
      now: input.now
    }),
    onResult: (_task, result) => {
      children.push(result);
    },
    shouldStopOnResult: (result) => result.status === 'failed' || result.status === 'canceled'
  });

  children.sort((left, right) => left.seed - right.seed);
  const failedChild = children.find((child) => child.status === 'failed');
  const canceledChild = children.find((child) => child.status === 'canceled');
  const status: SeededRunStatus = failedChild ? 'failed' : canceledChild ? 'canceled' : 'succeeded';
  const batchEndedAt = input.now();
  const wallClockSeconds = elapsedSeconds(batchStartedAt, batchEndedAt);
  const completedChildCount = children.filter((child) => child.status === 'succeeded').length;
  const failedChildCount = children.filter((child) => child.status === 'failed').length;
  const canceledChildCount = children.filter((child) => child.status === 'canceled').length;
  return {
    batchId: input.batch.batchId,
    phase: input.normalized.phase,
    workerCount: input.batch.workerCount,
    effectiveWorkerCount: input.batch.effectiveWorkerCount,
    repeatIndex: input.batch.repeatIndex,
    runOrderIndex: input.batch.runOrderIndex,
    seedCount: input.batch.seeds.length,
    status,
    startedAt: batchStartedAt.toISOString(),
    endedAt: batchEndedAt.toISOString(),
    wallClockSeconds,
    completedChildCount,
    failedChildCount,
    canceledChildCount,
    throughputRunsPerHour: throughputRunsPerHour(completedChildCount, wallClockSeconds),
    children
  };
}

async function runSeedTask(input: {
  task: ParallelScalingSeedTask;
  batch: ParallelScalingBatchPlan;
  normalized: NormalizedParallelScalingOptions;
  paths: ReturnType<typeof createDevelopmentRuntimePaths>;
  owner: SeededProcessOwner;
  workerIndex: number;
  now: () => Date;
}): Promise<ParallelScalingChildResult> {
  fs.mkdirSync(path.dirname(input.task.configPath), { recursive: true });
  fs.mkdirSync(input.task.outputPath, { recursive: true });
  fs.mkdirSync(path.dirname(input.task.logPath), { recursive: true });
  materializeParallelScalingConfig({
    repoRoot: input.normalized.repoRoot,
    snapshot: input.normalized.snapshot,
    baseMode: input.normalized.baseMode,
    targetPopulation: input.normalized.targetPopulation,
    nSteps: input.normalized.nSteps,
    seed: input.task.seed,
    outputConfigPath: input.task.configPath
  });

  const startedAt = input.now();
  startProgressTask(
    input.owner,
    {
      pointId: input.batch.batchId,
      pointLabel: input.batch.batchId,
      seed: input.task.seed,
      taskId: input.task.taskId
    },
    input.workerIndex,
    input.normalized.nSteps,
    'running'
  );

  const executionResult = await runSeededModelProcess({
    paths: input.paths,
    owner: input.owner,
    configPath: input.task.configPath,
    outputPath: input.task.outputPath,
    taskId: input.task.taskId,
    status: () => 'running',
    rawLogSink: (streamName, line) => {
      fs.appendFileSync(input.task.logPath, `[${streamName}] ${line}\n`, 'utf-8');
    },
    formatLaunchError: (error) => error.message
  });
  removeHeavyModelOutputFiles(input.task.outputPath);

  finishProgressTask(input.owner, input.task.taskId, executionResult.status, 'running');
  const endedAt = input.now();
  return {
    batchId: input.batch.batchId,
    taskId: input.task.taskId,
    seed: input.task.seed,
    workerIndex: input.workerIndex,
    status: executionResult.status,
    startedAt: startedAt.toISOString(),
    endedAt: endedAt.toISOString(),
    wallClockSeconds: elapsedSeconds(startedAt, endedAt),
    configPath: input.task.configPath,
    outputPath: input.task.outputPath,
    ...(executionResult.error ? { error: executionResult.error } : {})
  };
}

function buildSeedTask(
  batchRoot: string,
  batch: ParallelScalingBatchPlan,
  seed: number,
  runOrderIndex: number
): ParallelScalingSeedTask {
  const seedLabel = `seed-${seed}`;
  const taskId = seededTaskId(batch.batchId, seed);
  const childRoot = path.join(batchRoot, seedLabel);
  return {
    batchId: batch.batchId,
    taskId,
    runOrderIndex,
    seed,
    configPath: path.join(childRoot, 'config', 'config.properties'),
    outputPath: path.join(childRoot, 'output'),
    logPath: path.join(childRoot, 'logs', 'model.log')
  };
}

function removeHeavyModelOutputFiles(outputPath: string): void {
  if (!fs.existsSync(outputPath)) {
    return;
  }

  for (const entry of fs.readdirSync(outputPath, { withFileTypes: true })) {
    if (entry.isFile() && HEAVY_MODEL_OUTPUT_FILE_PATTERN.test(entry.name)) {
      fs.rmSync(path.join(outputPath, entry.name), { force: true });
    }
  }
}

function normalizeOptions(options: ParallelScalingExperimentOptions, enforceFullConfirmation = false): NormalizedParallelScalingOptions {
  const repoRoot = path.resolve(options.repoRoot);
  const outputRoot = path.resolve(options.outputRoot);
  assertPositiveInteger(options.seedCount, 'seedCount');
  assertPositiveInteger(options.targetPopulation, 'targetPopulation');
  assertPositiveInteger(options.nSteps, 'nSteps');
  assertPositiveInteger(options.repeats, 'repeats');
  if (!Number.isFinite(options.orderingSeed) || !Number.isInteger(options.orderingSeed)) {
    throw new Error('orderingSeed must be an integer.');
  }
  if (options.phase !== 'pilot' && options.phase !== 'full') {
    throw new Error('phase must be pilot or full.');
  }
  if (enforceFullConfirmation && options.phase === 'full' && options.confirmExpensive !== true) {
    throw new Error('Full parallel scaling phase is expensive; pass confirmExpensive to run it.');
  }
  return {
    repoRoot,
    outputRoot,
    snapshot: requireNonEmpty(options.snapshot, 'snapshot'),
    baseMode: requireNonEmpty(options.baseMode, 'baseMode'),
    workerCounts: parseWorkerCounts(options.workerCounts),
    seedCount: options.seedCount,
    targetPopulation: options.targetPopulation,
    nSteps: options.nSteps,
    repeats: options.repeats,
    orderingSeed: String(options.orderingSeed),
    orderingSeedValue: options.orderingSeed,
    phase: options.phase,
    javaOptions: [...(options.javaOptions ?? [])],
    policyLabel: options.policyLabel?.trim() || ((options.javaOptions ?? []).length > 0 ? 'custom' : 'default')
  };
}

function assertPositiveInteger(value: number, label: string): void {
  if (!Number.isFinite(value) || !Number.isInteger(value) || value <= 0) {
    throw new Error(`${label} must be a positive integer.`);
  }
}

function requireNonEmpty(value: string, label: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error(`${label} must not be empty.`);
  }
  return trimmed;
}

function readPropertyOverrides(filePath: string): Map<string, string> {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Missing mode override config: ${filePath}`);
  }
  const overrides = new Map<string, string>();
  for (const line of fs.readFileSync(filePath, 'utf-8').split(/\r?\n/)) {
    const match = PROPERTY_LINE_PATTERN.exec(line);
    if (!match) {
      continue;
    }
    overrides.set(match[2], stripInlineComment(match[4]).trim());
  }
  return overrides;
}

function rewriteConfig(input: {
  baselineConfigPath: string;
  snapshotRoot: string;
  outputConfigPath: string;
  overrides: Map<string, string>;
}): void {
  if (!fs.existsSync(input.baselineConfigPath)) {
    throw new Error(`Missing baseline config: ${input.baselineConfigPath}`);
  }

  const seenOverrides = new Set<string>();
  const rewritten = fs.readFileSync(input.baselineConfigPath, 'utf-8').split(/\r?\n/).map((line) => {
    const match = PROPERTY_LINE_PATTERN.exec(line);
    if (!match) {
      return line;
    }

    const leading = match[1];
    const key = match[2];
    const separator = match[3];
    const rawValue = match[4];

    const inlineComment = splitInlineComment(rawValue).comment;

    if (input.overrides.has(key)) {
      seenOverrides.add(key);
      return `${leading}${key}${separator}${input.overrides.get(key) as string}${inlineComment}`;
    }

    if (key.startsWith('DATA_')) {
      const fileName = path.basename(unquote(splitInlineComment(rawValue).value.trim()));
      if (!fileName) {
        throw new Error(`Could not rewrite ${key}: baseline value is empty.`);
      }
      const dataPath = path.join(input.snapshotRoot, fileName);
      if (!fs.existsSync(dataPath) || !fs.statSync(dataPath).isFile()) {
        throw new Error(`Could not rewrite ${key}: missing selected snapshot file ${dataPath}`);
      }
      return `${leading}${key}${separator}"${dataPath.replace(/\\/g, '/')}"${inlineComment}`;
    }

    return line;
  });

  for (const key of input.overrides.keys()) {
    if (!seenOverrides.has(key)) {
      throw new Error(`Could not apply override ${key} because it is missing from baseline config.`);
    }
  }

  fs.mkdirSync(path.dirname(input.outputConfigPath), { recursive: true });
  fs.writeFileSync(input.outputConfigPath, `${rewritten.join('\n')}\n`, 'utf-8');
}

function stripInlineComment(value: string): string {
  return splitInlineComment(value).value;
}

function splitInlineComment(value: string): { value: string; comment: string } {
  const index = value.indexOf(' #');
  if (index < 0) {
    return { value, comment: '' };
  }
  return {
    value: value.slice(0, index),
    comment: value.slice(index)
  };
}

function unquote(value: string): string {
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  return value;
}

function deterministicShuffle<T>(items: T[], seed: string): T[] {
  const keyed = items.map((item, index) => ({
    item,
    key: createHash('sha256').update(`${seed}\0${index}\0${JSON.stringify(item)}`).digest('hex')
  }));
  keyed.sort((left, right) => left.key.localeCompare(right.key));
  return keyed.map((entry) => entry.item);
}

function createNowProvider(rawNow: ParallelScalingExperimentDependencies['now']): () => Date {
  if (rawNow instanceof Date) {
    return () => new Date(rawNow.getTime());
  }
  if (typeof rawNow === 'function') {
    return rawNow;
  }
  return () => new Date();
}

function elapsedSeconds(startedAt: Date, endedAt: Date): number {
  return Math.max(0, (endedAt.getTime() - startedAt.getTime()) / 1000);
}

function throughputRunsPerHour(completedChildCount: number, wallClockSeconds: number): number {
  if (wallClockSeconds <= 0) {
    return 0;
  }
  return (completedChildCount / wallClockSeconds) * 3600;
}

function createRunId(createdAt: string, options: NormalizedParallelScalingOptions): string {
  const timestamp = createdAt.replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const policyDimensions = options.javaOptions.length > 0 || options.policyLabel !== 'default'
    ? {
        javaOptions: options.javaOptions,
        policyLabel: options.policyLabel
      }
    : {};
  const digest = createHash('sha256')
    .update(JSON.stringify({
      snapshot: options.snapshot,
      baseMode: options.baseMode,
      seedCount: options.seedCount,
      targetPopulation: options.targetPopulation,
      nSteps: options.nSteps,
      repeats: options.repeats,
      workerCounts: options.workerCounts,
      orderingSeed: options.orderingSeedValue,
      phase: options.phase,
      ...policyDimensions
    }))
    .digest('hex')
    .slice(0, 8);
  return `parallel-scaling-${timestamp}-${digest}`;
}

function hostMetadata(): ParallelScalingExperimentResult['host'] {
  return {
    hostname: os.hostname(),
    platform: process.platform,
    arch: process.arch,
    cpuCount: os.cpus().length,
    availableParallelism: typeof os.availableParallelism === 'function' ? os.availableParallelism() : os.cpus().length,
    totalMemoryBytes: os.totalmem()
  };
}

function gitMetadata(repoRoot: string): ParallelScalingExperimentResult['git'] {
  const commit = runGit(repoRoot, ['rev-parse', 'HEAD']);
  const branch = runGit(repoRoot, ['rev-parse', '--abbrev-ref', 'HEAD']);
  const status = runGit(repoRoot, ['status', '--porcelain']);
  return {
    commit,
    branch,
    dirty: status === null ? null : status.length > 0
  };
}

function runGit(repoRoot: string, args: string[]): string | null {
  const result = spawnSync('git', args, { cwd: repoRoot, encoding: 'utf-8' });
  if (result.error || result.status !== 0) {
    return null;
  }
  return result.stdout.trim();
}

function writeArtifacts(result: ParallelScalingExperimentResult): void {
  fs.mkdirSync(result.runRoot, { recursive: true });
  fs.writeFileSync(result.artifacts.childrenCsvPath, toCsv(CHILD_CSV_HEADERS, childrenCsvRows(result)), 'utf-8');
  fs.writeFileSync(result.artifacts.batchesCsvPath, toCsv(BATCH_CSV_HEADERS, batchCsvRows(result)), 'utf-8');
  fs.writeFileSync(result.artifacts.rawJsonPath, `${JSON.stringify(result, null, 2)}\n`, 'utf-8');
}

function childrenCsvRows(result: ParallelScalingExperimentResult): Array<Record<string, string | number>> {
  return result.batches
    .slice()
    .sort((left, right) => left.runOrderIndex - right.runOrderIndex)
    .flatMap((batch) =>
      batch.children
        .slice()
        .sort((left, right) => left.seed - right.seed)
        .map((child) => ({
          run_id: result.runId,
          batch_id: batch.batchId,
          phase: batch.phase,
          worker_count: batch.workerCount,
          effective_worker_count: batch.effectiveWorkerCount,
          repeat_index: batch.repeatIndex,
          run_order_index: batch.runOrderIndex,
          seed: child.seed,
          task_id: child.taskId,
          worker_index: child.workerIndex,
          status: child.status,
          started_at: child.startedAt,
          ended_at: child.endedAt,
          wall_clock_seconds: child.wallClockSeconds,
          config_path: child.configPath,
          output_path: child.outputPath,
          error: child.error ?? ''
        }))
    );
}

function batchCsvRows(result: ParallelScalingExperimentResult): Array<Record<string, string | number>> {
  return result.batches
    .slice()
    .sort((left, right) => left.runOrderIndex - right.runOrderIndex)
    .map((batch) => ({
      run_id: result.runId,
      batch_id: batch.batchId,
      phase: batch.phase,
      worker_count: batch.workerCount,
      effective_worker_count: batch.effectiveWorkerCount,
      repeat_index: batch.repeatIndex,
      run_order_index: batch.runOrderIndex,
      seed_count: batch.seedCount,
      status: batch.status,
      started_at: batch.startedAt,
      ended_at: batch.endedAt,
      wall_clock_seconds: batch.wallClockSeconds,
      completed_child_count: batch.completedChildCount,
      failed_child_count: batch.failedChildCount,
      canceled_child_count: batch.canceledChildCount,
      throughput_runs_per_hour: batch.throughputRunsPerHour
    }));
}

function toCsv(
  headers: readonly string[],
  rows: Array<Record<string, string | number>>
): string {
  const lines = [
    headers.join(','),
    ...rows.map((row) => headers.map((header) => csvCell(row[header])).join(','))
  ];
  return `${lines.join('\n')}\n`;
}

function csvCell(value: string | number | undefined): string {
  const raw = value === undefined ? '' : String(value);
  return /[",\n\r]/.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw;
}
