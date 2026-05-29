// Author: Max Stoddard
import assert from 'node:assert/strict';
import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { PassThrough } from 'node:stream';
import { fileURLToPath } from 'node:url';
import type { ModelLauncher, ModelLaunchRequest } from '../server/lib/modelLauncher.js';
import {
  parseArgs as parseParallelScalingCliArgs,
  toExperimentOptions as toParallelScalingExperimentOptions,
  usage as parallelScalingCliUsage
} from '../server/parallelScalingReportCli.js';
import {
  buildBatchPlan,
  materializeParallelScalingConfig,
  parseWorkerCounts,
  runParallelScalingExperiment,
  type ParallelScalingBatchResult,
  type ParallelScalingChildResult,
  type ParallelScalingExperimentOptions
} from '../server/lib/parallelScalingReport.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../..');
const expectedChildCsvHeader =
  'run_id,batch_id,phase,worker_count,effective_worker_count,repeat_index,run_order_index,seed,task_id,worker_index,status,started_at,ended_at,wall_clock_seconds,config_path,output_path,error';
const expectedBatchCsvHeader =
  'run_id,batch_id,phase,worker_count,effective_worker_count,repeat_index,run_order_index,seed_count,status,started_at,ended_at,wall_clock_seconds,completed_child_count,failed_child_count,canceled_child_count,throughput_runs_per_hour';

type ExactEqual<Left, Right> =
  (<Value>() => Value extends Left ? 1 : 2) extends (<Value>() => Value extends Right ? 1 : 2)
    ? (<Value>() => Value extends Right ? 1 : 2) extends (<Value>() => Value extends Left ? 1 : 2)
      ? true
      : false
    : false;
type AssertExact<T extends true> = T;

interface ExpectedParallelScalingExperimentOptions {
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

interface ExpectedParallelScalingChildResult {
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

interface ExpectedParallelScalingBatchResult {
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

type _OptionsContract = AssertExact<
  ExactEqual<ParallelScalingExperimentOptions, ExpectedParallelScalingExperimentOptions>
>;
type _ChildContract = AssertExact<ExactEqual<ParallelScalingChildResult, ExpectedParallelScalingChildResult>>;
type _BatchContract = AssertExact<ExactEqual<ParallelScalingBatchResult, ExpectedParallelScalingBatchResult>>;
const interfaceContracts: [_OptionsContract, _ChildContract, _BatchContract] = [true, true, true];
void interfaceContracts;

interface ParsedConfig {
  values: Map<string, string>;
  dataPaths: string[];
}

class FakeModelProcess extends EventEmitter {
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();

  constructor(exitCode: number, delayMs: number) {
    super();
    setTimeout(() => {
      this.stdout.write('Simulation: 1, time: 1\n');
      this.stdout.end();
      this.stderr.end();
      this.emit('close', exitCode, null);
    }, delayMs);
  }
}

class FakeLauncher implements ModelLauncher {
  readonly mode = 'maven' as const;
  readonly metadata = {
    mode: 'maven' as const,
    commandTemplate: 'fake model launcher'
  };
  readonly requests: ModelLaunchRequest[] = [];
  prepareCalls = 0;
  active = 0;
  peakConcurrency = 0;

  constructor(private readonly failSeeds = new Set<number>()) {}

  prepare(): void {
    this.prepareCalls += 1;
  }

  buildCommand() {
    return {
      command: 'fake',
      args: [],
      options: { cwd: repoRoot, shell: false },
      commandTemplate: 'fake model launcher'
    };
  }

