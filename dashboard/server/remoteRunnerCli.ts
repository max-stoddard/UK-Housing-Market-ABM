// Author: Max Stoddard
import fs from 'node:fs';
import path from 'node:path';
import {
  getModelRunJob,
  shutdownModelRunProcesses,
  submitModelRun
} from './lib/modelRuns';
import { createDevelopmentRuntimePaths } from './lib/runtimePaths';
import {
  getSensitivityExperiment,
  shutdownSensitivityRunProcesses,
  submitSensitivityExperiment
} from './lib/sensitivityRuns';
import type {
  ModelRunSubmitRequest,
  ModelRunJob,
  SensitivityExperimentCreateRequest,
  SensitivityExperimentMetadata
} from '../shared/types';

type RemoteRunRequest = {
  schemaVersion: 1;
  jobRef: string;
  type: 'manual' | 'sensitivity';
  createdAt: string;
  sourceCommit: string;
  sourceBundleKey: string;
  artifactS3Prefix: string;
  payload: ModelRunSubmitRequest | SensitivityExperimentCreateRequest;
};

type CliArgs = {
  requestPath: string;
  runRoot: string;
  artifactRoot: string;
};

const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'canceled']);
let activeRunContext: { request: RemoteRunRequest; artifactRoot: string; logPath: string } | null = null;
let terminationRequested = false;

function parseArgs(argv: string[]): CliArgs {
  const args = new Map<string, string>();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith('--') || !value) {
      throw new Error('Usage: remoteRunnerCli.ts --request <path> --run-root <path> --artifact-root <path>');
    }
    args.set(key, value);
  }

  const requestPath = args.get('--request');
  const runRoot = args.get('--run-root');
  const artifactRoot = args.get('--artifact-root');
  if (!requestPath || !runRoot || !artifactRoot) {
    throw new Error('Usage: remoteRunnerCli.ts --request <path> --run-root <path> --artifact-root <path>');
  }
  return {
    requestPath: path.resolve(requestPath),
    runRoot: path.resolve(runRoot),
    artifactRoot: path.resolve(artifactRoot)
  };
}

function readJson<T>(filePath: string): T {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8')) as T;
}

