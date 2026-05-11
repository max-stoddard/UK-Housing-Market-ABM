import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import type {
  ModelRunJob,
  ModelRunJobClearResponse,
  ModelRunJobLogsPayload,
  ModelRunJobStatus,
  ModelRunOptionsPayload,
  ModelRunParameterDefinition,
  ModelRunParameterGroup,
  ModelRunParameterType,
  ModelRunSnapshotOption,
  ResultsStorageSummary,
  ModelRunSubmitRequest,
  ModelRunSubmitResponse,
  ModelRunWarning
} from '../../shared/types';
import { getInProgressVersions, getVersions } from './service';
import {
  appendLogLine,
  appendOutputChunk,
  flushPartialLine,
  readLogSlice,
  type LogBufferState,
  type LogLineSink
} from './logs/logBuffer';
import {
  createMavenModelLauncher,
  getConfiguredMavenBin,
  type ModelLauncher,
  type ModelLauncherCommand
} from './modelLauncher';
import {
  formatRuntimePath,
  resolveRuntimePaths,
  type RuntimePathInput,
  type RuntimePaths
} from './runtimePaths';
import {
  RUN_MANIFEST_FILE_NAME,
  hashDirectory,
  writeManualRunManifest
} from './runManifest';
import {
  MANAGED_RUN_MARKER,
  isDashboardManagedRun,
  writeDashboardManagedRunMarker
} from './runOwnership';

const TMP_RUNS_DIR = 'dashboard-model-runs';
const MAX_QUEUE_SIZE = 10;
const MAX_LOG_LINES = 10_000;
const CANCEL_KILL_TIMEOUT_MS = 10_000;
const DEFAULT_RESULTS_CAP_MB = 400;

type ParameterDefinitionSeed = {
  key: string;
  title: string;
  description: string;
  group: ModelRunParameterGroup;
  type: ModelRunParameterType;
};

const USER_SET_PARAMETER_DEFS: ParameterDefinitionSeed[] = [
  {
    key: 'SEED',
    title: 'Seed',
    description: 'Seed for the random number generator.',
    group: 'General model control',
    type: 'integer'
  },
  {
    key: 'N_STEPS',
    title: 'Simulation duration (steps)',
    description: 'Simulation duration in model time steps.',
    group: 'General model control',
    type: 'integer'
  },
  {
    key: 'N_SIMS',
    title: 'Monte Carlo runs',
    description: 'Number of simulations to run.',
    group: 'General model control',
    type: 'integer'
  },
  {
    key: 'TARGET_POPULATION',
    title: 'Target population',
    description: 'Target number of households.',
    group: 'General model control',
    type: 'integer'
  },
  {
    key: 'TIME_TO_START_RECORDING_TRANSACTIONS',
    title: 'Transaction recording start time',
    description: 'Time step to start recording transaction micro-data.',
    group: 'General model control',
    type: 'integer'
  },
  {
    key: 'ROLLING_WINDOW_SIZE_FOR_CORE_INDICATORS',
    title: 'Core indicator rolling window',
    description: 'Window size in months for core indicator averages.',
    group: 'General model control',
    type: 'integer'
  },
  {
    key: 'CUMULATIVE_WEIGHT_BEYOND_YEAR',
    title: 'Cumulative weight beyond year',
    description: 'Weight assigned to events older than 12 months.',
    group: 'General model control',
    type: 'number'
  },
  {
    key: 'recordTransactions',
    title: 'Record transactions',
    description: 'Write data for each transaction.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordNBidUpFrequency',
    title: 'Record bid-up frequency',
    description: 'Write bid-up frequency data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordCoreIndicators',
    title: 'Record core indicators',
    description: 'Write core indicator time series.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordQualityBandPrice',
    title: 'Record quality-band prices',
    description: 'Write quality-band price time series.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordHouseholdID',
    title: 'Record household ID',
    description: 'Write household identifiers.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordEmploymentIncome',
    title: 'Record employment income',
    description: 'Write household gross employment income data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordRentalIncome',
    title: 'Record rental income',
    description: 'Write household gross rental income data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordBankBalance',
    title: 'Record bank balance',
    description: 'Write household bank balance data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordHousingWealth',
    title: 'Record housing wealth',
    description: 'Write household housing wealth data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordTotalDebt',
    title: 'Record total debt',
    description: 'Write household total debt data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordHousingStatus',
    title: 'Record housing status',
    description: 'Write household housing status data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordConsumption',
    title: 'Record non-housing consumption',
    description: 'Write household non-housing consumption data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordNHousesOwned',
    title: 'Record number of houses owned',
    description: 'Write household number-of-houses-owned data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordAge',
    title: 'Record household age',
    description: 'Write household representative age data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'recordSavingRate',
    title: 'Record saving rate',
    description: 'Write household saving-rate data.',
    group: 'General model control',
    type: 'boolean'
  },
  {
    key: 'CENTRAL_BANK_INITIAL_BASE_RATE',
    title: 'Initial base rate',
    description: 'Central bank initial base rate.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_LTV_HARD_MAX_FTB',
    title: 'Hard max LTV FTB',
    description: 'Hard maximum LTV ratio for first-time buyers.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_LTV_HARD_MAX_HM',
    title: 'Hard max LTV HM',
    description: 'Hard maximum LTV ratio for home movers.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_LTV_HARD_MAX_BTL',
    title: 'Hard max LTV BTL',
    description: 'Hard maximum LTV ratio for buy-to-let investors.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_LTI_SOFT_MAX_FTB',
    title: 'Soft max LTI FTB',
    description: 'Soft maximum LTI ratio for first-time buyers.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_LTI_SOFT_MAX_HM',
    title: 'Soft max LTI HM',
    description: 'Soft maximum LTI ratio for home movers.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB',
    title: 'Max fraction over soft max LTI FTB',
    description: 'Maximum mortgage fraction over FTB soft LTI.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM',
    title: 'Max fraction over soft max LTI HM',
    description: 'Maximum mortgage fraction over HM soft LTI.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_LTI_MONTHS_TO_CHECK',
    title: 'LTI months-to-check',
    description: 'Months checked for moving average over soft LTI.',
    group: 'Central Bank policy',
    type: 'integer'
  },
  {
    key: 'CENTRAL_BANK_AFFORDABILITY_HARD_MAX',
    title: 'Hard max affordability',
    description: 'Hard max share of income spent on mortgage repayments.',
    group: 'Central Bank policy',
    type: 'number'
  },
  {
    key: 'CENTRAL_BANK_ICR_HARD_MIN',
    title: 'Hard min ICR',
    description: 'Hard minimum expected rental-income to interest coverage.',
    group: 'Central Bank policy',
    type: 'number'
  }
];

