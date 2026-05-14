#!/usr/bin/env node
/* global console, fetch, process, setTimeout */
// Author: Max Stoddard
const baseUrl = (process.env.DASHBOARD_CLOUD_SMOKE_BASE_URL || 'https://d2fb77ex4myvdf.cloudfront.net').replace(/\/+$/, '');
const username = process.env.DASHBOARD_SMOKE_USERNAME || '';
const password = process.env.DASHBOARD_SMOKE_PASSWORD || '';
const deleteKey = process.env.DASHBOARD_SMOKE_DELETE_KEY || '';
const runLabel = `${process.env.GITHUB_SHA?.slice(0, 7) || 'local'}-${process.env.GITHUB_RUN_ID || Date.now()}`;
const pollIntervalMs = 5_000;
const timeoutMs = 20 * 60_000;
const terminalStatuses = new Set(['succeeded', 'failed', 'canceled']);

const smokeOverrides = {
  N_STEPS: 1,
  N_SIMS: 1,
  TARGET_POPULATION: 100,
  recordTransactions: false,
  recordNBidUpFrequency: false,
  recordCoreIndicators: true,
  recordQualityBandPrice: false,
  recordHouseholdID: false,
  recordEmploymentIncome: false,
  recordRentalIncome: false,
  recordBankBalance: false,
  recordHousingWealth: false,
  recordTotalDebt: false,
  recordHousingStatus: false,
  recordConsumption: false,
  recordNHousesOwned: false,
  recordAge: false,
  recordSavingRate: false
};

function requireConfigured(value, name) {
  if (!value) {
    throw new Error(`${name} is required for cloud experiment smoke.`);
  }
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      ...(options.headers || {})
    }
  });
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    throw new Error(`${options.method || 'GET'} ${path} failed with ${response.status}: ${typeof payload === 'string' ? payload : JSON.stringify(payload)}`);
  }
  return payload;
}

async function fetchJobLogTail(jobRef, token) {
  try {
    const payload = await requestJson(`/api/experiments/jobs/${encodeURIComponent(jobRef)}/logs?limit=80`, { token });
    return (payload.lines || []).slice(-30).join('\n');
  } catch (error) {
    return `Failed to fetch logs for ${jobRef}: ${error.message}`;
  }
}

async function assertSensitivityLogs(jobRef, token) {
  const payload = await requestJson(`/api/experiments/jobs/${encodeURIComponent(jobRef)}/logs?limit=200`, { token });
  if (!payload.progress || payload.progress.percentComplete !== 100) {
    throw new Error(`Sensitivity job ${jobRef} did not expose final progress: ${JSON.stringify(payload.progress)}`);
  }
  const lines = payload.lines || [];
  if (!lines.some((line) => /Worker \d+\/\d+ (started|finished) point/.test(line))) {
    throw new Error(`Sensitivity job ${jobRef} did not expose summarized worker logs.\n${lines.slice(-30).join('\n')}`);
  }
  if (lines.some((line) => line.includes('Simulation: 1, time:'))) {
    throw new Error(`Sensitivity job ${jobRef} exposed raw JVM progress spam.\n${lines.slice(-30).join('\n')}`);
  }
}

async function pollJob(jobRef, token) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const payload = await requestJson('/api/experiments/jobs', { token });
    const job = (payload.jobs || []).find((candidate) => candidate.jobRef === jobRef);
    if (!job) {
      throw new Error(`Cloud smoke job ${jobRef} was not found in unified experiment jobs.`);
    }
    if (terminalStatuses.has(job.status)) {
      if (job.status !== 'succeeded') {
        const logs = await fetchJobLogTail(jobRef, token);
        throw new Error(`Cloud smoke job ${jobRef} ended with ${job.status}.\n${logs}`);
      }
      return job;
    }
    await new Promise((resolve) => {
      setTimeout(resolve, pollIntervalMs);
    });
  }
  const logs = await fetchJobLogTail(jobRef, token);
  throw new Error(`Cloud smoke job ${jobRef} timed out after ${timeoutMs}ms.\n${logs}`);
}