function writeJson(filePath: string, value: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function appendLog(logPath: string, line: string): void {
  fs.mkdirSync(path.dirname(logPath), { recursive: true });
  fs.appendFileSync(logPath, `${line}\n`, 'utf-8');
}

function handleTermination(signal: NodeJS.Signals): void {
  terminationRequested = true;
  shutdownModelRunProcesses();
  shutdownSensitivityRunProcesses();
  if (activeRunContext) {
    appendLog(activeRunContext.logPath, `[system] Remote runner received ${signal}; canceling active model processes`);
    writeJson(path.join(activeRunContext.artifactRoot, 'remote-status.json'), {
      schemaVersion: 1,
      jobRef: activeRunContext.request.jobRef,
      type: activeRunContext.request.type,
      status: 'canceled',
      signal,
      sourceCommit: activeRunContext.request.sourceCommit,
      endedAt: new Date().toISOString()
    });
  }
  setTimeout(() => process.exit(130), 1_000).unref();
}

process.once('SIGTERM', handleTermination);
process.once('SIGINT', handleTermination);

async function waitForManualJob(jobId: string): Promise<ModelRunJob> {
  while (true) {
    if (terminationRequested) {
      throw new Error('Remote runner was canceled.');
    }
    const job = getModelRunJob(jobId);
    if (TERMINAL_STATUSES.has(job.status)) {
      return job;
    }
    await sleep(2_000);
  }
}

async function waitForSensitivityExperiment(
  paths: ReturnType<typeof createDevelopmentRuntimePaths>,
  experimentId: string
): Promise<SensitivityExperimentMetadata> {
  while (true) {
    if (terminationRequested) {
      throw new Error('Remote runner was canceled.');
    }
    const detail = getSensitivityExperiment(paths, experimentId).experiment;
    if (TERMINAL_STATUSES.has(detail.status)) {
      return detail;
    }
    await sleep(2_000);
  }
}

function copyIfExists(source: string, destination: string): void {
  if (!fs.existsSync(source)) {
    return;
  }
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.cpSync(source, destination, { recursive: true });
}

async function runManual(request: RemoteRunRequest, paths: ReturnType<typeof createDevelopmentRuntimePaths>, artifactRoot: string, logPath: string): Promise<void> {
  const submit = submitModelRun(paths, request.payload as ModelRunSubmitRequest, {
    ignoreStorageCap: true,
    logSink: (line) => appendLog(logPath, line)
  });
  if (!submit.accepted || !submit.job) {
    writeJson(path.join(artifactRoot, 'remote-status.json'), {
      schemaVersion: 1,
      jobRef: request.jobRef,
      status: 'failed',
      failureReason: 'Remote manual run was rejected by dashboard validation.',
      warnings: submit.warnings,
      endedAt: new Date().toISOString()
    });
    process.exitCode = 2;
    return;
  }

  const job = await waitForManualJob(submit.job.jobId);
  copyIfExists(path.join(paths.resultsRoot, job.runId), path.join(artifactRoot, 'Results', job.runId));
  writeJson(path.join(artifactRoot, 'remote-status.json'), {
    schemaVersion: 1,
    jobRef: request.jobRef,
    type: request.type,
    status: job.status,
    runId: job.runId,
    startedAt: job.startedAt,
    endedAt: job.endedAt,
    exitCode: job.exitCode,
    signal: job.signal,
    sourceCommit: request.sourceCommit
  });
  if (job.status !== 'succeeded') {
    process.exitCode = 1;
  }
}

async function runSensitivity(request: RemoteRunRequest, paths: ReturnType<typeof createDevelopmentRuntimePaths>, artifactRoot: string, logPath: string): Promise<void> {
  const submit = submitSensitivityExperiment(paths, request.payload as SensitivityExperimentCreateRequest, {
    logSink: (line) => appendLog(logPath, line)
  });
  if (!submit.accepted || !submit.experiment) {
    writeJson(path.join(artifactRoot, 'remote-status.json'), {
      schemaVersion: 1,
      jobRef: request.jobRef,
      status: 'failed',
      failureReason: 'Remote sensitivity experiment was rejected by dashboard validation.',
      warnings: submit.warnings,
      warningSummary: submit.warningSummary,
      endedAt: new Date().toISOString()
    });
    process.exitCode = 2;
    return;
  }

  const experiment = await waitForSensitivityExperiment(paths, submit.experiment.experimentId);
  copyIfExists(
    path.join(paths.resultsRoot, 'experiments', 'sensitivity', experiment.experimentId),
    path.join(artifactRoot, 'Results', 'experiments', 'sensitivity', experiment.experimentId)
  );
  writeJson(path.join(artifactRoot, 'remote-status.json'), {
    schemaVersion: 1,
    jobRef: request.jobRef,
    type: request.type,
    status: experiment.status,
    experimentId: experiment.experimentId,
    startedAt: experiment.startedAt,
    endedAt: experiment.endedAt,
    failureReason: experiment.failureReason,
    sourceCommit: request.sourceCommit
  });
  if (experiment.status !== 'succeeded') {
    process.exitCode = 1;
  }
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const request = readJson<RemoteRunRequest>(args.requestPath);
  const repoRoot = path.resolve(process.cwd(), '..');
  const paths = createDevelopmentRuntimePaths(repoRoot);
  paths.resultsRoot = path.join(args.runRoot, 'Results');
  paths.tempRoot = path.join(args.runRoot, 'tmp');
  paths.logsRoot = path.join(args.runRoot, 'logs');

  fs.mkdirSync(args.artifactRoot, { recursive: true });
  fs.mkdirSync(paths.resultsRoot, { recursive: true });
  fs.mkdirSync(paths.tempRoot, { recursive: true });
  fs.mkdirSync(paths.logsRoot, { recursive: true });
  fs.copyFileSync(args.requestPath, path.join(args.artifactRoot, 'request.json'));

  const logPath = path.join(args.artifactRoot, 'logs', 'remote-runner.log');
  activeRunContext = { request, artifactRoot: args.artifactRoot, logPath };
  appendLog(logPath, `[system] Remote runner starting ${request.jobRef}`);
  appendLog(logPath, `[system] sourceCommit=${request.sourceCommit}`);

  if (request.type === 'manual') {
    await runManual(request, paths, args.artifactRoot, logPath);
  } else {
    await runSensitivity(request, paths, args.artifactRoot, logPath);
  }

  appendLog(logPath, `[system] Remote runner finished ${request.jobRef}`);
  activeRunContext = null;
}

void main().catch((error) => {
  if (!terminationRequested) {
    console.error(error);
  }
  process.exitCode = 1;
});
