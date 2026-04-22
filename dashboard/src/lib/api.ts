import type {
  AuthLoginRequest,
  AuthLoginResponse,
  AuthLogoutResponse,
  AuthStatusPayload,
  CompareResponse,
  ExperimentJobCancelResponse,
  ExperimentJobLogsPayload,
  ExperimentJobsPayload,
  HomePreviewPayload,
  ModelRunJob,
  ModelRunJobClearResponse,
  ModelRunJobLogsPayload,
  ModelRunJobsPayload,
  ModelRunOptionsPayload,
  ModelRunSubmitRequest,
  ModelRunSubmitResponse,
  ParameterCardMeta,
  ResultsComparePayload,
  ResultsFileManifestEntry,
  ResultsRunDeleteResponse,
  ResultsRunDetail,
  ResultsRunSummary,
  ResultsStorageSummary,
  ResultsSeriesPayload,
  SensitivityExperimentChartsPayload,
  SensitivityExperimentCreateRequest,
  SensitivityExperimentDetailPayload,
  SensitivityExperimentListPayload,
  SensitivityExperimentLogsPayload,
  SensitivityExperimentResultsPayload,
  SensitivityExperimentSubmitResponse,
  ValidationOverviewPayload
} from '../../shared/types';

interface VersionsResponse {
  versions: string[];
  inProgressVersions?: string[];
}

export interface VersionsPayload {
  versions: string[];
  inProgressVersions: string[];
}

export type ValidationOverviewViewMode = 'tracked' | 'reference_2011';

interface CatalogResponse {
  items: ParameterCardMeta[];
}

interface ResultsRunsResponse {
  runs: ResultsRunSummary[];
}

interface ResultsRunFilesResponse {
  runId: string;
  files: ResultsFileManifestEntry[];
}

export class ApiRequestError extends Error {
  retryable: boolean;
  status: number | null;

  constructor(message: string, retryable: boolean, status: number | null) {
    super(message);
    this.name = 'ApiRequestError';
    this.retryable = retryable;
    this.status = status;
  }
}

export const API_RETRY_DELAY_MS = 2000;

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '');
let authToken: string | null = null;
export type ApiViewMode = 'dev' | 'non_dev_preview';
let apiViewMode: ApiViewMode = import.meta.env.DEV ? 'dev' : 'non_dev_preview';

function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return apiBaseUrl ? `${apiBaseUrl}${normalizedPath}` : normalizedPath;
}

