import express from 'express';
import path from 'node:path';
import { checkRuntimeDependencies } from './lib/runtimeDeps';
import { createWriteAuthControllerFromEnv, getWriteAuthConfigurationError, resolveDashboardWriteAccess } from './lib/writeAuth';
import { registerPublicRoutes } from './routes/publicRoutes';
import type { RouteContext, RuntimePolicy } from './routes/routeContext';

const dashboardRoot = process.cwd();
const repoRoot = path.resolve(dashboardRoot, '..');

const app = express();
const host = '0.0.0.0';
const port = Number.parseInt(process.env.PORT ?? process.env.DASHBOARD_API_PORT ?? '8787', 10);
const corsOrigin = process.env.DASHBOARD_CORS_ORIGIN?.trim() ?? '';
const modelRunsConfiguredFromEnv = (process.env.DASHBOARD_ENABLE_MODEL_RUNS?.trim().toLowerCase() ?? '') === 'true';
const writeAuth = createWriteAuthControllerFromEnv();
const isDevRuntime = (process.env.NODE_ENV?.trim().toLowerCase() ?? '') !== 'production';
const memoryLoggingEnabled = (process.env.DASHBOARD_LOG_MEMORY?.trim().toLowerCase() ?? '') === 'true';
const startupRuntimeDependencies = getRuntimeDependencies();
const MODEL_RUNS_DISABLED_REASON_CONFIG =
  'Model execution is disabled in this environment.';
const MODEL_RUNS_DISABLED_REASON_RUNTIME =
  'Model execution is unavailable because Java/Maven are missing in this API runtime. Deploy API with Docker runtime (Java+Maven) or install dependencies.';
const EXPERIMENTS_DISABLED_REASON =
  'Experiments are not available in this environment.';

function getRuntimeDependencies() {
  return checkRuntimeDependencies();
}

function isPreviewStrictRequest(req: express.Request): boolean {
  const viewMode = req.get('X-Dashboard-View-Mode')?.trim().toLowerCase() ?? '';
  return viewMode === 'non_dev_preview';
}

function resolveRuntimePolicy(req: express.Request): RuntimePolicy {
  const devBypassActive = isDevRuntime && !isPreviewStrictRequest(req);
  const modelRunsConfigured = devBypassActive ? true : modelRunsConfiguredFromEnv;
  const modelRunsEnabled = modelRunsConfigured && startupRuntimeDependencies.java.available && startupRuntimeDependencies.maven.available;
  const modelRunsDisabledReason = modelRunsEnabled
    ? null
    : modelRunsConfigured
      ? MODEL_RUNS_DISABLED_REASON_RUNTIME
      : MODEL_RUNS_DISABLED_REASON_CONFIG;
  const writeAuthConfigurationError = getWriteAuthConfigurationError(writeAuth, modelRunsEnabled, devBypassActive);

  return {
    devBypassActive,
    modelRunsConfigured,
    modelRunsEnabled,
    modelRunsDisabledReason,
    writeAuthConfigurationError
  };
}

function requireWriteAccess(req: express.Request, res: express.Response): boolean {
  const policy = resolveRuntimePolicy(req);
  const access = resolveDashboardWriteAccess(
    writeAuth,
    req.get('authorization'),
    policy.modelRunsEnabled,
    policy.devBypassActive
  );
  if (access.canWrite) {
    return true;
  }
  if (access.authMisconfigured) {
    res.status(503).json({
      error: policy.writeAuthConfigurationError ?? 'Write access is unavailable due to server configuration.'
    });
    return false;
  }
  res.status(403).json({ error: 'Write access requires login.' });
  return false;
}

function experimentsFeatureEnabled(): boolean {
  return true;
}

function requireExperimentsFeature(req: express.Request, res: express.Response): boolean {
  void req;
  if (experimentsFeatureEnabled()) {
    return true;
  }
  res.status(404).json({ error: EXPERIMENTS_DISABLED_REASON });
  return false;
}

