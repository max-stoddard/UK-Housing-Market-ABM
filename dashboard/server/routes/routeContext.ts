import type express from 'express';
import type { LogLineSink } from '../lib/logs/logBuffer';
import type { ModelLauncher } from '../lib/modelLauncher';
import type { RemoteExecutionManager } from '../lib/remoteExecution';
import type { RuntimeDependencyStatus } from '../lib/runtimeDeps';
import type { RuntimePaths } from '../lib/runtimePaths';
import type { WriteAuthController } from '../lib/writeAuth';

export interface RuntimePolicy {
  viewMode: 'dev' | 'preview_desktop' | 'preview_cloud';
  devBypassActive: boolean;
  downloadBypassActive: boolean;
  modelRunsConfigured: boolean;
  modelRunsEnabled: boolean;
  modelRunsDisabledReason: string | null;
  writeAuthConfigurationError: string | null;
}

export interface RouteContext {
  repoRoot: string;
  runtimePaths: RuntimePaths;
  modelRunsConfiguredFromEnv: boolean;
  writeAuth: WriteAuthController;
  launcher?: ModelLauncher;
  remoteExecution?: RemoteExecutionManager;
  modelLogSink?: LogLineSink;
  getRuntimeDependencies: () => RuntimeDependencyStatus;
  resolveRuntimePolicy: (req: express.Request) => RuntimePolicy;
  requireDownloadAccess: (req: express.Request, res: express.Response) => boolean;
  requireWriteAccess: (req: express.Request, res: express.Response) => boolean;
  requireExperimentsFeature: (req: express.Request, res: express.Response) => boolean;
  withMemoryLogging: (label: string, handler: express.RequestHandler) => express.RequestHandler;
}