const TERMINAL_STATUSES = new Set<ModelRunJobStatus>(['succeeded', 'failed', 'canceled']);

type ParsedOverride = {
  typed: number | boolean;
  serialized: string;
};

interface ModelRunJobInternal {
  job: ModelRunJob;
  runtimePaths: RuntimePaths;
  warnings: ModelRunWarning[];
  logBuffer: LogBufferState;
  process?: ChildProcessWithoutNullStreams;
  launcher: ModelLauncher;
  cancelRequested: boolean;
  killTimer?: NodeJS.Timeout;
  tempDirPath: string;
  configAbsolutePath: string;
  runAbsolutePath: string;
  seed: number | null;
  overriddenParameters: Record<string, number | boolean>;
  ignoreStorageCap: boolean;
}

interface SubmitModelRunOptions {
  ignoreStorageCap?: boolean;
  launcher?: ModelLauncher;
  logSink?: LogLineSink;
}

interface PrepareModelRunSubmissionOptions {
  ignoreStorageCap?: boolean;
  now?: Date;
}

interface PreparedModelRunSubmission {
  baseline: string;
  title?: string;
  runId: string;
  jobId: string;
  createdAt: string;
  warnings: ModelRunWarning[];
  tempDirPath: string;
  configAbsolutePath: string;
  runAbsolutePath: string;
  baselineConfigPath: string;
  baselineDirPath: string;
  normalizedOverrides: Map<string, string>;
  valuesByKey: Map<string, number | boolean>;
  overriddenParameters: Record<string, number | boolean>;
  ignoreStorageCap: boolean;
}

type SpawnModelRunFn = (
  repoRoot: string,
  configPath: string,
  outputPath: string
) => ChildProcessWithoutNullStreams;

const jobsById = new Map<string, ModelRunJobInternal>();
const jobOrder: string[] = [];
let runningJobId: string | null = null;
let shutdownRequested = false;
const defaultModelLauncher = createMavenModelLauncher();
let modelRunLauncherOverrideForTests: ModelLauncher | null = null;

function createSpawnFunctionLauncher(spawnFn: SpawnModelRunFn): ModelLauncher {
  return {
    mode: 'maven',
    metadata: {
      mode: 'maven',
      commandTemplate: 'test model launcher'
    },
    buildCommand: (request): ModelLauncherCommand => ({
      command: 'test-model-launcher',
      args: [request.configPath, request.outputPath],
      options: {
        cwd: request.repoRoot
      },
      commandTemplate: 'test model launcher'
    }),
    launch: (request) => spawnFn(request.repoRoot, request.configPath, request.outputPath)
  };
}

function resolveModelLauncher(launcher: ModelLauncher | undefined): ModelLauncher {
  return launcher ?? modelRunLauncherOverrideForTests ?? defaultModelLauncher;
}

function formatLauncherProcessError(launcher: ModelLauncher, error: Error): string {
  const spawnError = error as NodeJS.ErrnoException;
  if (spawnError.code !== 'ENOENT') {
    return error.message;
  }

  if (launcher.mode === 'maven') {
    const mavenBin = launcher.metadata.mavenBin ?? getConfiguredMavenBin();
    return `Maven executable "${mavenBin}" was not found. Configure DASHBOARD_MAVEN_BIN or run the API in an environment with Java+Maven (e.g. Docker runtime).`;
  }

  const javaExe = launcher.metadata.javaExe ?? 'java';
  return `Java executable "${javaExe}" was not found for packaged model launcher.`;
}

