# UK Housing Model Dashboard
Author: Max Stoddard

Local React dashboard for visualizing `input-data-versions/` model parameters, with optional version comparison and provenance tracking.

## Toolchain

Use Node 22 for dashboard work. `dashboard/.nvmrc` and `dashboard/package.json` `engines.node` are the source of truth for local development, CI, and the Render static build.

## Run

From repository root:

```bash
./run-dashboard.sh
```

## Useful commands

```bash
cd dashboard
npm run lint
npm run build
npm run test:smoke
npm run start:server
```

## Production Runtime

The frontend can call either same-origin API routes or an external API base URL.

- `VITE_API_BASE_URL` (optional): absolute API origin, for example `https://uk-housing-market-abm-api.onrender.com`
  - if unset, frontend calls relative `/api/*` paths.

Dashboard API environment variables:

- `PORT` (preferred in production): HTTP port.
- `DASHBOARD_API_PORT` (local fallback): HTTP port when `PORT` is not set.
- `DASHBOARD_CORS_ORIGIN` (optional): allowed browser origin for cross-origin requests (for split frontend/API deploys).
- `DASHBOARD_ENABLE_MODEL_RUNS` (optional): set to `true` to enable model execution APIs in non-dev runtimes.
- `DASHBOARD_WRITE_USERNAME` + `DASHBOARD_WRITE_PASSWORD` (optional pair): enables write-login mode when both are set.
- `DASHBOARD_MAVEN_BIN` (optional): Maven executable used by model runs (defaults to `mvn`).
- `DASHBOARD_RESULTS_CAP_MB` (optional): total `Results/` storage cap in MB for dashboard-managed runs (defaults to `400`). New run submissions are blocked when usage is at/above cap after managed-run pruning.
- `DASHBOARD_LOG_MEMORY` (optional): set to `true` to log request duration plus RSS/heap deltas for public API routes.

Runtime target compatibility:

| Target | Runtime shape | Model execution | Writable/auth boundary |
| --- | --- | --- | --- |
| Dev mode | Repo-shaped local workflow using the developer machine's Node, Java, and Maven. | Enabled by default in non-production when Java/Maven are available. | Dev bypass is active only when `NODE_ENV != production` and the request is not `Preview non-dev`; no cloud or desktop runtime should depend on it. |
| Cloud mode | Lightweight public API/container path from `dashboard/Dockerfile.api`; no Electron requirement. | `DASHBOARD_ENABLE_MODEL_RUNS=false` by default; `/healthz`, `/api/runtime-deps`, and read routes remain usable without Java or Maven. | Public API image must not include Java, Maven, git, `private-datasets/`, or baseline `Results/`; public model execution fails closed. |
| Desktop mode | Electron-owned local server on `127.0.0.1` with random port, packaged Java 25 runtime/fat jar, and Electron `userData` writable roots. | Packaged launcher for dashboard-managed manual and sensitivity runs; release resources are assembled from allowlisted input data and the runnable model jar. | Per-session bearer token and no packaged dev bypass; release data stays allowlisted and separate from cloud credentials/resources. |

Experiments availability:

- The `Experiments` navigation item, `/experiments`, and `/login` are available in dev, production, and `Preview non-dev`.
- Experiment, model-run, results-management, and auth-for-experiments API routes are registered in every runtime.
- Actual model execution remains controlled separately by `DASHBOARD_ENABLE_MODEL_RUNS`, Java/Maven runtime availability, and write credentials.
- The homepage no longer shows git-history stats; production avoids all git/GitHub diff work entirely.

Write-access behavior:

- If `DASHBOARD_WRITE_USERNAME` and `DASHBOARD_WRITE_PASSWORD` are both unset:
  - auth is disabled,
  - local development can use write features without login.
- If both are set:
  - dashboard write actions require login (single global username/password),
  - read-only pages remain available without login.
- If model runs are enabled (`DASHBOARD_ENABLE_MODEL_RUNS=true`) but credentials are unset:
  - API enters fail-closed mode for write actions (`503`),
  - login is intentionally disabled until credentials are configured,
  - read-only pages remain available.

Write actions requiring login in auth-enabled mode:

- queue model runs
- cancel model runs
- clear finished jobs from queue history
- delete manual result runs from Experiments (`type=manual`, `mode=view`)
- start sensitivity experiments
- cancel sensitivity experiments
- cancel unified experiment jobs (`POST /api/experiments/jobs/:jobRef/cancel`)

Sensitivity API endpoints:

- `GET /api/experiments/sensitivity`
- `POST /api/experiments/sensitivity`
- `GET /api/experiments/sensitivity/:experimentId`
- `GET /api/experiments/sensitivity/:experimentId/results`
- `GET /api/experiments/sensitivity/:experimentId/charts`
- `GET /api/experiments/sensitivity/:experimentId/logs`
- `POST /api/experiments/sensitivity/:experimentId/cancel`

Unified experiment monitoring endpoints:

- `GET /api/experiments/jobs`
- `GET /api/experiments/jobs/:jobRef/logs`
- `POST /api/experiments/jobs/:jobRef/cancel`

Experiments route:

