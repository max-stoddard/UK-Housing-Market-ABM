// Author: Max Stoddard
import { spawn, type ChildProcessWithoutNullStreams, type SpawnOptionsWithoutStdio } from 'node:child_process';

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

export function getConfiguredMavenBin(): string {
  return process.env.DASHBOARD_MAVEN_BIN?.trim() || 'mvn';
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
      cwd: request.repoRoot
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
      return spawn(command.command, command.args, command.options);
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
      return spawn(command.command, command.args, command.options);
    }
  };
}
