// Author: Max Stoddard
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {
  parseWorkerCounts,
  runParallelScalingExperiment,
  type ParallelScalingExperimentOptions
} from './lib/parallelScalingReport';

export type CliPhase = 'pilot' | 'full';

export interface CliArgs {
  phase: CliPhase;
  repoRoot: string;
  outputRoot: string;
  snapshot: string;
  baseMode: string;
  workerCounts?: string;
  seedCount?: number;
  targetPopulation?: number;
  nSteps?: number;
  repeats?: number;
  orderingSeed?: number;
  confirmExpensive: boolean;
  pythonAnalyzer?: string;
}

export function parseArgs(argv: string[]): CliArgs {
  const args = new Map<string, string | true>();
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!key.startsWith('--')) {
      throw new Error(usage());
    }
    if (key === '--confirm-expensive' || key === '--analyze') {
      args.set(key, true);
      continue;
    }
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) {
      throw new Error(usage());
    }
    args.set(key, value);
    index += 1;
  }

  const repoRoot = path.resolve(stringArg(args, '--repo-root') ?? path.resolve(process.cwd(), '..'));
  const phase = parsePhase(stringArg(args, '--phase') ?? 'pilot');
  return {
    phase,
    repoRoot,
    outputRoot: path.resolve(stringArg(args, '--output-root') ?? path.join(repoRoot, 'tmp', '_report')),
    snapshot: stringArg(args, '--snapshot') ?? 'v0',
    baseMode: stringArg(args, '--base-mode') ?? 'core-minimal-20k-s1',
    workerCounts: stringArg(args, '--workers') ?? stringArg(args, '--worker-counts') ?? undefined,
    seedCount: optionalIntegerArg(args, '--seed-count'),
    targetPopulation: optionalIntegerArg(args, '--target-population'),
    nSteps: optionalIntegerArg(args, '--n-steps'),
    repeats: optionalIntegerArg(args, '--repeats'),
    orderingSeed: optionalAnyIntegerArg(args, '--ordering-seed'),
    confirmExpensive: args.get('--confirm-expensive') === true,
    pythonAnalyzer: stringArg(args, '--python-analyzer') ?? (args.get('--analyze') === true ? defaultAnalyzerPath(repoRoot) : undefined)
  };
}

export function toExperimentOptions(args: CliArgs): ParallelScalingExperimentOptions {
  if (args.phase === 'full' && !args.confirmExpensive) {
    throw new Error('Full parallel scaling phase is expensive; pass --confirm-expensive to run it.');
  }

  return {
    repoRoot: args.repoRoot,
    snapshot: args.snapshot,
    baseMode: args.baseMode,
    outputRoot: args.outputRoot,
    targetPopulation: args.targetPopulation ?? 20_000,
    nSteps: args.nSteps ?? 2_000,
    seedCount: args.seedCount ?? (args.phase === 'full' ? 32 : 3),
    workerCounts: args.workerCounts ? parseWorkerCounts(args.workerCounts) : args.phase === 'full' ? parseWorkerCounts(undefined) : [1, 2],
    repeats: args.repeats ?? (args.phase === 'full' ? 3 : 1),
    orderingSeed: args.orderingSeed ?? 1,
    phase: args.phase,
    confirmExpensive: args.confirmExpensive
  };
}