async function deleteJob(jobRef, token) {
  await requestJson(`/api/experiments/jobs/${encodeURIComponent(jobRef)}`, {
    method: 'DELETE',
    token,
    headers: {
      'X-Dashboard-Delete-Key': deleteKey
    }
  });
}

async function assertJobDeleted(jobRef, token) {
  const payload = await requestJson('/api/experiments/jobs', { token });
  if ((payload.jobs || []).some((candidate) => candidate.jobRef === jobRef)) {
    throw new Error(`Cloud smoke job ${jobRef} was still listed after deletion.`);
  }
}

function assertRunnerAvailable(runtimeDeps) {
  const remote = runtimeDeps.remoteExecution;
  if (!remote?.configured) {
    throw new Error('Cloud smoke requires DASHBOARD_EXECUTION_BACKEND=aws_ssm; remote execution is not configured.');
  }
  if (!remote.available || remote.runnerState !== 'running' || remote.ssmPingStatus !== 'Online') {
    throw new Error(
      `Cloud smoke requires the EC2 runner to be running and SSM Online; CI will not start EC2. ` +
        `runnerState=${remote.runnerState ?? 'unknown'} ssmPingStatus=${remote.ssmPingStatus ?? 'unknown'} reason=${remote.reason ?? 'none'}`
    );
  }
  if (!runtimeDeps.modelRunsEnabled) {
    throw new Error(`Cloud smoke requires model runs enabled: ${runtimeDeps.modelRunsDisabledReason ?? 'disabled'}`);
  }
}

async function main() {
  requireConfigured(username, 'DASHBOARD_SMOKE_USERNAME');
  requireConfigured(password, 'DASHBOARD_SMOKE_PASSWORD');
  const runtimeDeps = await requestJson('/api/runtime-deps');
  assertRunnerAvailable(runtimeDeps);

  const login = await requestJson('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  });
  if (!login?.token || !login.canWrite) {
    throw new Error('Cloud smoke login did not return write access.');
  }
  const token = login.token;

  const manual = await requestJson('/api/model-runs', {
    method: 'POST',
    token,
    body: JSON.stringify({
      baseline: 'v0o2',
      basePolicy: '2011',
      title: `ci cloud smoke manual v0o2 ${runLabel}`,
      overrides: smokeOverrides,
      confirmWarnings: true
    })
  });
  if (!manual.accepted || !manual.job?.jobId) {
    throw new Error(`Cloud manual smoke was rejected: ${JSON.stringify(manual)}`);
  }
  const manualJobRef = `manual:${manual.job.jobId}`;
  await pollJob(manualJobRef, token);

  const sensitivity = await requestJson('/api/experiments/sensitivity', {
    method: 'POST',
    token,
    body: JSON.stringify({
      baseline: 'v0o2',
      basePolicy: '2011',
      title: `ci cloud smoke sensitivity v0o2 ${runLabel}`,
      policyPackageId: 'owner_occupier_lti_soft_max',
      min: 5,
      max: 6,
      sampleCount: 2,
      overrides: smokeOverrides,
      maxWorkers: 2,
      confirmWarnings: true
    })
  });
  if (!sensitivity.accepted || !sensitivity.experiment?.experimentId) {
    throw new Error(`Cloud sensitivity smoke was rejected: ${JSON.stringify(sensitivity)}`);
  }
  const sensitivityJobRef = `sensitivity:${sensitivity.experiment.experimentId}`;
  await pollJob(sensitivityJobRef, token);
  await assertSensitivityLogs(sensitivityJobRef, token);
  if (deleteKey) {
    await deleteJob(manualJobRef, token);
    await assertJobDeleted(manualJobRef, token);
    await deleteJob(sensitivityJobRef, token);
    await assertJobDeleted(sensitivityJobRef, token);
  } else {
    console.warn('DASHBOARD_SMOKE_DELETE_KEY is not configured; leaving cloud smoke jobs for manual cleanup.');
  }

  console.log(`Cloud experiment smoke passed against ${baseUrl} with v0o2.`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
