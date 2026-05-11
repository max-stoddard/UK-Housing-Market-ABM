import type {
  ExperimentJobCancelResponse,
  ExperimentJobLogsPayload,
  ExperimentJobSummary,
  ExperimentJobsPayload,
  ModelRunJob,
  SensitivityExperimentSummary
} from '../../shared/types';
import { cancelModelRunJob, getModelRunJobLogs, listModelRunJobs } from './modelRuns';
import {
  cancelSensitivityExperiment,
  getSensitivityExperimentLogs,
  listSensitivityExperiments
} from './sensitivityRuns';
import type { RuntimePathInput } from './runtimePaths';

function toManualSummary(job: ModelRunJob): ExperimentJobSummary {
  return {
    jobRef: `manual:${job.jobId}`,
    type: 'manual',
    id: job.jobId,
    title: job.title || job.runId,
    status: job.status,
    createdAt: job.createdAt,
    startedAt: job.startedAt,
    endedAt: job.endedAt,
    baseline: job.baseline,
    runId: job.runId
  };
}

function toSensitivitySummary(experiment: SensitivityExperimentSummary): ExperimentJobSummary {
  return {
    jobRef: `sensitivity:${experiment.experimentId}`,
    type: 'sensitivity',
    id: experiment.experimentId,
    title: experiment.title || experiment.experimentId,
    status: experiment.status,
    createdAt: experiment.createdAt,
    startedAt: experiment.startedAt,
    endedAt: experiment.endedAt,
    baseline: experiment.baseline
  };
}

function parseJobRef(jobRef: string): { type: 'manual' | 'sensitivity'; id: string } {
  const trimmed = jobRef.trim();
  if (!trimmed) {
    throw new Error('jobRef is required.');
  }

  const manualMatch = /^manual:(.+)$/.exec(trimmed);
  if (manualMatch) {
    return { type: 'manual', id: manualMatch[1] };
  }

  const sensitivityMatch = /^sensitivity:(.+)$/.exec(trimmed);
  if (sensitivityMatch) {
    return { type: 'sensitivity', id: sensitivityMatch[1] };
  }

  throw new Error(`Unknown experiment jobRef: ${jobRef}`);
}

export function listExperimentJobs(pathsInput: RuntimePathInput): ExperimentJobsPayload {
  const manualJobs = listModelRunJobs().map(toManualSummary);
  const sensitivityJobs = listSensitivityExperiments(pathsInput).experiments.map(toSensitivitySummary);

  const jobs = [...manualJobs, ...sensitivityJobs].sort(
    (left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt)
  );

  const activeManual = manualJobs.find((job) => job.status === 'queued' || job.status === 'running') ?? null;
  const activeSensitivity = sensitivityJobs.find((job) => job.status === 'queued' || job.status === 'running') ?? null;

  return {
    jobs,
    locks: {
      manualSubmissionLocked: Boolean(activeSensitivity),
      sensitivitySubmissionLocked: Boolean(activeManual),
      activeManualJobRef: activeManual?.jobRef ?? null,
      activeSensitivityJobRef: activeSensitivity?.jobRef ?? null
    }
  };
}

export function getExperimentJobLogs(
  pathsInput: RuntimePathInput,
  jobRef: string,
  cursor: number | undefined,
  limit: number | undefined
): ExperimentJobLogsPayload {
  const parsed = parseJobRef(jobRef);

  if (parsed.type === 'manual') {
    const payload = getModelRunJobLogs(parsed.id, cursor, limit);
    return {
      jobRef,
      type: 'manual',
      cursor: payload.cursor,
      nextCursor: payload.nextCursor,
      lines: payload.lines,
      hasMore: payload.hasMore,
      done: payload.done,
      truncated: payload.truncated
    };
  }

  const payload = getSensitivityExperimentLogs(pathsInput, parsed.id, cursor, limit);
  return {
    jobRef,
    type: 'sensitivity',
    cursor: payload.cursor,
    nextCursor: payload.nextCursor,
    lines: payload.lines,
    hasMore: payload.hasMore,
    done: payload.done,
    truncated: payload.truncated
  };
}

export function cancelExperimentJob(pathsInput: RuntimePathInput, jobRef: string): ExperimentJobCancelResponse {
  const parsed = parseJobRef(jobRef);

  if (parsed.type === 'manual') {
    const job = cancelModelRunJob(pathsInput, parsed.id);
    return {
      job: toManualSummary(job)
    };
  }

  const detail = cancelSensitivityExperiment(pathsInput, parsed.id);
  return {
    job: toSensitivitySummary(detail.experiment)
  };
}
