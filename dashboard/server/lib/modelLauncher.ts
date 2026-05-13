// Author: Max Stoddard
import { spawnSync } from 'node:child_process';
import type { ChildProcessWithoutNullStreams, SpawnOptionsWithoutStdio } from 'node:child_process';
import path from 'node:path';
import crossSpawn from 'cross-spawn';

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
  prepare?: (request: Pick<ModelLaunchRequest, 'repoRoot'>) => void;
  buildCommand: (request: ModelLaunchRequest) => ModelLauncherCommand;
  launch: (request: ModelLaunchRequest) => ChildProcessWithoutNullStreams;
}

export interface PreparedMavenRuntime {
  javaExe: string;
  classpath: string;
}

function defaultMavenWrapperBin(repoRoot?: string): string {
  const wrapperName = process.platform === 'win32' ? 'mvnw.cmd' : 'mvnw';
  return repoRoot ? path.join(repoRoot, wrapperName) : `.${path.sep}${wrapperName}`;
}

export function getConfiguredMavenBin(repoRoot?: string): string {
  return process.env.DASHBOARD_MAVEN_BIN?.trim() || defaultMavenWrapperBin(repoRoot);
}

export function getConfiguredJavaBin(): string {
  return process.env.DASHBOARD_JAVA_BIN?.trim() || process.env.DASHBOARD_PACKAGED_JAVA_EXE?.trim() || 'java';
}

export function spawnCommand(
  command: string,
  args: string[],
  options: SpawnOptionsWithoutStdio
): ChildProcessWithoutNullStreams {
  return crossSpawn(command, args, { ...options, shell: false }) as ChildProcessWithoutNullStreams;
}

function shouldUseShellForCommand(command: string): boolean {
  return process.platform === 'win32' && /\.(?:cmd|bat)$/i.test(command);
}

function runCheckedPreparationCommand(command: string, args: string[], cwd: string, description: string): string {
  const result = spawnSync(command, args, {
    cwd,
    encoding: 'utf-8',
    shell: shouldUseShellForCommand(command)
  });
  const stdout = result.stdout ?? '';
  const stderr = result.stderr ?? '';
  const combinedOutput = `${stdout}\n${stderr}`.trim();
  if (result.error) {
    throw new Error(`Failed to ${description}: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const tail = combinedOutput ? `\n${combinedOutput.slice(-4_000)}` : '';
    throw new Error(`Failed to ${description}: ${command} ${args.join(' ')} exited with status ${result.status ?? 'unknown'}.${tail}`);
  }
  return stdout.trim();
}

function parseClasspathOutput(output: string): string {
  const classpath = output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .at(-1);
  if (!classpath) {
    throw new Error('Failed to resolve Maven runtime classpath: Maven returned empty classpath output.');
  }
  return classpath;
}

export function buildMavenModelLaunchCommand(
  mavenBin: string,
  request: ModelLaunchRequest,
  preparedRuntime?: PreparedMavenRuntime
): ModelLauncherCommand {
  const javaExe = preparedRuntime?.javaExe ?? getConfiguredJavaBin();
  const classpath = preparedRuntime?.classpath ?? '<prepared-classpath>';

  return {
    command: javaExe,
    args: ['-cp', classpath, 'housing.Model', '-configFile', request.configPath, '-outputFolder', request.outputPath, '-dev'],
    options: {
      cwd: request.repoRoot,
      shell: false
    },
    commandTemplate: `${mavenBin} -q -DskipTests compile && ${javaExe} -cp <prepared-classpath> housing.Model -configFile <path> -outputFolder <path> -dev`
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

export function createMavenModelLauncher(mavenBin = getConfiguredMavenBin(), javaExe = getConfiguredJavaBin()): ModelLauncher {
  const preparedByRepoRoot = new Map<string, PreparedMavenRuntime>();
  const metadata: ModelLauncherMetadata = {
    mode: 'maven',
    mavenBin,
    javaExe,
    commandTemplate: `${mavenBin} -q -DskipTests compile && ${javaExe} -cp <prepared-classpath> housing.Model -configFile <path> -outputFolder <path> -dev`
  };

  const prepare = (request: Pick<ModelLaunchRequest, 'repoRoot'>): PreparedMavenRuntime => {
    const repoRoot = path.resolve(request.repoRoot);
    const cached = preparedByRepoRoot.get(repoRoot);
    if (cached) {
      return cached;
    }

    runCheckedPreparationCommand(mavenBin, ['-q', '-DskipTests', 'compile'], repoRoot, 'compile the model for dashboard execution');
    const classpathOutput = runCheckedPreparationCommand(
      mavenBin,
      ['-q', '-Dexec.classpathScope=runtime', '-Dexec.executable=echo', '-Dexec.args=%classpath', 'exec:exec'],
      repoRoot,
      'resolve the model runtime classpath'
    );
    const preparedRuntime = {
      javaExe,
      classpath: parseClasspathOutput(classpathOutput)
    };
    preparedByRepoRoot.set(repoRoot, preparedRuntime);
    return preparedRuntime;
  };

  return {
    mode: 'maven',
    metadata,
    prepare: (request) => {
      prepare(request);
    },
    buildCommand: (request) =>
      buildMavenModelLaunchCommand(
        mavenBin,
        request,
        preparedByRepoRoot.get(path.resolve(request.repoRoot)) ?? { javaExe, classpath: '<prepared-classpath>' }
      ),
    launch: (request) => {
      const command = buildMavenModelLaunchCommand(mavenBin, request, prepare(request));
      return spawnCommand(command.command, command.args, command.options);
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
      return spawnCommand(command.command, command.args, command.options);
    }
  };
}
