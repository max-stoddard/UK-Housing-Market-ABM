import { Link } from 'react-router-dom';
import type { ExperimentJobSummary } from '../../../shared/types';

function statusClass(status: ExperimentJobSummary['status']): string {
  switch (status) {
    case 'succeeded':
      return 'status-pill complete';
    case 'running':
      return 'status-pill partial';
    case 'queued':
    case 'canceled':
      return 'coverage-pill unsupported';
    default:
      return 'status-pill invalid';
  }
}

function formatStatus(status: ExperimentJobSummary['status']): string {
  return status.replace('_', ' ');
}

function typeLabel(type: ExperimentJobSummary['type']): string {
  return type === 'manual' ? 'Manual' : 'Sensitivity';
}

interface ExperimentQueueCardProps {
  jobs: ExperimentJobSummary[];
  isLoading: boolean;
  selectedJobRef: string;
  onSelectJobRef: (jobRef: string) => void;
  executionDisabled: boolean;
  authEnabled: boolean;
  canDownloadResults: boolean;
  downloadingJobRef: string;
  onCancelJob: (jobRef: string) => void;
  onDownloadJob: (job: ExperimentJobSummary) => void;
}

export function ExperimentQueueCard({
  jobs,
  isLoading,
  selectedJobRef,
  onSelectJobRef,
  executionDisabled,
  authEnabled,
  canDownloadResults,
  downloadingJobRef,
  onCancelJob,
  onDownloadJob
}: ExperimentQueueCardProps) {
  return (
    <article className="results-card">
      <h3>Experiment Queue</h3>
      {isLoading ? (
        <p className="loading-banner">Loading experiment jobs...</p>
      ) : jobs.length === 0 ? (
        <p className="info-banner">No experiment jobs submitted yet.</p>
      ) : (
        <ul className="job-list">
          {jobs.map((job) => (
            <li key={job.jobRef} className={`job-item ${selectedJobRef === job.jobRef ? 'focused' : ''}`}>
              <button type="button" className="run-focus-btn" onClick={() => onSelectJobRef(job.jobRef)}>
                {selectedJobRef === job.jobRef ? 'Viewing' : 'View'}
              </button>
              <strong>{job.title}</strong>
              <p>
                {typeLabel(job.type)} • {job.id}
              </p>
              {job.baseline && <p>Baseline: {job.baseline}</p>}
              <p>
                <span className={statusClass(job.status)}>{formatStatus(job.status)}</span>
              </p>
              <p>{job.createdAt}</p>

              {(job.status === 'queued' || job.status === 'running') && (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={executionDisabled}
                  onClick={() => onCancelJob(job.jobRef)}
                >
                  Cancel
                </button>
              )}

              {job.type === 'manual' && job.status === 'succeeded' && job.runId && (
                <div className="job-actions-row">
                  <Link
                    className="summary-link-inline"
                    to={`/experiments?type=manual&mode=view&baselineRunId=${encodeURIComponent(job.runId)}`}
                  >
                    View Experiment Results
                  </Link>
                  {!canDownloadResults ? (
                    authEnabled ? (
                      <Link className="summary-link-inline" to={`/login?next=${encodeURIComponent('/experiments?type=manual&mode=run')}`}>
                        Login to Download
                      </Link>
                    ) : (
                      <button type="button" className="summary-link-inline summary-button-inline" disabled>
                        Download Unavailable
                      </button>
                    )
                  ) : (
                    <button
                      type="button"
                      className="summary-link-inline summary-button-inline"
                      disabled={downloadingJobRef === job.jobRef}
                      onClick={() => onDownloadJob(job)}
                    >
                      {downloadingJobRef === job.jobRef ? 'Downloading...' : 'Download Results'}
                    </button>
                  )}
                </div>
              )}

              {job.type === 'sensitivity' && job.status === 'succeeded' && (
                <div className="job-actions-row">
                  <Link
                    className="summary-link-inline"
                    to={`/experiments?type=sensitivity&mode=view&experimentId=${encodeURIComponent(job.id)}`}
                  >
                    View Experiment Results
                  </Link>
                  {!canDownloadResults ? (
                    authEnabled ? (
                      <Link
                        className="summary-link-inline"
                        to={`/login?next=${encodeURIComponent('/experiments?type=sensitivity&mode=run')}`}
                      >
                        Login to Download
                      </Link>
                    ) : (
                      <button type="button" className="summary-link-inline summary-button-inline" disabled>
                        Download Unavailable
                      </button>
                    )
                  ) : (
                    <button
                      type="button"
                      className="summary-link-inline summary-button-inline"
                      disabled={downloadingJobRef === job.jobRef}
                      onClick={() => onDownloadJob(job)}
                    >
                      {downloadingJobRef === job.jobRef ? 'Downloading...' : 'Download Results'}
                    </button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