export function usage(): string {
  return [
    'Usage: parallelScalingReportCli.ts [options]',
    '  --phase <pilot|full>',
    '  --repo-root <path>',
    '  --output-root <path>',
    '  --snapshot <snapshot>',
    '  --base-mode <mode>',
    '  --workers <comma-separated counts>',
    '  --worker-counts <comma-separated counts>',
    '  --seed-count <positive integer>',
    '  --target-population <positive integer>',
    '  --n-steps <positive integer>',
    '  --repeats <positive integer>',
    '  --ordering-seed <seed>',
    '  --confirm-expensive',
    '  --analyze | --python-analyzer <path>',
    '',
    'Pilot example:',
    '  node --import tsx/esm server/parallelScalingReportCli.ts \\',
    '    --phase pilot \\',
    '    --snapshot v0 \\',
    '    --base-mode core-minimal-20k-s1 \\',
    '    --target-population 5000 \\',
    '    --n-steps 2000 \\',
    '    --seed-count 8 \\',
    '    --workers 1,4,8 \\',
    '    --repeats 1 \\',
    '    --ordering-seed 20260527 \\',
    '    --output-root ../tmp/_report',
    '',
    'Full example:',
    '  node --import tsx/esm server/parallelScalingReportCli.ts \\',
    '    --phase full \\',
    '    --snapshot v0 \\',
    '    --base-mode core-minimal-20k-s1 \\',
    '    --target-population <pilot-selected-population> \\',
    '    --n-steps 2000 \\',
    '    --seed-count 40 \\',
    '    --workers 1,2,4,8,12,16,20,24,32 \\',
    '    --repeats 3 \\',
    '    --ordering-seed 20260527 \\',
    '    --output-root ../tmp/_report \\',
    '    --confirm-expensive'
  ].join('\n');
}

function stringArg(args: Map<string, string | true>, key: string): string | null {
  const value = args.get(key);
  return typeof value === 'string' ? value : null;
}

function optionalIntegerArg(args: Map<string, string | true>, key: string): number | undefined {
  const value = stringArg(args, key);
  if (value === null) {
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${key} must be a positive integer.`);
  }
  return parsed;
}

function optionalAnyIntegerArg(args: Map<string, string | true>, key: string): number | undefined {
  const value = stringArg(args, key);
  if (value === null) {
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed)) {
    throw new Error(`${key} must be an integer.`);
  }
  return parsed;
}

function parsePhase(raw: string): CliPhase {
  if (raw === 'pilot' || raw === 'full') {
    return raw;
  }
  throw new Error('--phase must be pilot or full.');
}

function defaultAnalyzerPath(repoRoot: string): string {
  return path.join(repoRoot, 'scripts', 'python', 'experiments', 'model', 'parallel_scaling_report.py');
}

function maybeRunAnalyzer(analyzerPath: string | undefined, rawJsonPath: string, outputRoot: string): void {
  if (!analyzerPath) {
    return;
  }
  if (!fs.existsSync(analyzerPath)) {
    console.warn(`Python analyzer not found, skipping: ${analyzerPath}`);
    return;
  }
  const result = spawnSync('python3', [analyzerPath, '--raw-json', rawJsonPath, '--output-root', outputRoot], {
    encoding: 'utf-8',
    stdio: 'inherit'
  });
  if (result.error) {
    throw new Error(`Failed to run Python analyzer: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error(`Python analyzer exited with status ${result.status ?? 'unknown'}.`);
  }
}

export async function main(): Promise<void> {
  if (process.argv.slice(2).some((arg) => arg === '--help' || arg === '-h')) {
    console.log(usage());
    return;
  }

  const args = parseArgs(process.argv.slice(2));
  const result = await runParallelScalingExperiment(toExperimentOptions(args), {
    logSink: (line) => console.log(line)
  });
  console.log(`parallel scaling report ${result.runId} ${result.status}`);
  console.log(`raw JSON: ${result.artifacts.rawJsonPath}`);
  maybeRunAnalyzer(args.pythonAnalyzer, result.artifacts.rawJsonPath, args.outputRoot);
  if (result.status !== 'succeeded') {
    process.exitCode = 1;
  }
}

function isDirectCliEntrypoint(): boolean {
  const entrypoint = process.argv[1] ? path.basename(process.argv[1]) : '';
  return entrypoint === 'parallelScalingReportCli.ts' || entrypoint === 'parallelScalingReportCli.js';
}

if (isDirectCliEntrypoint()) {
  void main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
