// Author: Max Stoddard
import { spawn, type ChildProcessWithoutNullStreams, type SpawnOptionsWithoutStdio } from 'node:child_process';
import path from 'node:path';

export type ModelLauncherMode = 'maven' | 'packaged';

export interface ModelLaunchRequest {
  repoRoot: string;
  configPath: string;
  outputPath: string;
}

export interface ModelLauncherCommand {
  command: string;
  args: string[];
  options: SpawnOptionsWithoutStdio;
  commandTemplate: string;
}

export interface ModelLauncherMetadata {
  mode: ModelLauncherMode;
  commandTemplate: string;
  mavenBin?: string;
  javaExe?: string;
  modelJar?: string;
}

export interface ModelLauncher {
  mode: ModelLauncherMode;
  metadata: ModelLauncherMetadata;
  buildCommand: (request: ModelLaunchRequest) => ModelLauncherCommand;
  launch: (request: ModelLaunchRequest) => ChildProcessWithoutNullStreams;
}

const windowsBatchInvokerScript = [
  '$ErrorActionPreference = "Stop"',
  '$command = $args[0]',
  '$commandArgs = @()',
  'if ($args.Count -gt 1) { $commandArgs = $args[1..($args.Count - 1)] }',
  '& $command @commandArgs',
  'exit $LASTEXITCODE'
].join('; ');

function defaultMavenWrapperBin(repoRoot?: string): string {
  const wrapperName = process.platform === 'win32' ? 'mvnw.cmd' : 'mvnw';
  return repoRoot ? path.join(repoRoot, wrapperName) : `.${path.sep}${wrapperName}`;
}

function isWindowsBatchCommand(command: string): boolean {
  return process.platform === 'win32' && /\.(?:cmd|bat)$/i.test(command);
}

export function getConfiguredMavenBin(repoRoot?: string): string {
  return process.env.DASHBOARD_MAVEN_BIN?.trim() || defaultMavenWrapperBin(repoRoot);
}

export function prepareCommandForSpawn(
  command: string,
  args: string[],
  options: SpawnOptionsWithoutStdio
): ModelLauncherCommand {
  if (!isWindowsBatchCommand(command)) {
    return {
      command,
      args,
      options: { ...options, shell: false },
      commandTemplate: `${command} ${args.join(' ')}`
    };
  }

  return {
    command: 'powershell.exe',
    args: [
      '-NoProfile',
      '-NonInteractive',
      '-ExecutionPolicy',
      'Bypass',
      '-Command',
      windowsBatchInvokerScript,
      command,
      ...args
    ],
    options: { ...options, shell: false },
    commandTemplate: `${command} ${args.join(' ')}`
  };
}

function quoteForExecArgs(value: string): string {
  return `"${value.replace(/"/g, '\\"')}"`;
}

export function buildMavenModelLaunchCommand(
  mavenBin: string,
  request: ModelLaunchRequest
): ModelLauncherCommand {
  const execArgs = [
    '-configFile',
    quoteForExecArgs(request.configPath),
    '-outputFolder',
    quoteForExecArgs(request.outputPath),
    '-dev'
  ].join(' ');

  return {
    command: mavenBin,
    args: ['compile', 'exec:java', `-Dexec.args=${execArgs}`],
    options: {
      cwd: request.repoRoot,
      shell: false
    },
    commandTemplate: `${mavenBin} compile exec:java -Dexec.args="-configFile <path> -outputFolder <path> -dev"`
  };
}

export function buildPackagedModelLaunchCommand(
  javaExe: string,
  modelJar: string,
  request: ModelLaunchRequest
): ModelLauncherCommand {
  return {
    command: javaExe,
    args: ['-jar', modelJar, '-configFile', request.configPath, '-outputFolder', request.outputPath, '-dev'],
    options: {
      cwd: request.repoRoot,
      shell: false
    },
    commandTemplate: `${javaExe} -jar <modelJar> -configFile <path> -outputFolder <path> -dev`
  };
}

export function createMavenModelLauncher(mavenBin = getConfiguredMavenBin()): ModelLauncher {
  const metadata: ModelLauncherMetadata = {
    mode: 'maven',
    mavenBin,
    commandTemplate: `${mavenBin} compile exec:java -Dexec.args="-configFile <path> -outputFolder <path> -dev"`
  };

  return {
    mode: 'maven',
    metadata,
    buildCommand: (request) => buildMavenModelLaunchCommand(mavenBin, request),
    launch: (request) => {
      const command = buildMavenModelLaunchCommand(mavenBin, request);
      const prepared = prepareCommandForSpawn(command.command, command.args, command.options);
      return spawn(prepared.command, prepared.args, prepared.options);
    }
  };
}

export function createPackagedModelLauncher(javaExe: string, modelJar: string): ModelLauncher {
  const metadata: ModelLauncherMetadata = {
    mode: 'packaged',
    javaExe,
    modelJar,
    commandTemplate: `${javaExe} -jar <modelJar> -configFile <path> -outputFolder <path> -dev`
  };

  return {
    mode: 'packaged',
    metadata,
    buildCommand: (request) => buildPackagedModelLaunchCommand(javaExe, modelJar, request),
    launch: (request) => {
      const command = buildPackagedModelLaunchCommand(javaExe, modelJar, request);
      const prepared = prepareCommandForSpawn(command.command, command.args, command.options);
      return spawn(prepared.command, prepared.args, prepared.options);
    }
  };
}
