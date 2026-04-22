import type express from 'express';
import { compareParameters, getHomePreview, getInProgressVersions, getParameterCatalog, getValidationOverview, getVersions } from '../lib/service';
import { resolveDashboardWriteAccess } from '../lib/writeAuth';
import type { RouteContext } from './routeContext';

const HOME_PREVIEW_PARAMETER_IDS = [
  'wealth_given_income_joint',
  'house_price_lognormal',
  'downpayment_oo_lognormal',
  'btl_probability_bins'
];

export function registerPublicRoutes(app: express.Express, context: RouteContext): void {
  app.get('/healthz', (_req, res) => {
    res.json({ ok: true });
  });

  app.get('/api/runtime-deps', context.withMemoryLogging('runtime-deps', (_req, res) => {
    const deps = context.getRuntimeDependencies();
    res.json({
      java: deps.java.available,
      maven: deps.maven.available,
      mavenBin: deps.mavenBin,
      modelRunsConfigured: context.modelRunsConfiguredFromEnv,
      modelRunsEnabled: context.modelRunsConfiguredFromEnv && deps.java.available && deps.maven.available,
      versionInfo: {
        java: deps.java.versionOutput || null,
        maven: deps.maven.versionOutput || null,
        javaError: deps.java.error ?? null,
        mavenError: deps.maven.error ?? null
      }
    });
  }));

  app.get('/api/auth/status', context.withMemoryLogging('auth-status', (req, res) => {
    const policy = context.resolveRuntimePolicy(req);
    const access = resolveDashboardWriteAccess(
      context.writeAuth,
      req.get('authorization'),
      policy.modelRunsEnabled,
      policy.devBypassActive
    );
    res.json({
      authEnabled: access.authEnabled,
      canWrite: access.canWrite,
      authMisconfigured: access.authMisconfigured,
      modelRunsEnabled: policy.modelRunsEnabled,
      modelRunsConfigured: policy.modelRunsConfigured,
      modelRunsDisabledReason: policy.modelRunsDisabledReason
    });
  }));

  app.get('/api/versions', context.withMemoryLogging('versions', (_req, res) => {
    try {
      const versions = getVersions(context.repoRoot);
      const inProgressVersions = getInProgressVersions(context.repoRoot);
      res.json({ versions, inProgressVersions });
    } catch (error) {
      res.status(500).json({ error: (error as Error).message });
    }
  }));

  app.get('/api/validation-overview', context.withMemoryLogging('validation-overview', (req, res) => {
    try {
      const version = String(req.query.version ?? '').trim();
      const viewParam = String(req.query.view ?? 'tracked').trim();
      const view = viewParam === 'reference_2011' ? 'reference_2011' : 'tracked';
      res.json(getValidationOverview(context.repoRoot, version || undefined, view));
    } catch (error) {
      res.status(500).json({ error: (error as Error).message });
    }
  }));

  app.get('/api/parameter-catalog', context.withMemoryLogging('parameter-catalog', (_req, res) => {
    res.json({ items: getParameterCatalog() });
  }));

  app.get('/api/home-preview', context.withMemoryLogging('home-preview', (req, res) => {
    const version = String(req.query.version ?? '').trim();
    if (!version) {
      res.status(400).json({ error: 'version query parameter is required' });
      return;
    }

    try {
      res.json(getHomePreview(context.repoRoot, version, HOME_PREVIEW_PARAMETER_IDS));
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  }));

  app.get('/api/compare', context.withMemoryLogging('compare', (req, res) => {
    const left = String(req.query.left ?? '');
    const right = String(req.query.right ?? '');
    const idsParam = String(req.query.ids ?? '');
    const provenanceScopeParam = String(req.query.provenanceScope ?? 'range');

    if (!left || !right) {
      res.status(400).json({ error: 'left and right query parameters are required' });
      return;
    }

    const ids = idsParam
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean);

    const provenanceScope = provenanceScopeParam === 'through_right' ? 'through_right' : 'range';

    try {
      const payload = compareParameters(context.repoRoot, left, right, ids, provenanceScope);
      res.json(payload);
    } catch (error) {
      res.status(400).json({ error: (error as Error).message });
    }
  }));
}
