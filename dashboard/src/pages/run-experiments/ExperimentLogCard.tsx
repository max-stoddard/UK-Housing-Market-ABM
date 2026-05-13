import type { ExperimentJobSummary, ExperimentProgressSnapshot } from '../../../shared/types';

interface ExperimentLogCardProps {
  selectedJob: ExperimentJobSummary | null;
  lines: string[];
  progress?: ExperimentProgressSnapshot | null;
}

function formatNumber(value: number, digits = 1): string {
  return Number.isFinite(value) ? value.toFixed(digits) : '0.0';
}

function formatRate(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}/min` : 'pending';
}

function formatDuration(seconds: number | null | undefined): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) {
    return 'pending';
  }
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${remainingSeconds}s`;
}

function formatFinishTime(value: string | null | undefined): string {
  if (!value) {
    return 'pending';
  }
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return 'pending';
  }
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function ProgressPanel({ progress }: { progress: ExperimentProgressSnapshot }) {
  const percent = Math.max(0, Math.min(100, progress.percentComplete));
  return (
    <section className="job-progress-panel" aria-label="Experiment run progress">
      <div className="job-progress-head">
        <strong>{formatNumber(percent)}%</strong>
        <span>{progress.status}</span>
      </div>
      <div className="job-progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <span style={{ width: `${percent}%` }} />
      </div>
      <dl className="job-progress-stats">
        <div>
          <dt>Runs</dt>
          <dd>
            {progress.completedRuns}/{progress.totalRuns}
          </dd>
        </div>
        <div>
          <dt>Progress</dt>
          <dd>
            {formatNumber(progress.completedRunEquivalents)}/{progress.totalRuns}
          </dd>
        </div>
        <div>
          <dt>Workers</dt>
          <dd>
            {progress.activeWorkers}/{progress.totalWorkers}
          </dd>
        </div>
        <div>
          <dt>Throughput</dt>
          <dd>{formatRate(progress.throughputRunsPerMinute)}</dd>
        </div>
        <div>
          <dt>ETA</dt>
          <dd>{formatDuration(progress.etaSeconds)}</dd>
        </div>
        <div>
          <dt>Finish</dt>
          <dd>{formatFinishTime(progress.estimatedFinishAt)}</dd>
        </div>
        <div>
          <dt>Elapsed</dt>
          <dd>{formatDuration(progress.elapsedSeconds)}</dd>
        </div>
      </dl>
    </section>
  );
}

export function ExperimentLogCard({ selectedJob, lines, progress }: ExperimentLogCardProps) {
  return (
    <article className="results-card">
      <h3>Live Logs {selectedJob ? `(${selectedJob.title})` : ''}</h3>
      {selectedJob && progress && <ProgressPanel progress={progress} />}
      {selectedJob ? (
        <pre className="job-log-view">{lines.length === 0 ? 'No logs yet.' : lines.join('\n')}</pre>
      ) : (
        <p className="info-banner">Select a queue item to view logs.</p>
      )}
    </article>
  );
}