  launch(request: ModelLaunchRequest): ChildProcessWithoutNullStreams {
    this.requests.push(request);
    this.active += 1;
    this.peakConcurrency = Math.max(this.peakConcurrency, this.active);
    const config = parseConfig(request.configPath);
    const seed = Number(config.values.get('SEED'));
    const child = new FakeModelProcess(this.failSeeds.has(seed) ? 1 : 0, 10);
    child.on('close', () => {
      this.active -= 1;
      fs.mkdirSync(request.outputPath, { recursive: true });
      fs.writeFileSync(path.join(request.outputPath, 'Output-run1.csv'), 'Model time;Value\n1;1\n', 'utf-8');
    });
    return child as unknown as ChildProcessWithoutNullStreams;
  }
}

function parseConfig(configPath: string): ParsedConfig {
  const values = new Map<string, string>();
  const dataPaths: string[] = [];
  for (const line of fs.readFileSync(configPath, 'utf-8').split(/\r?\n/)) {
    const match = /^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$/.exec(line);
    if (!match) {
      continue;
    }
    const rawValue = match[2].replace(/\s+#.*$/, '').trim();
    const value = rawValue.replace(/^["']|["']$/g, '');
    values.set(match[1], value);
    if (match[1].startsWith('DATA_')) {
      dataPaths.push(value);
    }
  }
  return { values, dataPaths };
}

function makeOptions(outputRoot: string, overrides: Partial<ParallelScalingExperimentOptions> = {}): ParallelScalingExperimentOptions {
  return {
    repoRoot,
    snapshot: 'v0',
    baseMode: 'core-minimal-20k-s1',
    outputRoot,
    targetPopulation: 1234,
    nSteps: 7,
    seedCount: 3,
    workerCounts: [1, 2, 4],
    repeats: 1,
    orderingSeed: 101,
    phase: 'pilot',
    ...overrides
  };
}

function makeTempReportRoot(): string {
  const parent = path.join(os.tmpdir(), 'tmp', '_report');
  fs.mkdirSync(parent, { recursive: true });
  return fs.mkdtempSync(path.join(parent, 'parallel-scaling-report-test-'));
}

async function withTempReportRoot<T>(fn: (outputRoot: string) => Promise<T> | T): Promise<T> {
  const outputRoot = makeTempReportRoot();
  try {
    return await fn(outputRoot);
  } finally {
    fs.rmSync(outputRoot, { recursive: true, force: true });
  }
}

assert.deepEqual(
  parseWorkerCounts(undefined),
  [1, 2, 4, 8, 12, 16, 20, 24, 32],
  'Expected the default full worker ladder to remain stable'
);
assert.throws(() => parseWorkerCounts('1,2,2'), /duplicate worker count/i);
assert.throws(() => parseWorkerCounts('1,0,2'), /positive integer/i);

{
  const left = buildBatchPlan(makeOptions('/tmp/report-a', { orderingSeed: 11 })).map((batch) => batch.batchId);
  const right = buildBatchPlan(makeOptions('/tmp/report-b', { orderingSeed: 11 })).map((batch) => batch.batchId);
  const changed = buildBatchPlan(makeOptions('/tmp/report-c', { orderingSeed: 12 })).map((batch) => batch.batchId);
  assert.deepEqual(left, right, 'Expected same inputs to produce identical run order');
  assert.notDeepEqual(left, changed, 'Expected orderingSeed to change deterministic run order');
}

{
  const plan = buildBatchPlan(makeOptions('/tmp/report', { seedCount: 3, workerCounts: [1, 4, 32] }));
  assert.deepEqual(
    plan
      .map((batch) => [batch.workerCount, batch.effectiveWorkerCount])
      .sort((left, right) => left[0] - right[0]),
    [
      [1, 1],
      [4, 3],
      [32, 3]
    ],
    'Expected effective workers to be capped by seedCount'
  );
}

await withTempReportRoot(async (outputRoot) => {
  const configPaths = [1, 2, 3].map((seed) => {
    const configPath = path.join(outputRoot, `seed-${seed}`, 'config.properties');
    materializeParallelScalingConfig({
      repoRoot,
      snapshot: 'v0',
      baseMode: 'core-minimal-20k-s1',
      targetPopulation: 4321,
      nSteps: 11,
      seed,
      outputConfigPath: configPath
    });
    return configPath;
  });

  const parsedConfigs = configPaths.map(parseConfig);
  assert.deepEqual(
    parsedConfigs.map((config) => config.values.get('SEED')),
    ['1', '2', '3'],
    'Expected materialized configs to pin unique SEED values'
  );
  for (const parsed of parsedConfigs) {
    assert.equal(parsed.values.get('N_SIMS'), '1', 'Expected report configs to force N_SIMS=1');
    assert.equal(parsed.values.get('TARGET_POPULATION'), '4321', 'Expected targetPopulation override to apply');
    assert.equal(parsed.values.get('N_STEPS'), '11', 'Expected nSteps override to apply');
    assert.ok(parsed.dataPaths.length > 0, 'Expected config to include DATA_* paths');
    for (const dataPath of parsed.dataPaths) {
      assert.ok(path.isAbsolute(dataPath), `Expected DATA_* path to be absolute: ${dataPath}`);
      assert.ok(
        dataPath.startsWith(path.join(repoRoot, 'input-data-versions', 'v0') + path.sep),
        `Expected DATA_* path under input-data-versions/v0: ${dataPath}`
      );
    }
  }

  const baselinePath = path.join(outputRoot, 'broken-baseline.properties');
  fs.writeFileSync(baselinePath, 'SEED = 1\nN_STEPS = 1\nN_SIMS = 1\n', 'utf-8');
  assert.throws(
    () =>
      materializeParallelScalingConfig({
        repoRoot,
        snapshot: 'v0',
        baseMode: 'core-minimal-20k-s1',
        targetPopulation: 100,
        nSteps: 1,
        seed: 1,
        outputConfigPath: path.join(outputRoot, 'broken-config.properties'),
        baselineConfigPath: baselinePath
      }),
    /missing from baseline config.*TARGET_POPULATION|TARGET_POPULATION.*missing from baseline config/i,
    'Expected missing override keys to fail clearly'
  );
});

await withTempReportRoot(async (outputRoot) => {
  const launcher = new FakeLauncher();
  const result = await runParallelScalingExperiment(makeOptions(outputRoot, { workerCounts: [8], seedCount: 3 }), {
    launcher,
    now: new Date('2025-01-01T00:00:00.000Z')
  });

  assert.equal(launcher.prepareCalls, 1, 'Expected launcher.prepare to be called once');
  assert.equal(launcher.peakConcurrency <= 3, true, 'Expected fake launcher concurrency to stay within effective workers');
  assert.equal(result.workload.phase, 'pilot', 'Expected result workload to record phase');
  assert.equal(result.batches[0].phase, 'pilot', 'Expected batch result to record phase');
  assert.equal(result.batches[0].effectiveWorkerCount, 3, 'Expected result to record capped effective worker count');
  assert.equal(result.batches[0].completedChildCount, 3, 'Expected batch result to count completed children');
  assert.equal(result.batches[0].failedChildCount, 0, 'Expected batch result to count failed children');
  assert.equal(result.batches[0].canceledChildCount, 0, 'Expected batch result to count canceled children');
  assert.equal(
    Number.isFinite(result.batches[0].throughputRunsPerHour),
    true,
    'Expected batch throughput to be finite'
  );
  assert.ok(
    result.batches[0].children.every((child) => child.workerIndex >= 1),
    'Expected worker indices to be recorded as 1-based'
  );
  assert.ok(
    result.batches[0].children.every((child) => child.configPath.includes(`${path.sep}tmp${path.sep}_report${path.sep}`)),
    'Expected child configs to be written under tmp/_report'
  );
  assert.ok(
    result.batches[0].children.every((child) => child.outputPath.includes(`${path.sep}tmp${path.sep}_report${path.sep}`)),
    'Expected child outputs to be written under tmp/_report'
  );
  assert.ok(
    result.batches[0].children.every((child) => !child.outputPath.includes(`${path.sep}Results${path.sep}`)),
    'Expected report output paths not to use Results'
  );
  assert.ok(
    result.batches[0].children.every((child) => !fs.existsSync(path.join(child.outputPath, 'Output-run1.csv'))),
    'Expected parallel scaling seed outputs to remove heavy model Output-run CSV files'
  );
  assert.equal(
    path.basename(result.artifacts.childrenCsvPath),
    'parallel_scaling_children.csv',
    'Expected planned children CSV artifact name'
  );
  assert.equal(
    path.basename(result.artifacts.batchesCsvPath),
    'parallel_scaling_batches.csv',
    'Expected planned batches CSV artifact name'
  );
  assert.equal(
    path.basename(result.artifacts.rawJsonPath),
    'parallel_scaling_raw.json',
    'Expected planned raw JSON artifact name'
  );
  assert.equal(path.basename(path.dirname(result.artifacts.rawJsonPath)), result.runId, 'Expected artifacts under run id');
  assert.ok(fs.existsSync(result.artifacts.childrenCsvPath), 'Expected children CSV artifact to be written');
  assert.ok(fs.existsSync(result.artifacts.batchesCsvPath), 'Expected batches CSV artifact to be written');
  assert.ok(fs.existsSync(result.artifacts.rawJsonPath), 'Expected raw JSON artifact to be written');
  assert.equal(
    fs.readFileSync(result.artifacts.childrenCsvPath, 'utf-8').split(/\r?\n/)[0],
    expectedChildCsvHeader,
    'Expected planned children CSV header'
  );
  assert.equal(
    fs.readFileSync(result.artifacts.batchesCsvPath, 'utf-8').split(/\r?\n/)[0],
    expectedBatchCsvHeader,
    'Expected planned batches CSV header'
  );
  assert.deepEqual(result.workload.javaOptions, [], 'Expected default runs to record empty JVM options');
  assert.equal(result.workload.policyLabel, 'default', 'Expected default runs to record the default policy label');
});

await withTempReportRoot(async (outputRoot) => {
  const launcher = new FakeLauncher();
  const apcResult = await runParallelScalingExperiment(
    makeOptions(outputRoot, {
      workerCounts: [2],
      seedCount: 3,
      javaOptions: ['-XX:ActiveProcessorCount=1'],
      policyLabel: 'APC1'
    }),
    { launcher, now: new Date('2025-01-01T00:00:00.000Z') }
  );
  assert.deepEqual(
    launcher.requests.map((request) => request.javaOptions),
    [
      ['-XX:ActiveProcessorCount=1'],
      ['-XX:ActiveProcessorCount=1'],
      ['-XX:ActiveProcessorCount=1']
    ],
    'Expected APC1 JVM option to propagate to every child launch'
  );
  assert.deepEqual(apcResult.workload.javaOptions, ['-XX:ActiveProcessorCount=1']);
  assert.equal(apcResult.workload.policyLabel, 'APC1');
  const persistedApcResult = JSON.parse(fs.readFileSync(apcResult.artifacts.rawJsonPath, 'utf-8')) as {
    workload: { javaOptions: string[]; policyLabel: string };
  };
  assert.deepEqual(
    persistedApcResult.workload.javaOptions,
    ['-XX:ActiveProcessorCount=1'],
    'Expected raw JSON artifact to persist APC1 JVM options'
  );
  assert.equal(
    persistedApcResult.workload.policyLabel,
    'APC1',
    'Expected raw JSON artifact to persist APC1 policy label'
  );
});

await withTempReportRoot(async (outputRoot) => {
  const now = new Date('2025-01-01T00:00:00.000Z');
  const sharedOptions = {
    workerCounts: [1],
    seedCount: 1,
    targetPopulation: 1234,
    nSteps: 7,
    repeats: 1,
    orderingSeed: 101,
    phase: 'pilot' as const
  };
  const defaultResult = await runParallelScalingExperiment(makeOptions(outputRoot, sharedOptions), {
    launcher: new FakeLauncher(),
    now
  });
  const customResult = await runParallelScalingExperiment(
    makeOptions(outputRoot, {
      ...sharedOptions,
      javaOptions: ['--enable-preview']
    }),
    {
      launcher: new FakeLauncher(),
      now
    }
  );

  assert.equal(defaultResult.workload.policyLabel, 'default', 'Expected no JVM options to use default policy label');
  assert.equal(customResult.workload.policyLabel, 'custom', 'Expected unlabeled JVM options to use custom policy label');
  assert.notEqual(
    defaultResult.runId,
    customResult.runId,
    'Expected runs with different JVM policy dimensions to have distinct run ids'
  );
});

await withTempReportRoot(async (outputRoot) => {
  const launcher = new FakeLauncher(new Set([2]));
  const result = await runParallelScalingExperiment(makeOptions(outputRoot, { workerCounts: [1, 2], seedCount: 3 }), {
    launcher,
    now: new Date('2025-01-01T00:00:00.000Z')
  });
  const failedBatch = result.batches.find((batch) => batch.status === 'failed');
  assert.ok(failedBatch, 'Expected a failed child to mark its batch failed');
  assert.equal(failedBatch.failedChildCount, 1, 'Expected failed batch to count failed children');
  assert.ok(
    result.analysis.excludedBatchIds.includes(failedBatch.batchId),
    'Expected failed batch to be recorded in analysis exclusions'
  );
  assert.ok(
    !result.analysis.includedBatchIds.includes(failedBatch.batchId),
    'Expected failed batch to be absent from analysis inclusions'
  );
  const failedBatchIndex = result.batches.indexOf(failedBatch);
  assert.equal(
    result.batches.length,
    failedBatchIndex + 1,
    'Expected the experiment to stop launching later batches after a failed batch'
  );
});

{
  const help = parallelScalingCliUsage();
  assert.match(help, /--phase <pilot\|full>/, 'Expected CLI help to document pilot/full phases');
  assert.match(help, /--workers <comma-separated counts>/, 'Expected CLI help to document --workers');
  assert.match(help, /Pilot example:/, 'Expected CLI help to include a pilot example');
  assert.match(help, /Full example:/, 'Expected CLI help to include a full example');
}

{
  assert.throws(
    () =>
      toParallelScalingExperimentOptions(
        parseParallelScalingCliArgs([
          '--phase',
          'full',
          '--snapshot',
          'v0',
          '--base-mode',
          'core-minimal-20k-s1',
          '--target-population',
          '5000',
          '--n-steps',
          '2000',
          '--seed-count',
          '40',
          '--workers',
          '1,2',
          '--repeats',
          '3',
          '--ordering-seed',
          '20260527',
          '--output-root',
          path.join(os.tmpdir(), 'tmp', '_report')
        ])
      ),
    /--confirm-expensive/,
    'Expected full phase to refuse without --confirm-expensive'
  );

  const fullWithConfirmation = toParallelScalingExperimentOptions(
    parseParallelScalingCliArgs([
      '--phase',
      'full',
      '--snapshot',
      'v0',
      '--base-mode',
      'core-minimal-20k-s1',
      '--target-population',
      '5000',
      '--n-steps',
      '2000',
      '--seed-count',
      '40',
      '--workers',
      '1,2',
      '--repeats',
      '3',
      '--ordering-seed',
      '20260527',
      '--output-root',
      path.join(os.tmpdir(), 'tmp', '_report'),
      '--confirm-expensive'
    ])
  );
  assert.equal(fullWithConfirmation.phase, 'full', 'Expected confirmed full CLI args to map to full phase');
  assert.deepEqual(fullWithConfirmation.workerCounts, [1, 2], 'Expected --workers to parse worker counts');
  assert.equal(fullWithConfirmation.confirmExpensive, true, 'Expected confirmed full CLI args to set confirmExpensive');

  const apcOptions = toParallelScalingExperimentOptions(
    parseParallelScalingCliArgs([
      '--phase',
      'full',
      '--snapshot',
      'v0',
      '--base-mode',
      'core-minimal-20k-s1',
      '--target-population',
      '5000',
      '--n-steps',
      '2000',
      '--seed-count',
      '40',
      '--workers',
      '1,2',
      '--repeats',
      '3',
      '--ordering-seed',
      '20260527',
      '--output-root',
      path.join(os.tmpdir(), 'tmp', '_report'),
      '--java-option',
      '-XX:ActiveProcessorCount=1',
      '--policy-label',
      'APC1',
      '--confirm-expensive'
    ])
  );
  assert.deepEqual(apcOptions.javaOptions, ['-XX:ActiveProcessorCount=1']);
  assert.equal(apcOptions.policyLabel, 'APC1');

  const repeatedJavaOptionOptions = toParallelScalingExperimentOptions(
    parseParallelScalingCliArgs([
      '--phase',
      'full',
      '--snapshot',
      'v0',
      '--base-mode',
      'core-minimal-20k-s1',
      '--target-population',
      '5000',
      '--n-steps',
      '2000',
      '--seed-count',
      '40',
      '--workers',
      '1,2',
      '--repeats',
      '3',
      '--ordering-seed',
      '20260527',
      '--output-root',
      path.join(os.tmpdir(), 'tmp', '_report'),
      '--java-option',
      '--add-opens=java.base/java.lang=ALL-UNNAMED',
      '--java-option',
      '--enable-preview',
      '--confirm-expensive'
    ])
  );
  assert.deepEqual(
    repeatedJavaOptionOptions.javaOptions,
    ['--add-opens=java.base/java.lang=ALL-UNNAMED', '--enable-preview'],
    'Expected repeated --java-option values to preserve JVM options that start with --'
  );
}