function withMemoryLogging(label: string, handler: express.RequestHandler): express.RequestHandler {
  return (req, res, next) => {
    const startNs = process.hrtime.bigint();
    const startMemory = memoryLoggingEnabled ? process.memoryUsage() : null;

    if (memoryLoggingEnabled) {
      res.once('finish', () => {
        const endMemory = process.memoryUsage();
        const elapsedMs = Number(process.hrtime.bigint() - startNs) / 1_000_000;
        const rssDeltaMb = (endMemory.rss - (startMemory?.rss ?? 0)) / (1024 * 1024);
        const heapDeltaMb = (endMemory.heapUsed - (startMemory?.heapUsed ?? 0)) / (1024 * 1024);
        console.log(
          `[memory] ${label} ${req.method} ${req.originalUrl} status=${res.statusCode} ` +
            `durationMs=${elapsedMs.toFixed(1)} rssMb=${(endMemory.rss / (1024 * 1024)).toFixed(1)} ` +
            `heapMb=${(endMemory.heapUsed / (1024 * 1024)).toFixed(1)} ` +
            `rssDeltaMb=${rssDeltaMb.toFixed(1)} heapDeltaMb=${heapDeltaMb.toFixed(1)}`
        );
      });
    }

    void Promise.resolve(handler(req, res, next)).catch(next);
  };
}

function logRuntimeDependencies(): void {
  console.log(`[runtime-deps] java=${startupRuntimeDependencies.java.available ? 'available' : 'missing'}`);
  if (startupRuntimeDependencies.java.versionOutput) {
    console.log(`[runtime-deps] java version: ${startupRuntimeDependencies.java.versionOutput.split('\n')[0]}`);
  }
  if (startupRuntimeDependencies.java.error) {
    console.error(`[runtime-deps] java error: ${startupRuntimeDependencies.java.error}`);
  }

  console.log(
    `[runtime-deps] maven=${startupRuntimeDependencies.maven.available ? 'available' : 'missing'} (bin=${startupRuntimeDependencies.mavenBin})`
  );
  if (startupRuntimeDependencies.maven.versionOutput) {
    console.log(`[runtime-deps] maven version: ${startupRuntimeDependencies.maven.versionOutput.split('\n')[0]}`);
  }
  if (startupRuntimeDependencies.maven.error) {
    console.error(`[runtime-deps] maven error: ${startupRuntimeDependencies.maven.error}`);
  }

  if (modelRunsConfiguredFromEnv && (!startupRuntimeDependencies.java.available || !startupRuntimeDependencies.maven.available)) {
    console.error(
      '[dashboard-api] Model runs requested, but Java/Maven runtime dependencies are unavailable. ' +
        'API will remain online in read-only mode for model runs until dependencies are present.'
    );
  }
}

async function bootstrap(): Promise<void> {
  logRuntimeDependencies();

  app.use(express.json());
  app.use((req, res, next) => {
    if (!corsOrigin) {
      next();
      return;
    }

    const requestOrigin = req.get('origin');
    if (requestOrigin && requestOrigin === corsOrigin) {
      res.setHeader('Access-Control-Allow-Origin', corsOrigin);
      res.setHeader('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Dashboard-View-Mode');
      res.setHeader('Vary', 'Origin');
    }

    if (req.method === 'OPTIONS') {
      res.status(204).end();
      return;
    }

    next();
  });

  const routeContext: RouteContext = {
    repoRoot,
    modelRunsConfiguredFromEnv,
    writeAuth,
    getRuntimeDependencies,
    resolveRuntimePolicy,
    requireWriteAccess,
    requireExperimentsFeature,
    withMemoryLogging
  };

  registerPublicRoutes(app, routeContext);

  const { registerDevRoutes } = await import('./routes/devRoutes');
  registerDevRoutes(app, routeContext);

  app.listen(port, host, () => {
    console.log(`[dashboard-api] listening on ${host}:${port}`);
  });
}

void bootstrap();