function isTerminal(status: ModelRunJobStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

function toRuntimePath(paths: RuntimePaths, absolutePath: string): string {
  return formatRuntimePath(paths, absolutePath);
}

function parseConfigAssignments(configPath: string): Map<string, string> {
  const lines = fs.readFileSync(configPath, 'utf-8').split(/\r?\n/);
  const values = new Map<string, string>();

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    const match = /^([A-Za-z0-9_]+)\s*=\s*(.+)$/.exec(trimmed);
    if (!match) {
      continue;
    }

    const rawValue = stripInlineComment(match[2]).trim();
    values.set(match[1], unquote(rawValue));
  }

  return values;
}

function unquote(value: string): string {
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  return value;
}

function stripInlineComment(value: string): string {
  const index = value.indexOf(' #');
  if (index >= 0) {
    return value.slice(0, index);
  }
  return value;
}

function parseTypedConfigValue(raw: string, type: ModelRunParameterType, key: string): number | boolean {
  if (type === 'boolean') {
    if (raw === 'true') {
      return true;
    }
    if (raw === 'false') {
      return false;
    }
    throw new Error(`Config value for ${key} is not boolean: ${raw}`);
  }

  const parsed = Number.parseFloat(raw);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Config value for ${key} is not numeric: ${raw}`);
  }

  if (type === 'integer' && !Number.isInteger(parsed)) {
    throw new Error(`Config value for ${key} is not an integer: ${raw}`);
  }

  return parsed;
}

function normalizeOverrideValue(key: string, raw: unknown, type: ModelRunParameterType): ParsedOverride {
  if (type === 'boolean') {
    if (typeof raw === 'boolean') {
      return { typed: raw, serialized: raw ? 'true' : 'false' };
    }
    if (raw === 'true' || raw === 'false') {
      const boolValue = raw === 'true';
      return { typed: boolValue, serialized: raw };
    }
    throw new Error(`Override ${key} must be boolean.`);
  }

  if (typeof raw !== 'number' || !Number.isFinite(raw)) {
    throw new Error(`Override ${key} must be numeric.`);
  }

  if (type === 'integer' && !Number.isInteger(raw)) {
    throw new Error(`Override ${key} must be an integer.`);
  }

  return { typed: raw, serialized: String(raw) };
}

function buildSnapshotOptions(pathsInput: RuntimePathInput): {
  snapshots: ModelRunSnapshotOption[];
  defaultBaseline: string;
} {
  const paths = resolveRuntimePaths(pathsInput);
  const versions = getVersions(paths);
  if (versions.length === 0) {
    throw new Error('No input-data-versions snapshots are available.');
  }

  const inProgressSet = new Set(getInProgressVersions(paths));
  const snapshots = versions
    .map((version) => ({
      version,
      status: inProgressSet.has(version) ? 'in_progress' : 'stable'
    } satisfies ModelRunSnapshotOption))
    .reverse();

  const defaultBaseline = versions.includes('v0oo') ? 'v0oo' : [...versions].reverse().find((version) => !inProgressSet.has(version)) ?? versions[versions.length - 1];

  return { snapshots, defaultBaseline };
}

function resolveBaseline(pathsInput: RuntimePathInput, requestedBaseline: string | undefined): {
  baseline: string;
  snapshots: ModelRunSnapshotOption[];
  defaultBaseline: string;
} {
  const { snapshots, defaultBaseline } = buildSnapshotOptions(pathsInput);
  if (!requestedBaseline) {
    return { baseline: defaultBaseline, snapshots, defaultBaseline };
  }

  const normalized = requestedBaseline.trim();
  if (!snapshots.some((snapshot) => snapshot.version === normalized)) {
    throw new Error(`Unknown baseline snapshot: ${requestedBaseline}`);
  }

  return { baseline: normalized, snapshots, defaultBaseline };
}

function getBaselineConfigPath(pathsInput: RuntimePathInput, baseline: string): string {
  const paths = resolveRuntimePaths(pathsInput);
  return path.join(paths.dataRoot, baseline, 'config.properties');
}

function getParameterDefinitionsForBaseline(pathsInput: RuntimePathInput, baseline: string): ModelRunParameterDefinition[] {
  const configPath = getBaselineConfigPath(pathsInput, baseline);
  if (!fs.existsSync(configPath)) {
    throw new Error(`Missing config.properties for baseline ${baseline}`);
  }

  const configValues = parseConfigAssignments(configPath);

  return USER_SET_PARAMETER_DEFS.map((definition) => {
    const rawValue = configValues.get(definition.key);
    if (rawValue === undefined) {
      throw new Error(`Baseline ${baseline} is missing USER SET parameter ${definition.key}`);
    }

    return {
      ...definition,
      defaultValue: parseTypedConfigValue(rawValue, definition.type, definition.key)
    };
  });
}

function rewriteConfigForJob(
  baselineConfigPath: string,
  baselineDirPath: string,
  outputConfigPath: string,
  overrides: Map<string, string>
): void {
  const lines = fs.readFileSync(baselineConfigPath, 'utf-8').split(/\r?\n/);
  const seenOverrides = new Set<string>();

  const rewritten = lines.map((line) => {
    const match = /^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*)$/.exec(line);
    if (!match) {
      return line;
    }

    const leading = match[1];
    const key = match[2];
    const separator = match[3];
    const rawValue = match[4];

    if (overrides.has(key)) {
      seenOverrides.add(key);
      return `${leading}${key}${separator}${overrides.get(key) as string}`;
    }

    if (key.startsWith('DATA_')) {
      const stripped = stripInlineComment(rawValue).trim();
      const unquoted = unquote(stripped);
      if (!unquoted) {
        return line;
      }
      const fileName = path.basename(unquoted);
      const candidate = path.join(baselineDirPath, fileName);
      if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
        return `${leading}${key}${separator}"${candidate.replace(/\\/g, '/')}"`;
      }
    }

    return line;
  });

  for (const key of overrides.keys()) {
    if (!seenOverrides.has(key)) {
      throw new Error(`Could not apply override ${key} because it is missing from baseline config.`);
    }
  }

  fs.mkdirSync(path.dirname(outputConfigPath), { recursive: true });
  fs.writeFileSync(outputConfigPath, `${rewritten.join('\n')}\n`, 'utf-8');
}

function createWarnings(valuesByKey: Map<string, number | boolean>): ModelRunWarning[] {
  const warnings: ModelRunWarning[] = [];

  const nSteps = Number(valuesByKey.get('N_STEPS') ?? 0);
  if (nSteps > 4_000) {
    warnings.push({
      code: 'high_n_steps',
      message: `N_STEPS=${nSteps} can significantly increase runtime and output size.`,
      severity: 'warning'
    });
  }

  const targetPopulation = Number(valuesByKey.get('TARGET_POPULATION') ?? 0);
  if (targetPopulation > 15_000) {
    warnings.push({
      code: 'high_target_population',
      message: `TARGET_POPULATION=${targetPopulation} can increase runtime and memory usage.`,
      severity: 'warning'
    });
  }

  const nSims = Number(valuesByKey.get('N_SIMS') ?? 0);
  if (nSims > 1) {
    warnings.push({
      code: 'multiple_simulations',
      message: `N_SIMS=${nSims} runs multiple simulations and may take much longer.`,
      severity: 'warning'
    });
  }

  if (valuesByKey.get('recordTransactions') === true) {
    warnings.push({
      code: 'record_transactions_enabled',
      message: 'recordTransactions=true can produce very large transaction output files.',
      severity: 'warning'
    });
  }

  const microFlags = [
    'recordHouseholdID',
    'recordEmploymentIncome',
    'recordRentalIncome',
    'recordBankBalance',
    'recordHousingWealth',
    'recordTotalDebt',
    'recordHousingStatus',
    'recordConsumption',
    'recordNHousesOwned',
    'recordAge',
    'recordSavingRate'
  ];

  const enabledMicroFlags = microFlags.filter((key) => valuesByKey.get(key) === true);
  if (enabledMicroFlags.length >= 4) {
    warnings.push({
      code: 'heavy_microdata_recording',
      message: `Microdata recording is enabled for ${enabledMicroFlags.length} fields and may create heavy output files.`,
      severity: 'warning'
    });
  }

  if (valuesByKey.get('recordCoreIndicators') === false) {
    warnings.push({
      code: 'core_indicators_disabled',
      message: 'recordCoreIndicators=false means very little data will be visible in Model Results.',
      severity: 'warning'
    });
  }

  return warnings;
}

function ensureQueueCapacity(): void {
  const activeCount = [...jobsById.values()].filter((job) => job.job.status === 'queued' || job.job.status === 'running').length;
  if (activeCount >= MAX_QUEUE_SIZE) {
    throw new Error(`Run queue capacity reached (${MAX_QUEUE_SIZE}).`);
  }
}

function formatRunTimestamp(date: Date): string {
  const yyyy = String(date.getUTCFullYear());
  const mm = String(date.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(date.getUTCDate()).padStart(2, '0');
  const hh = String(date.getUTCHours()).padStart(2, '0');
  const min = String(date.getUTCMinutes()).padStart(2, '0');
  const sec = String(date.getUTCSeconds()).padStart(2, '0');
  return `${yyyy}${mm}${dd}T${hh}${min}${sec}Z`;
}

function sanitizeRunFolderFragment(value: string): string {
  const withoutReserved = value.replace(/[<>:"/\\|?*]/g, ' ');
  const withoutControlChars = [...withoutReserved]
    .map((character) => (character.charCodeAt(0) < 32 ? ' ' : character))
    .join('');
  return withoutControlChars.replace(/\s+/g, ' ').replace(/\.+$/g, '').trim();
}

function buildRunId(date: Date, title: string | undefined, baseline: string): string {
  const baselineFragment = sanitizeRunFolderFragment(baseline) || 'baseline';
  if (title) {
    const titleFragment = sanitizeRunFolderFragment(title);
    if (titleFragment) {
      return `${titleFragment} ${baselineFragment}`;
    }
  }
  return `run-${formatRunTimestamp(date)} ${baselineFragment}`;
}

function hasActiveRunId(runId: string): boolean {
  for (const job of jobsById.values()) {
    if ((job.job.status === 'queued' || job.job.status === 'running') && job.job.runId === runId) {
      return true;
    }
  }
  return false;
}

function resolveResultsCapBytes(): number {
  const rawCapMb = process.env.DASHBOARD_RESULTS_CAP_MB?.trim();
  if (!rawCapMb) {
    return DEFAULT_RESULTS_CAP_MB * 1024 * 1024;
  }

  const parsedCapMb = Number.parseFloat(rawCapMb);
  if (!Number.isFinite(parsedCapMb) || parsedCapMb <= 0) {
    return DEFAULT_RESULTS_CAP_MB * 1024 * 1024;
  }

  return Math.floor(parsedCapMb * 1024 * 1024);
}

function directorySizeBytes(directoryPath: string): number {
  let total = 0;
  const stack = [directoryPath];

  while (stack.length > 0) {
    const current = stack.pop() as string;
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      const absolute = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(absolute);
      } else if (entry.isFile()) {
        total += fs.statSync(absolute).size;
      }
    }
  }

  return total;
}

function getResultsStorageUsageBytes(pathsInput: RuntimePathInput): number {
  const paths = resolveRuntimePaths(pathsInput);
  const resultsRoot = paths.resultsRoot;
  if (!fs.existsSync(resultsRoot)) {
    return 0;
  }

  return fs
    .readdirSync(resultsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .reduce((sum, entry) => sum + directorySizeBytes(path.join(resultsRoot, entry.name)), 0);
}

export function getResultsStorageSummary(pathsInput: RuntimePathInput): ResultsStorageSummary {
  return {
    usedBytes: getResultsStorageUsageBytes(pathsInput),
    capBytes: resolveResultsCapBytes()
  };
}

function assertResultsStorageHeadroom(pathsInput: RuntimePathInput): void {
  const summary = getResultsStorageSummary(pathsInput);
  if (summary.usedBytes >= summary.capBytes) {
    const usageMb = (summary.usedBytes / (1024 * 1024)).toFixed(1);
    const capMb = (summary.capBytes / (1024 * 1024)).toFixed(1);
    throw new Error(
      `Results storage cap reached (${usageMb} MB used / ${capMb} MB cap). Delete existing runs before starting another run.`
    );
  }
}

function createUnmanagedRunPathError(runId: string): Error {
  return new Error(
    `Output folder "${runId}" already exists but is not marked as a dashboard-managed run. Refusing to overwrite it from the dashboard.`
  );
}

function assertExistingRunPathIsDashboardManaged(runPath: string, runId: string): void {
  if (!isDashboardManagedRun(runPath, runId)) {
    throw createUnmanagedRunPathError(runId);
  }
}

function removeRunDirectoryIfDashboardManaged(runPath: string, runId: string): void {
  if (isDashboardManagedRun(runPath, runId)) {
    fs.rmSync(runPath, { recursive: true, force: true });
  }
}

function startNextQueuedJob(): void {
  if (shutdownRequested) {
    return;
  }
  if (runningJobId !== null) {
    return;
  }

  const queuedJob = jobOrder
    .map((jobId) => jobsById.get(jobId))
    .find((job): job is ModelRunJobInternal => job !== undefined && job.job.status === 'queued');

  if (!queuedJob) {
    return;
  }

  const paths = queuedJob.runtimePaths;
  if (!queuedJob.ignoreStorageCap) {
    try {
      assertResultsStorageHeadroom(paths);
    } catch (error) {
      queuedJob.job.status = 'failed';
      queuedJob.job.endedAt = new Date().toISOString();
      queuedJob.job.exitCode = null;
      queuedJob.job.signal = null;
      appendLogLine(queuedJob.logBuffer, `[stderr] ${(error as Error).message}`, MAX_LOG_LINES);
      removeRunDirectoryIfDashboardManaged(queuedJob.runAbsolutePath, queuedJob.job.runId);
      fs.rmSync(queuedJob.tempDirPath, { recursive: true, force: true });
      startNextQueuedJob();
      return;
    }
  }

  if (
    fs.existsSync(queuedJob.runAbsolutePath) &&
    !isDashboardManagedRun(queuedJob.runAbsolutePath, queuedJob.job.runId)
  ) {
    queuedJob.job.status = 'failed';
    queuedJob.job.endedAt = new Date().toISOString();
    queuedJob.job.exitCode = null;
    queuedJob.job.signal = null;
    appendLogLine(
      queuedJob.logBuffer,
      `[stderr] ${createUnmanagedRunPathError(queuedJob.job.runId).message}`,
      MAX_LOG_LINES
    );
    fs.rmSync(queuedJob.tempDirPath, { recursive: true, force: true });
    startNextQueuedJob();
    return;
  }

  queuedJob.job.status = 'running';
  queuedJob.job.startedAt = new Date().toISOString();
  runningJobId = queuedJob.job.jobId;

  fs.mkdirSync(queuedJob.runAbsolutePath, { recursive: true });
  writeDashboardManagedRunMarker(queuedJob.runAbsolutePath, {
    jobId: queuedJob.job.jobId,
    runId: queuedJob.job.runId,
    baseline: queuedJob.job.baseline,
    title: queuedJob.job.title ?? null,
    createdAt: queuedJob.job.createdAt
  });
  writeManualRunManifest({
    paths,
    launcher: queuedJob.launcher,
    job: queuedJob.job,
    configPath: queuedJob.configAbsolutePath,
    outputPath: queuedJob.runAbsolutePath,
    seed: queuedJob.seed,
    overriddenParameters: queuedJob.overriddenParameters,
    outputHash: null
  });

  let child: ChildProcessWithoutNullStreams;
  try {
    child = queuedJob.launcher.launch({
      repoRoot: paths.repoRoot,
      configPath: queuedJob.configAbsolutePath,
      outputPath: queuedJob.runAbsolutePath
    });
  } catch (error) {
    queuedJob.job.status = 'failed';
    queuedJob.job.endedAt = new Date().toISOString();
    queuedJob.job.exitCode = null;
    queuedJob.job.signal = null;
    appendLogLine(
      queuedJob.logBuffer,
      `[stderr] Failed to spawn model process: ${formatLauncherProcessError(queuedJob.launcher, error as Error)}`,
      MAX_LOG_LINES
    );
    runningJobId = null;
    removeRunDirectoryIfDashboardManaged(queuedJob.runAbsolutePath, queuedJob.job.runId);
    fs.rmSync(queuedJob.tempDirPath, { recursive: true, force: true });
    startNextQueuedJob();
    return;
  }

  queuedJob.process = child;

  child.stdout.on('data', (chunk: Buffer) => {
    appendOutputChunk(queuedJob.logBuffer, 'stdout', chunk, MAX_LOG_LINES);
  });

  child.stderr.on('data', (chunk: Buffer) => {
    appendOutputChunk(queuedJob.logBuffer, 'stderr', chunk, MAX_LOG_LINES);
  });

  child.on('error', (error: Error) => {
    appendLogLine(
      queuedJob.logBuffer,
      `[stderr] Model process error: ${formatLauncherProcessError(queuedJob.launcher, error)}`,
      MAX_LOG_LINES
    );
  });

  child.on('close', (code, signal) => {
    flushPartialLine(queuedJob.logBuffer, MAX_LOG_LINES);

    if (queuedJob.killTimer) {
      clearTimeout(queuedJob.killTimer);
      queuedJob.killTimer = undefined;
    }

    queuedJob.job.endedAt = new Date().toISOString();
    queuedJob.job.exitCode = code;
    queuedJob.job.signal = signal;

    if (queuedJob.cancelRequested) {
      queuedJob.job.status = 'canceled';
    } else if (code === 0) {
      queuedJob.job.status = 'succeeded';
    } else {
      queuedJob.job.status = 'failed';
    }

    if (queuedJob.job.status === 'succeeded') {
      writeManualRunManifest({
        paths,
        launcher: queuedJob.launcher,
        job: queuedJob.job,
        configPath: queuedJob.configAbsolutePath,
        outputPath: queuedJob.runAbsolutePath,
        seed: queuedJob.seed,
        overriddenParameters: queuedJob.overriddenParameters,
        outputHash: hashDirectory(
          queuedJob.runAbsolutePath,
          new Set([RUN_MANIFEST_FILE_NAME, MANAGED_RUN_MARKER])
        )
      });
    }

    if (queuedJob.job.status === 'failed' || queuedJob.job.status === 'canceled') {
      removeRunDirectoryIfDashboardManaged(queuedJob.runAbsolutePath, queuedJob.job.runId);
    }

    fs.rmSync(queuedJob.tempDirPath, { recursive: true, force: true });
    runningJobId = null;
    startNextQueuedJob();
  });
}

function toPublicJob(job: ModelRunJobInternal): ModelRunJob {
  return { ...job.job };
}

export function getModelRunOptions(
  pathsInput: RuntimePathInput,
  requestedBaseline: string | undefined,
  executionEnabled: boolean
): ModelRunOptionsPayload {
  const paths = resolveRuntimePaths(pathsInput);
  const { baseline, snapshots, defaultBaseline } = resolveBaseline(paths, requestedBaseline);

  return {
    executionEnabled,
    snapshots,
    defaultBaseline,
    requestedBaseline: baseline,
    parameters: getParameterDefinitionsForBaseline(paths, baseline)
  };
}

export function listModelRunJobs(): ModelRunJob[] {
  return [...jobOrder]
    .reverse()
    .map((jobId) => jobsById.get(jobId))
    .filter((job): job is ModelRunJobInternal => Boolean(job))
    .map((job) => toPublicJob(job));
}

export function getModelRunJob(jobId: string): ModelRunJob {
  const normalized = jobId.trim();
  if (!normalized) {
    throw new Error('jobId is required.');
  }

  const job = jobsById.get(normalized);
  if (!job) {
    throw new Error(`Unknown model run job: ${jobId}`);
  }

  return toPublicJob(job);
}

export function getModelRunJobLogs(jobId: string, cursor: number | undefined, limit: number | undefined): ModelRunJobLogsPayload {
  const normalized = jobId.trim();
  if (!normalized) {
    throw new Error('jobId is required.');
  }

  const job = jobsById.get(normalized);
  if (!job) {
    throw new Error(`Unknown model run job: ${jobId}`);
  }

  const slice = readLogSlice(job.logBuffer, cursor, limit);

  return {
    jobId: normalized,
    cursor: slice.cursor,
    nextCursor: slice.nextCursor,
    lines: slice.lines,
    hasMore: slice.hasMore,
    done: isTerminal(job.job.status) && !slice.hasMore,
    truncated: slice.truncated
  };
}

export function cancelModelRunJob(_pathsInput: RuntimePathInput, jobId: string): ModelRunJob {
  const normalized = jobId.trim();
  if (!normalized) {
    throw new Error('jobId is required.');
  }

  const job = jobsById.get(normalized);
  if (!job) {
    throw new Error(`Unknown model run job: ${jobId}`);
  }

  if (isTerminal(job.job.status)) {
    return toPublicJob(job);
  }

  if (job.job.status === 'queued') {
    job.job.status = 'canceled';
    job.job.endedAt = new Date().toISOString();
    fs.rmSync(job.tempDirPath, { recursive: true, force: true });
    startNextQueuedJob();
    return toPublicJob(job);
  }

  if (job.job.status === 'running' && job.process) {
    if (!job.cancelRequested) {
      const sigtermSent = job.process.kill('SIGTERM');
      if (sigtermSent) {
        job.cancelRequested = true;
        job.killTimer = setTimeout(() => {
          if (job.process && !isTerminal(job.job.status)) {
            job.process.kill('SIGKILL');
          }
        }, CANCEL_KILL_TIMEOUT_MS);
      } else {
        appendLogLine(
          job.logBuffer,
          '[stderr] Cancel requested but SIGTERM could not be delivered; waiting for process close.',
          MAX_LOG_LINES
        );
      }
    }
    return toPublicJob(job);
  }

  return toPublicJob(job);
}

export function clearModelRunJob(jobId: string): ModelRunJobClearResponse {
  const normalized = jobId.trim();
  if (!normalized) {
    throw new Error('jobId is required.');
  }

  const job = jobsById.get(normalized);
  if (!job) {
    throw new Error(`Unknown model run job: ${jobId}`);
  }

  if (job.job.status === 'queued' || job.job.status === 'running') {
    throw new Error('Only finished jobs can be cleared from the job queue.');
  }

  jobsById.delete(normalized);
  const orderIndex = jobOrder.indexOf(normalized);
  if (orderIndex >= 0) {
    jobOrder.splice(orderIndex, 1);
  }

  return {
    jobId: normalized,
    cleared: true
  };
}

export function prepareModelRunSubmission(
  pathsInput: RuntimePathInput,
  payload: ModelRunSubmitRequest,
  options: PrepareModelRunSubmissionOptions = {}
): { accepted: false; warnings: ModelRunWarning[] } | { accepted: true; prepared: PreparedModelRunSubmission } {
  const paths = resolveRuntimePaths(pathsInput);
  const ignoreStorageCap = options.ignoreStorageCap === true;
  const baselineRaw = payload.baseline?.trim();
  if (!baselineRaw) {
    throw new Error('baseline is required.');
  }

  const { baseline } = resolveBaseline(paths, baselineRaw);
  const parameterDefinitions = getParameterDefinitionsForBaseline(paths, baseline);
  const parameterDefMap = new Map(parameterDefinitions.map((item) => [item.key, item]));

  const overrides = payload.overrides ?? {};
  const overrideEntries = Object.entries(overrides);
  const normalizedOverrides = new Map<string, string>();
  const overriddenParameters: Record<string, number | boolean> = {};

  const valuesByKey = new Map(parameterDefinitions.map((definition) => [definition.key, definition.defaultValue]));

  for (const [key, rawValue] of overrideEntries) {
    const definition = parameterDefMap.get(key);
    if (!definition) {
      throw new Error(`Unsupported override key: ${key}`);
    }

    const parsedOverride = normalizeOverrideValue(key, rawValue, definition.type);
    normalizedOverrides.set(key, parsedOverride.serialized);
    valuesByKey.set(key, parsedOverride.typed);
    overriddenParameters[key] = parsedOverride.typed;
  }

  const now = options.now ?? new Date();
  const trimmedTitle = payload.title?.trim();
  const title = trimmedTitle ? trimmedTitle.slice(0, 120) : undefined;
  const runId = buildRunId(now, title, baseline);
  if (hasActiveRunId(runId)) {
    throw new Error(`A queued or running job is already targeting output folder "${runId}".`);
  }

  const runAbsolutePath = path.join(paths.resultsRoot, runId);
  const warnings = createWarnings(valuesByKey);
  if (fs.existsSync(runAbsolutePath)) {
    assertExistingRunPathIsDashboardManaged(runAbsolutePath, runId);
    warnings.push({
      code: 'output_folder_exists',
      message: `Output folder "${runId}" already exists and will be overwritten.`,
      severity: 'warning'
    });
  }

  if (warnings.length > 0 && payload.confirmWarnings !== true) {
    return {
      accepted: false,
      warnings
    };
  }

  ensureQueueCapacity();
  if (!ignoreStorageCap) {
    assertResultsStorageHeadroom(paths);
  }

  if (fs.existsSync(runAbsolutePath)) {
    assertExistingRunPathIsDashboardManaged(runAbsolutePath, runId);
    fs.rmSync(runAbsolutePath, { recursive: true, force: true });
  }

  if (!ignoreStorageCap) {
    assertResultsStorageHeadroom(paths);
  }

  const jobId = `job-${formatRunTimestamp(now)}-${randomUUID().slice(0, 8)}`;

  const tempDirPath = path.join(paths.tempRoot, TMP_RUNS_DIR, jobId);
  const configAbsolutePath = path.join(tempDirPath, 'config.properties');
  const baselineDirPath = path.join(paths.dataRoot, baseline);
  const baselineConfigPath = path.join(baselineDirPath, 'config.properties');

  return {
    accepted: true,
    prepared: {
      baseline,
      title,
      runId,
      jobId,
      createdAt: now.toISOString(),
      warnings,
      tempDirPath,
      configAbsolutePath,
      runAbsolutePath,
      baselineConfigPath,
      baselineDirPath,
      normalizedOverrides,
      valuesByKey,
      overriddenParameters,
      ignoreStorageCap
    }
  };
}

export function submitModelRun(
  pathsInput: RuntimePathInput,
  payload: ModelRunSubmitRequest,
  options: SubmitModelRunOptions = {}
): ModelRunSubmitResponse {
  const paths = resolveRuntimePaths(pathsInput);
  const launcher = resolveModelLauncher(options.launcher);
  const preparedResult = prepareModelRunSubmission(paths, payload, {
    ignoreStorageCap: options.ignoreStorageCap
  });
  if (!preparedResult.accepted) {
    return preparedResult;
  }
  const {
    baseline,
    title,
    runId,
    jobId,
    createdAt,
    warnings,
    tempDirPath,
    configAbsolutePath,
    runAbsolutePath,
    baselineConfigPath,
    baselineDirPath,
    normalizedOverrides,
    valuesByKey,
    overriddenParameters,
    ignoreStorageCap
  } = preparedResult.prepared;

  rewriteConfigForJob(baselineConfigPath, baselineDirPath, configAbsolutePath, normalizedOverrides);

  const job: ModelRunJob = {
    jobId,
    runId,
    title,
    baseline,
    status: 'queued',
    createdAt,
    outputPath: toRuntimePath(paths, runAbsolutePath),
    configPath: toRuntimePath(paths, configAbsolutePath)
  };

  const internalJob: ModelRunJobInternal = {
    job,
    runtimePaths: paths,
    warnings,
    logBuffer: {
      logLines: [],
      logStart: 0,
      partialLine: '',
      ...(options.logSink ? { sink: (line) => options.logSink?.(`[manual:${jobId}] ${line}`) } : {})
    },
    launcher,
    cancelRequested: false,
    tempDirPath,
    configAbsolutePath,
    runAbsolutePath,
    seed: typeof valuesByKey.get('SEED') === 'number' ? Number(valuesByKey.get('SEED')) : null,
    overriddenParameters,
    ignoreStorageCap
  };

  jobsById.set(job.jobId, internalJob);
  jobOrder.push(job.jobId);
  startNextQueuedJob();

  return {
    accepted: true,
    warnings,
    job: toPublicJob(internalJob)
  };
}

export function __setModelRunSpawnForTests(spawnFn: SpawnModelRunFn | null): void {
  modelRunLauncherOverrideForTests = spawnFn ? createSpawnFunctionLauncher(spawnFn) : null;
}

export function shutdownModelRunProcesses(): void {
  const now = new Date().toISOString();
  shutdownRequested = true;
  for (const job of jobsById.values()) {
    if (job.killTimer) {
      clearTimeout(job.killTimer);
      job.killTimer = undefined;
    }
    if (job.process && !isTerminal(job.job.status)) {
      job.cancelRequested = true;
      job.job.status = 'canceled';
      job.job.endedAt = now;
      job.process.kill('SIGKILL');
    } else if (job.job.status === 'queued') {
      job.cancelRequested = true;
      job.job.status = 'canceled';
      job.job.endedAt = now;
      fs.rmSync(job.tempDirPath, { recursive: true, force: true });
    }
  }
}

export function __resetModelRunManagerForTests(): void {
  shutdownModelRunProcesses();
  jobsById.clear();
  jobOrder.length = 0;
  runningJobId = null;
  shutdownRequested = false;
  __setModelRunSpawnForTests(null);
}