- Available in local dev view, production, and `Preview non-dev`.
- Unified page at `/experiments` with query-based selectors.
- `type=manual|sensitivity` and `mode=run|view` drive setup/results combinations.
- optional focus params: `jobRef` (run mode queue/log), `runId` (manual view), `experimentId` (sensitivity view).

KPI definitions (tail-120 window, used for manual KPI cards and sensitivity analytics):

- `Mean`: arithmetic mean of the tail-120 monthly values.
- `CV`: `stdev / abs(mean)`; returns `null` when `abs(mean)` is near zero.
- `Annualised Trend`: OLS monthly slope multiplied by `12`.
- `Range`: `P95 - P5` using linear percentile interpolation.

Sensitivity behavior:

- one-at-a-time numeric USER SET parameter sweeps (manual min/max, baseline-in-range required)
- 5-point sampling (`min`, `mid-lower`, `baseline`, `mid-upper`, `max`) with integer rounding and duplicate collapse
- summary-first retention by default (per-point outputs deleted after summary extraction)
- optional full-output retention under `Results/experiments/sensitivity/<experimentId>/points`
- persisted experiment metadata + chart-ready summaries under `Results/experiments/sensitivity/<experimentId>`
- merged live logs with lifecycle markers + stdout/stderr stream under sensitivity and unified logs endpoints
- tornado charts support KPI-basis selection (`Mean`, `CV`, `Annualised Trend`, `Range`)
- manual run submissions are blocked while a sensitivity experiment is active, and sensitivity submissions are blocked while manual jobs are active

### Local Auth Setup

Default local workflow (no login lockout):

```bash
cd dashboard
npm run dev
```

Local development defaults:

- when running in local dev (`NODE_ENV != production`), dashboard requests run in dev view mode by default.
- dev view mode bypasses write-auth configuration lockouts so `Experiments` run mode is usable without setting credentials.
- actual run execution still requires Java and Maven in the API runtime.
- use the `Preview non-dev` toggle in the app header (shown in dev) to switch to the same runtime/auth policy used by Render production.

Optional local auth testing (login required):

```bash
cd dashboard
export DASHBOARD_ENABLE_MODEL_RUNS=true
export DASHBOARD_WRITE_USERNAME=admin
export DASHBOARD_WRITE_PASSWORD=change-me
npm run dev
```

Then open `/login` in the web app and sign in with that username/password.

Health endpoint:

- `GET /healthz`
- `GET /api/runtime-deps` (runtime diagnostics):
  - returns `java`, `maven`, `mavenBin`, and `versionInfo` for dependency checks.

Homepage preview endpoint:

- `GET /api/home-preview?version=<version>`
- returns only the lightweight chart payload needed for the homepage hero preview
- avoids dashboard input version history, dataset attribution, and other compare-page metadata
- keeps the homepage live without forcing the full compare path on first public load

## Render Deployment

Repository root includes `render.yaml` with:

- static web service: `uk-housing-market-abm`
- API web service: `uk-housing-market-abm-api` (slim Docker runtime for public dashboard APIs)

The public Render API is intentionally lightweight:

- Dockerfile: `dashboard/Dockerfile.api`
- base image: Node 22 slim, aligned with dashboard CI
- ships only the public dashboard server plus `input-data-versions`
- does not include git, Java, Maven, or baseline `Results/` outputs
- uses compiled server output (`dist-server`) instead of running through `tsx`

The Render static service builds only the client bundle with `npm run build:client`. Server compilation remains part of local/CI full builds and the API container validation job.

Render production defaults to `DASHBOARD_ENABLE_MODEL_RUNS=false`, which keeps the Experiments workspace visible but disables model execution.

If you intentionally want remote experiment execution again, treat it as a separate service concern. The public 512 MB instance is not intended to host model execution or results analytics.

Local development remains the supported way to use experiments. If you still want to re-enable them in another environment, start with:

- `DASHBOARD_ENABLE_MODEL_RUNS=true`
- `DASHBOARD_WRITE_USERNAME` (secret)
- `DASHBOARD_WRITE_PASSWORD` (secret)

Deploys are configured from `master` and gated by passing GitHub checks.

GitHub Actions validates:

- `npm run lint`
- `npm run build`
- `npm run test:smoke`
- `docker build -f dashboard/Dockerfile.api .` whenever API deployment inputs change (`dashboard/server/**`, `dashboard/shared/**`, `dashboard/Dockerfile.api`, `dashboard/tsconfig.server.json`, `input-data-versions/**`, `.dockerignore`, or dashboard package manifests)

If Render stops showing commit events (for example, "No event for this commit"), first re-link the service repository in Render to the current GitHub repo identity (`max-stoddard/UK-Housing-Market-ABM`) and re-sync the Blueprint.

Changes to `render.yaml` still require a Render Blueprint sync. The optional GitHub deploy-hook fallback does not apply Blueprint config updates on its own.

Optional resilience fallback:

- add `RENDER_STATIC_DEPLOY_HOOK` and `RENDER_API_DEPLOY_HOOK` as GitHub repository secrets
- `.github/workflows/dashboard-ci.yml` will call these hooks after checks pass on `master`, only when matching service inputs changed
