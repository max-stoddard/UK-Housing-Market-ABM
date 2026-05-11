import { Link } from 'react-router-dom';
import { buildExperimentsPath } from '../routeState';
import { DEFAULT_EXPERIMENT_ROUTE_STATE, type ExperimentType } from '../types';
import { experimentTypeRegistry } from '../registry';
import { ExperimentLogCard } from '../../run-experiments/ExperimentLogCard';
import { ExperimentQueueCard } from '../../run-experiments/ExperimentQueueCard';
import { useExperimentRunController } from './useExperimentRunController';

interface ExperimentRunModeProps {
  activeType: ExperimentType;
  canWrite: boolean;
  authEnabled: boolean;
  selectedJobRef: string;
  onSelectedJobRefChange: (jobRef: string) => void;
  onOpenManualResults: (runId: string) => void;
  onOpenSensitivityResults: (experimentId: string) => void;
}

export function ExperimentRunMode({
  activeType,
  canWrite,
  authEnabled,
  selectedJobRef,
  onSelectedJobRefChange,
  onOpenManualResults,
  onOpenSensitivityResults
}: ExperimentRunModeProps) {
  const controller = useExperimentRunController({
    selectedJobRef,
    onSelectedJobRefChange,
    onOpenManualResults,
    onOpenSensitivityResults
  });

  const runActionsDisabled = controller.executionDisabled || !canWrite;
  const RunSetupComponent = experimentTypeRegistry[activeType].RunSetupComponent;

  return (
    <section className="run-exp-layout">
      {controller.pageError && <p className="error-banner">{controller.pageError}</p>}
      {controller.logError && <p className="error-banner">{controller.logError}</p>}

      {controller.pendingRunId && (
        <p className="waiting-banner">
          Run completed. Redirecting to results...{' '}
          <Link
            to={buildExperimentsPath({
              ...DEFAULT_EXPERIMENT_ROUTE_STATE,
              mode: 'view',
              type: 'manual',
              baselineRunId: controller.pendingRunId
            })}
          >
            View Experiment Results
          </Link>
        </p>
      )}

      {controller.pendingSensitivityExperimentId && (
        <p className="waiting-banner">
          Sensitivity experiment completed. Redirecting to results...{' '}
          <Link
            to={buildExperimentsPath({
              ...DEFAULT_EXPERIMENT_ROUTE_STATE,
              mode: 'view',
              type: 'sensitivity',
              experimentId: controller.pendingSensitivityExperimentId
            })}
          >
            View Experiment Results
          </Link>
        </p>
      )}

      {controller.executionDisabled && (
        <p className="info-banner">
          {controller.executionDisabledReason ||
            'Model execution is currently unavailable because model runs are disabled or Java/Maven are missing in this API runtime.'}
        </p>
      )}

      {!canWrite && authEnabled && (
        <p className="info-banner">
          Write access is required to run or cancel experiments.{' '}
          <Link
            className="summary-link-inline"
            to={`/login?next=${encodeURIComponent(
              buildExperimentsPath({
                ...DEFAULT_EXPERIMENT_ROUTE_STATE,
                mode: 'run',
                type: activeType
              })
            )}`}
          >
            Login for run access
          </Link>
        </p>
      )}

      <div className="run-exp-grid">
        <RunSetupComponent controller={controller} runActionsDisabled={runActionsDisabled} />

        <ExperimentQueueCard
          jobs={controller.jobs}
          isLoading={controller.isLoadingJobs}
          selectedJobRef={selectedJobRef}
          onSelectJobRef={onSelectedJobRefChange}
          executionDisabled={runActionsDisabled}
          onCancelJob={(jobRef) => {
            void controller.onCancelJob(jobRef);
          }}
        />

        <ExperimentLogCard selectedJob={controller.selectedJob} lines={controller.logLines} />
      </div>
    </section>
  );
}
