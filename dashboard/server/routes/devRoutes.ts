import type express from 'express';
import {
  deleteResultsRun,
  getResultsCompare,
  getResultsRunDetail,
  getResultsRunFiles,
  getResultsRuns,
  getResultsSeries
} from '../lib/results';
import {
  cancelModelRunJob,
  clearModelRunJob,
  getModelRunJob,
  getModelRunJobLogs,
  getModelRunOptions,
  getResultsStorageSummary,
  listModelRunJobs,
  submitModelRun
} from '../lib/modelRuns';
import { cancelExperimentJob, getExperimentJobLogs, listExperimentJobs } from '../lib/experimentJobs';
import {
  cancelSensitivityExperiment,
  getActiveSensitivityExperimentId,
  getSensitivityExperiment,
  getSensitivityExperimentCharts,
  getSensitivityExperimentLogs,
  getSensitivityExperimentResults,
  hasActiveSensitivityExperiment,
  listSensitivityExperiments,
  submitSensitivityExperiment
} from '../lib/sensitivityRuns';
import type { RouteContext } from './routeContext';

const MODEL_RUNS_DISABLED_REASON_CONFIG =
  'Model execution is disabled in this environment.';

export function registerDevRoutes(app: express.Express, context: RouteContext): void {
  app.post('/api/auth/login', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }

    const policy = context.resolveRuntimePolicy(req);
    if (policy.writeAuthConfigurationError) {
      res.status(503).json({ error: policy.writeAuthConfigurationError });
      return;
    }

    const username = typeof req.body?.username === 'string' ? req.body.username : '';
    const password = typeof req.body?.password === 'string' ? req.body.password : '';
    const result = context.writeAuth.login(username, password);
    if (!result.ok) {
      res.status(401).json({ error: 'Invalid username or password.' });
      return;
    }
    res.json(result);
  });

  app.post('/api/auth/logout', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const access = context.writeAuth.resolveAccess(req.get('authorization'));
    context.writeAuth.logout(access.token);
    res.json({ ok: true });
  });

  app.get('/api/results/runs', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      const runs = getResultsRuns(context.runtimePaths);
      res.json({ runs });
    } catch (error) {
      res.status(500).json({ error: (error as Error).message });
    }
  });

  app.get('/api/results/storage', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      res.json(getResultsStorageSummary(context.runtimePaths));
    } catch (error) {
      res.status(500).json({ error: (error as Error).message });
    }
  });

  app.get('/api/results/runs/:runId', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      const detail = getResultsRunDetail(context.runtimePaths, String(req.params.runId ?? ''));
      res.json(detail);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/results/runs/:runId/files', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      const files = getResultsRunFiles(context.runtimePaths, String(req.params.runId ?? ''));
      res.json({ runId: String(req.params.runId ?? ''), files });
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.delete('/api/results/runs/:runId', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    if (!context.requireWriteAccess(req, res)) {
      return;
    }

    try {
      const payload = deleteResultsRun(context.runtimePaths, String(req.params.runId ?? ''));
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/results/runs/:runId/series', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const runId = String(req.params.runId ?? '');
    const indicator = String(req.query.indicator ?? '');
    if (!indicator) {
      res.status(400).json({ error: 'indicator query parameter is required' });
      return;
    }

    const rawSmoothWindow = Number.parseInt(String(req.query.smoothWindow ?? '0'), 10);
    const smoothWindow = Number.isFinite(rawSmoothWindow) ? rawSmoothWindow : 0;

    try {
      const payload = getResultsSeries(context.runtimePaths, runId, indicator, smoothWindow);
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/results/compare', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const runIds = String(req.query.runIds ?? '')
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean);
    const indicatorIds = String(req.query.indicatorIds ?? '')
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean);
    const window = String(req.query.window ?? 'post200');
    const rawSmoothWindow = Number.parseInt(String(req.query.smoothWindow ?? '0'), 10);
    const smoothWindow = Number.isFinite(rawSmoothWindow) ? rawSmoothWindow : 0;

    try {
      const payload = getResultsCompare(context.runtimePaths, runIds, indicatorIds, window, smoothWindow);
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/model-runs/options', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      const policy = context.resolveRuntimePolicy(req);
      const baseline = String(req.query.baseline ?? '').trim() || undefined;
      const payload = getModelRunOptions(context.runtimePaths, baseline, policy.modelRunsEnabled);
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.post('/api/model-runs', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }
    if (!context.requireWriteAccess(req, res)) {
      return;
    }

    if (hasActiveSensitivityExperiment(context.runtimePaths)) {
      const experimentId = getActiveSensitivityExperimentId(context.runtimePaths);
      res.status(409).json({
        error: `Cannot queue manual runs while sensitivity experiment ${experimentId ?? ''} is active.`.trim()
      });
      return;
    }

    try {
      const payload = submitModelRun(context.runtimePaths, req.body, {
        ignoreStorageCap: policy.devBypassActive,
        launcher: context.launcher,
        logSink: context.modelLogSink
      });
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/model-runs/jobs', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }

    try {
      res.json({ jobs: listModelRunJobs() });
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/model-runs/jobs/:jobId', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }

    try {
      res.json(getModelRunJob(String(req.params.jobId ?? '')));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.post('/api/model-runs/jobs/:jobId/cancel', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }
    if (!context.requireWriteAccess(req, res)) {
      return;
    }

    try {
      res.json(cancelModelRunJob(context.runtimePaths, String(req.params.jobId ?? '')));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.delete('/api/model-runs/jobs/:jobId', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }
    if (!context.requireWriteAccess(req, res)) {
      return;
    }

    try {
      res.json(clearModelRunJob(String(req.params.jobId ?? '')));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/model-runs/jobs/:jobId/logs', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }

    const cursorRaw = Number.parseInt(String(req.query.cursor ?? '0'), 10);
    const limitRaw = Number.parseInt(String(req.query.limit ?? '200'), 10);

    try {
      const payload = getModelRunJobLogs(
        String(req.params.jobId ?? ''),
        Number.isFinite(cursorRaw) ? cursorRaw : undefined,
        Number.isFinite(limitRaw) ? limitRaw : undefined
      );
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/experiments/sensitivity', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      res.json(listSensitivityExperiments(context.runtimePaths));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.post('/api/experiments/sensitivity', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }
    if (!context.requireWriteAccess(req, res)) {
      return;
    }

    try {
      const payload = submitSensitivityExperiment(context.runtimePaths, req.body, {
        launcher: context.launcher,
        logSink: context.modelLogSink
      });
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/experiments/sensitivity/:experimentId', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      res.json(getSensitivityExperiment(context.runtimePaths, String(req.params.experimentId ?? '')));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/experiments/sensitivity/:experimentId/results', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      res.json(getSensitivityExperimentResults(context.runtimePaths, String(req.params.experimentId ?? '')));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/experiments/sensitivity/:experimentId/charts', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      res.json(getSensitivityExperimentCharts(context.runtimePaths, String(req.params.experimentId ?? '')));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/experiments/sensitivity/:experimentId/logs', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const cursorRaw = Number.parseInt(String(req.query.cursor ?? '0'), 10);
    const limitRaw = Number.parseInt(String(req.query.limit ?? '200'), 10);

    try {
      const payload = getSensitivityExperimentLogs(
        context.runtimePaths,
        String(req.params.experimentId ?? ''),
        Number.isFinite(cursorRaw) ? cursorRaw : undefined,
        Number.isFinite(limitRaw) ? limitRaw : undefined
      );
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.post('/api/experiments/sensitivity/:experimentId/cancel', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }
    if (!context.requireWriteAccess(req, res)) {
      return;
    }

    try {
      res.json(cancelSensitivityExperiment(context.runtimePaths, String(req.params.experimentId ?? '')));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/experiments/jobs', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    try {
      res.json(listExperimentJobs(context.runtimePaths));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.get('/api/experiments/jobs/:jobRef/logs', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const cursorRaw = Number.parseInt(String(req.query.cursor ?? '0'), 10);
    const limitRaw = Number.parseInt(String(req.query.limit ?? '200'), 10);

    try {
      const payload = getExperimentJobLogs(
        context.runtimePaths,
        String(req.params.jobRef ?? ''),
        Number.isFinite(cursorRaw) ? cursorRaw : undefined,
        Number.isFinite(limitRaw) ? limitRaw : undefined
      );
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });

  app.post('/api/experiments/jobs/:jobRef/cancel', (req, res) => {
    if (!context.requireExperimentsFeature(req, res)) {
      return;
    }
    const policy = context.resolveRuntimePolicy(req);
    if (!policy.modelRunsEnabled) {
      res.status(403).json({ error: policy.modelRunsDisabledReason ?? MODEL_RUNS_DISABLED_REASON_CONFIG });
      return;
    }
    if (!context.requireWriteAccess(req, res)) {
      return;
    }

    try {
      res.json(cancelExperimentJob(context.runtimePaths, String(req.params.jobRef ?? '')));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  });
}