function withAuthHeaders(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers);
  if (authToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${authToken}`);
  }
  headers.set('X-Dashboard-View-Mode', apiViewMode);
  return {
    ...init,
    headers
  };
}

function isRetryableStatus(status: number): boolean {
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

async function readErrorMessage(response: Response, fallbackMessage: string): Promise<string> {
  try {
    const payload = (await response.json()) as { error?: string; message?: string };
    if (payload.error) {
      return payload.error;
    }
    if (payload.message) {
      return payload.message;
    }
  } catch {
    return fallbackMessage;
  }
  return fallbackMessage;
}

async function requestJson<T>(url: string, fallbackMessage: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, withAuthHeaders());
  } catch {
    throw new ApiRequestError(fallbackMessage, true, null);
  }

  if (!response.ok) {
    const message = await readErrorMessage(response, fallbackMessage);
    throw new ApiRequestError(message, isRetryableStatus(response.status), response.status);
  }

  return (await response.json()) as T;
}

async function requestJsonWithInit<T>(url: string, fallbackMessage: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, withAuthHeaders(init));
  } catch {
    throw new ApiRequestError(fallbackMessage, true, null);
  }

  if (!response.ok) {
    const message = await readErrorMessage(response, fallbackMessage);
    throw new ApiRequestError(message, isRetryableStatus(response.status), response.status);
  }

  return (await response.json()) as T;
}

export function isRetryableApiError(error: unknown): boolean {
  return error instanceof ApiRequestError && error.retryable;
}

export function setApiAuthToken(token: string | null): void {
  authToken = token;
}

export function getApiAuthToken(): string | null {
  return authToken;
}

export function setApiViewMode(mode: ApiViewMode): void {
  apiViewMode = mode;
}

export function getApiViewMode(): ApiViewMode {
  return apiViewMode;
}

export async function fetchAuthStatus(): Promise<AuthStatusPayload> {
  return requestJson<AuthStatusPayload>(buildApiUrl('/api/auth/status'), 'Failed to fetch auth status');
}

export async function loginWriteAccess(payload: AuthLoginRequest): Promise<AuthLoginResponse> {
  return requestJsonWithInit<AuthLoginResponse>(buildApiUrl('/api/auth/login'), 'Failed to login for write access', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
}

export async function logoutWriteAccess(): Promise<AuthLogoutResponse> {
  return requestJsonWithInit<AuthLogoutResponse>(buildApiUrl('/api/auth/logout'), 'Failed to logout', {
    method: 'POST'
  });
}

export async function fetchVersions(): Promise<VersionsPayload> {
  const payload = await requestJson<VersionsResponse>(buildApiUrl('/api/versions'), 'Failed to fetch versions');
  return {
    versions: payload.versions,
    inProgressVersions: payload.inProgressVersions ?? []
  };
}

export async function fetchValidationOverview(
  version?: string,
  view: ValidationOverviewViewMode = 'tracked'
): Promise<ValidationOverviewPayload> {
  const params = new URLSearchParams();
  if (version) {
    params.set('version', version);
  }
  params.set('view', view);
  const query = params.toString();
  const url = query ? `${buildApiUrl('/api/validation-overview')}?${query}` : buildApiUrl('/api/validation-overview');
  return requestJson<ValidationOverviewPayload>(url, 'Failed to fetch validation overview');
}

export async function fetchCatalog(): Promise<ParameterCardMeta[]> {
  const payload = await requestJson<CatalogResponse>(buildApiUrl('/api/parameter-catalog'), 'Failed to fetch parameter catalog');
  return payload.items;
}

export async function fetchHomePreview(version: string): Promise<HomePreviewPayload> {
  const params = new URLSearchParams({ version });
  return requestJson<HomePreviewPayload>(
    `${buildApiUrl('/api/home-preview')}?${params.toString()}`,
    'Failed to fetch homepage preview'
  );
}

export async function fetchCompare(
  left: string,
  right: string,
  ids: string[],
  provenanceScope: 'range' | 'through_right' = 'range'
): Promise<CompareResponse> {
  const params = new URLSearchParams({
    left,
    right,
    ids: ids.join(','),
    provenanceScope
  });

  return requestJson<CompareResponse>(`${buildApiUrl('/api/compare')}?${params.toString()}`, 'Failed to fetch comparison');
}

export async function fetchResultsRuns(): Promise<ResultsRunSummary[]> {
  const payload = await requestJson<ResultsRunsResponse>(buildApiUrl('/api/results/runs'), 'Failed to fetch results runs');
  return payload.runs;
}

export async function fetchResultsStorageSummary(): Promise<ResultsStorageSummary> {
  return requestJson<ResultsStorageSummary>(buildApiUrl('/api/results/storage'), 'Failed to fetch results storage summary');
}

export async function fetchResultsRunDetail(runId: string): Promise<ResultsRunDetail> {
  return requestJson<ResultsRunDetail>(buildApiUrl(`/api/results/runs/${encodeURIComponent(runId)}`), 'Failed to fetch run detail');
}

export async function fetchResultsRunFiles(runId: string): Promise<ResultsFileManifestEntry[]> {
  const payload = await requestJson<ResultsRunFilesResponse>(
    buildApiUrl(`/api/results/runs/${encodeURIComponent(runId)}/files`),
    'Failed to fetch run files'
  );
  return payload.files;
}

export async function deleteResultsRun(runId: string): Promise<ResultsRunDeleteResponse> {
  return requestJsonWithInit<ResultsRunDeleteResponse>(
    buildApiUrl(`/api/results/runs/${encodeURIComponent(runId)}`),
    'Failed to delete run',
    {
      method: 'DELETE'
    }
  );
}

export async function fetchResultsSeries(
  runId: string,
  indicatorId: string,
  smoothWindow: 0 | 3 | 12
): Promise<ResultsSeriesPayload> {
  const params = new URLSearchParams({
    indicator: indicatorId,
    smoothWindow: String(smoothWindow)
  });
  return requestJson<ResultsSeriesPayload>(
    `${buildApiUrl(`/api/results/runs/${encodeURIComponent(runId)}/series`)}?${params.toString()}`,
    'Failed to fetch series'
  );
}

export async function fetchResultsCompare(
  runIds: string[],
  indicatorIds: string[],
  window: 'post200' | 'tail120' | 'full',
  smoothWindow: 0 | 3 | 12
): Promise<ResultsComparePayload> {
  const params = new URLSearchParams({
    runIds: runIds.join(','),
    indicatorIds: indicatorIds.join(','),
    window,
    smoothWindow: String(smoothWindow)
  });
  return requestJson<ResultsComparePayload>(
    `${buildApiUrl('/api/results/compare')}?${params.toString()}`,
    'Failed to fetch results comparison'
  );
}

export async function fetchModelRunOptions(baseline?: string): Promise<ModelRunOptionsPayload> {
  const params = new URLSearchParams();
  if (baseline) {
    params.set('baseline', baseline);
  }
  const query = params.toString();
  const url = query ? `${buildApiUrl('/api/model-runs/options')}?${query}` : buildApiUrl('/api/model-runs/options');
  return requestJson<ModelRunOptionsPayload>(url, 'Failed to fetch model run options');
}

export async function submitModelRun(payload: ModelRunSubmitRequest): Promise<ModelRunSubmitResponse> {
  return requestJsonWithInit<ModelRunSubmitResponse>(buildApiUrl('/api/model-runs'), 'Failed to submit model run', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
}

export async function fetchModelRunJobs(): Promise<ModelRunJob[]> {
  const payload = await requestJson<ModelRunJobsPayload>(buildApiUrl('/api/model-runs/jobs'), 'Failed to fetch model run jobs');
  return payload.jobs;
}

export async function fetchModelRunJob(jobId: string): Promise<ModelRunJob> {
  return requestJson<ModelRunJob>(
    buildApiUrl(`/api/model-runs/jobs/${encodeURIComponent(jobId)}`),
    'Failed to fetch model run job'
  );
}

export async function clearModelRunJob(jobId: string): Promise<ModelRunJobClearResponse> {
  return requestJsonWithInit<ModelRunJobClearResponse>(
    buildApiUrl(`/api/model-runs/jobs/${encodeURIComponent(jobId)}`),
    'Failed to clear model run job',
    {
      method: 'DELETE'
    }
  );
}

export async function cancelModelRunJob(jobId: string): Promise<ModelRunJob> {
  return requestJsonWithInit<ModelRunJob>(
    buildApiUrl(`/api/model-runs/jobs/${encodeURIComponent(jobId)}/cancel`),
    'Failed to cancel model run job',
    {
      method: 'POST'
    }
  );
}

export async function fetchModelRunLogs(jobId: string, cursor: number, limit = 200): Promise<ModelRunJobLogsPayload> {
  const params = new URLSearchParams({
    cursor: String(cursor),
    limit: String(limit)
  });
  return requestJson<ModelRunJobLogsPayload>(
    `${buildApiUrl(`/api/model-runs/jobs/${encodeURIComponent(jobId)}/logs`)}?${params.toString()}`,
    'Failed to fetch model run logs'
  );
}

export async function fetchSensitivityExperiments(): Promise<SensitivityExperimentListPayload> {
  return requestJson<SensitivityExperimentListPayload>(
    buildApiUrl('/api/experiments/sensitivity'),
    'Failed to fetch sensitivity experiments'
  );
}

export async function submitSensitivityExperiment(
  payload: SensitivityExperimentCreateRequest
): Promise<SensitivityExperimentSubmitResponse> {
  return requestJsonWithInit<SensitivityExperimentSubmitResponse>(
    buildApiUrl('/api/experiments/sensitivity'),
    'Failed to submit sensitivity experiment',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    }
  );
}

export async function fetchSensitivityExperiment(experimentId: string): Promise<SensitivityExperimentDetailPayload> {
  return requestJson<SensitivityExperimentDetailPayload>(
    buildApiUrl(`/api/experiments/sensitivity/${encodeURIComponent(experimentId)}`),
    'Failed to fetch sensitivity experiment'
  );
}

export async function fetchSensitivityExperimentResults(experimentId: string): Promise<SensitivityExperimentResultsPayload> {
  return requestJson<SensitivityExperimentResultsPayload>(
    buildApiUrl(`/api/experiments/sensitivity/${encodeURIComponent(experimentId)}/results`),
    'Failed to fetch sensitivity experiment results'
  );
}

export async function fetchSensitivityExperimentCharts(experimentId: string): Promise<SensitivityExperimentChartsPayload> {
  return requestJson<SensitivityExperimentChartsPayload>(
    buildApiUrl(`/api/experiments/sensitivity/${encodeURIComponent(experimentId)}/charts`),
    'Failed to fetch sensitivity experiment charts'
  );
}

export async function fetchSensitivityExperimentLogs(
  experimentId: string,
  cursor: number,
  limit = 200
): Promise<SensitivityExperimentLogsPayload> {
  const params = new URLSearchParams({
    cursor: String(cursor),
    limit: String(limit)
  });
  return requestJson<SensitivityExperimentLogsPayload>(
    `${buildApiUrl(`/api/experiments/sensitivity/${encodeURIComponent(experimentId)}/logs`)}?${params.toString()}`,
    'Failed to fetch sensitivity experiment logs'
  );
}

export async function cancelSensitivityExperiment(experimentId: string): Promise<SensitivityExperimentDetailPayload> {
  return requestJsonWithInit<SensitivityExperimentDetailPayload>(
    buildApiUrl(`/api/experiments/sensitivity/${encodeURIComponent(experimentId)}/cancel`),
    'Failed to cancel sensitivity experiment',
    {
      method: 'POST'
    }
  );
}

export async function fetchExperimentJobs(): Promise<ExperimentJobsPayload> {
  return requestJson<ExperimentJobsPayload>(buildApiUrl('/api/experiments/jobs'), 'Failed to fetch experiment jobs');
}

export async function fetchExperimentJobLogs(
  jobRef: string,
  cursor: number,
  limit = 200
): Promise<ExperimentJobLogsPayload> {
  const params = new URLSearchParams({
    cursor: String(cursor),
    limit: String(limit)
  });
  return requestJson<ExperimentJobLogsPayload>(
    `${buildApiUrl(`/api/experiments/jobs/${encodeURIComponent(jobRef)}/logs`)}?${params.toString()}`,
    'Failed to fetch experiment logs'
  );
}

export async function cancelExperimentJob(jobRef: string): Promise<ExperimentJobCancelResponse> {
  return requestJsonWithInit<ExperimentJobCancelResponse>(
    buildApiUrl(`/api/experiments/jobs/${encodeURIComponent(jobRef)}/cancel`),
    'Failed to cancel experiment job',
    {
      method: 'POST'
    }
  );
}
