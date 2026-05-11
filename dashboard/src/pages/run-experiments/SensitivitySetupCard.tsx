import type { ModelRunParameterDefinition, ModelRunSnapshotOption, ModelRunWarning } from '../../../shared/types';
import {
  formatExperimentModelOption,
  orderExperimentModelOptions
} from '../../lib/experimentVersionOptions';
import {
  GeneralModelControl,
  isRecordSetting,
  RecordSettingsControl
} from './GeneralModelControl';

type NumericParameter = ModelRunParameterDefinition & { type: 'integer' | 'number' };

interface SensitivitySetupCardProps {
  executionDisabled: boolean;
  isLoadingOptions: boolean;
  selectedBaseline: string;
  onBaselineChange: (baseline: string) => void;
  snapshots: ModelRunSnapshotOption[];
  numericParameters: NumericParameter[];
  parameterKey: string;
  onParameterKeyChange: (value: string) => void;
  minValue: string;
  maxValue: string;
  onMinValueChange: (value: string) => void;
  onMaxValueChange: (value: string) => void;
  sampleCount: string;
  onSampleCountChange: (value: string) => void;
  parameters: ModelRunParameterDefinition[];
  formValues: Record<string, string | boolean>;
  onFormValueChange: (parameter: ModelRunParameterDefinition, value: string | boolean) => void;
  maxWorkers: string;
  onMaxWorkersChange: (value: string) => void;
  title: string;
  onTitleChange: (value: string) => void;
  selectedParameter: NumericParameter | null;
  warnings: ModelRunWarning[];
  isSubmitting: boolean;
  isCanceling: boolean;
  sensitivitySubmissionLockedByManual: boolean;
  lockMessage: string | null;
  hasActiveSensitivityJob: boolean;
  onSubmit: (confirmWarnings: boolean) => void;
  onCancelActive: () => void;
}

export function SensitivitySetupCard({
  executionDisabled,
  isLoadingOptions,
  selectedBaseline,
  onBaselineChange,
  snapshots,
  numericParameters,
  parameterKey,
  onParameterKeyChange,
  minValue,
  maxValue,
  onMinValueChange,
  onMaxValueChange,
  sampleCount,
  onSampleCountChange,
  parameters,
  formValues,
  onFormValueChange,
  maxWorkers,
  onMaxWorkersChange,
  title,
  onTitleChange,
  selectedParameter,
  warnings,
  isSubmitting,
  isCanceling,
  sensitivitySubmissionLockedByManual,
  lockMessage,
  hasActiveSensitivityJob,
  onSubmit,
  onCancelActive
}: SensitivitySetupCardProps) {
  const orderedSnapshots = orderExperimentModelOptions(snapshots);
  const selectedSnapshot = orderedSnapshots.find((snapshot) => snapshot.version === selectedBaseline) ?? null;
  const recordParameters = parameters.filter((parameter) => parameter.group === 'General model control' && isRecordSetting(parameter));
  const sampleValues = buildSensitivitySampleValues(selectedParameter, minValue, maxValue, sampleCount);
  const simulationDuration = String(formValues.N_STEPS ?? '');
  const monteCarloRuns = String(formValues.N_SIMS ?? '');

  return (
    <article className="results-card">
      <h3>Sensitivity Setup</h3>
      <p>Run one-parameter-at-a-time policy sweeps with baseline comparison.</p>
      {sensitivitySubmissionLockedByManual && lockMessage && <p className="info-banner">{lockMessage}</p>}

      {isLoadingOptions ? (
        <p className="loading-banner">Loading sensitivity options...</p>
      ) : (
        <>
          <div className="run-form-head sensitivity-run-form-head">
            <label className="sensitivity-policy-field">
              Sensitivity policy parameter
              <select
                value={parameterKey}
                disabled={executionDisabled}
                onChange={(event) => onParameterKeyChange(event.target.value)}
              >
                {numericParameters.map((parameter) => (
                  <option key={parameter.key} value={parameter.key}>
                    {parameter.title} ({parameter.key})
                  </option>
                ))}
              </select>
            </label>

            <label className="sensitivity-title-field">
              Optional experiment title
              <input
                type="text"
                value={title}
                disabled={executionDisabled}
                onChange={(event) => onTitleChange(event.target.value)}
                maxLength={120}
                placeholder="Policy sensitivity label"
              />
            </label>

            <label className="sensitivity-version-field">
              Calibration Parameter Version
              <select
                value={selectedBaseline}
                disabled={executionDisabled}
                onChange={(event) => onBaselineChange(event.target.value)}
              >
                {orderedSnapshots.map((snapshot) => (
                  <option key={snapshot.version} value={snapshot.version}>
                    {formatExperimentModelOption(snapshot, orderedSnapshots)}
                  </option>
                ))}
              </select>
            </label>

            <label className="sensitivity-min-field">
              Min value
              <input
                type="number"
                step={selectedParameter?.type === 'integer' ? 1 : 'any'}
                value={minValue}
                disabled={executionDisabled}
                onChange={(event) => onMinValueChange(event.target.value)}
              />
            </label>

            <label className="sensitivity-max-field">
              Max value
              <input
                type="number"
                step={selectedParameter?.type === 'integer' ? 1 : 'any'}
                value={maxValue}
                disabled={executionDisabled}
                onChange={(event) => onMaxValueChange(event.target.value)}
              />
            </label>

            <label className="sensitivity-sample-field">
              <span className="sensitivity-field-label">
                Sample count
                <span className="sensitivity-info-trigger" tabIndex={0} aria-label="Sample count information">
                  <span aria-hidden="true" className="sensitivity-info-icon">
                    i
                  </span>
                  <span role="tooltip" className="sensitivity-info-tooltip">
                    Sampled parameter values include min and max. The baseline point is added when it is not already on the
                    uniform grid.
                  </span>
                </span>
              </span>
              <input
                type="number"
                step={1}
                min={2}
                value={sampleCount}
                disabled={executionDisabled}
                onChange={(event) => onSampleCountChange(event.target.value)}
              />
            </label>
          </div>

          <div className="run-param-groups">
            <GeneralModelControl
              mode="sensitivity"
              parameters={parameters}
              formValues={formValues}
              executionDisabled={executionDisabled}
              onFormValueChange={onFormValueChange}
              maxWorkers={maxWorkers}
              onMaxWorkersChange={onMaxWorkersChange}
              maxWorkersHint="Maximum independent point/seed model runs to execute in parallel."
              showRecordSettings={false}
            />

            <RecordSettingsControl
              parameters={recordParameters}
              formValues={formValues}
              executionDisabled={executionDisabled}
              onFormValueChange={onFormValueChange}
            />
          </div>

          {warnings.length > 0 && (
            <div className="run-warning-card">
              <h4>Warnings detected</h4>
              <p>Confirm to start anyway.</p>
              <ul>
                {warnings.map((warning) => (
                  <li key={`${warning.code}-${warning.message}`}>{warning.message}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="sensitivity-run-summary">
            <section className="run-param-group sensitivity-experiment-summary" aria-label="Sensitivity experiment summary">
              <h4>Experiment summary</h4>
              <dl>
                <div>
                  <dt>Parameter varied</dt>
                  <dd>{selectedParameter ? `${selectedParameter.title} (${selectedParameter.key})` : 'No parameter selected'}</dd>
                </div>
                <div>
                  <dt>Baseline value</dt>
                  <dd>{selectedParameter ? String(selectedParameter.defaultValue) : 'Not set'}</dd>
                </div>
                <div>
                  <dt>Points tested</dt>
                  <dd>{sampleValues.length > 0 ? sampleValues.join(', ') : 'Enter a valid min, max, and sample count.'}</dd>
                </div>
                <div>
                  <dt>Monte Carlo runs per point</dt>
                  <dd>{monteCarloRuns || 'Not set'}</dd>
                </div>
                <div>
                  <dt>Model version</dt>
                  <dd>{selectedSnapshot ? formatExperimentModelOption(selectedSnapshot, orderedSnapshots) : selectedBaseline}</dd>
                </div>
                <div>
                  <dt>Simulation duration</dt>
                  <dd>{simulationDuration ? `${simulationDuration} steps` : 'Not set'}</dd>
                </div>
                <div>
                  <dt>Workers parallelised across</dt>
                  <dd>{maxWorkers || 'Not set'}</dd>
                </div>
              </dl>
            </section>
          </div>

          <div className="run-form-actions">
            <button
              type="button"
              className="primary-button"
              disabled={isSubmitting || executionDisabled || sensitivitySubmissionLockedByManual || hasActiveSensitivityJob}
              onClick={() => onSubmit(false)}
            >
              {isSubmitting ? 'Submitting...' : 'Start Sensitivity'}
            </button>
            {warnings.length > 0 && (
              <button
                type="button"
                className="secondary-button"
                disabled={isSubmitting || executionDisabled || sensitivitySubmissionLockedByManual || hasActiveSensitivityJob}
                onClick={() => onSubmit(true)}
              >
                Confirm and Start
              </button>
            )}
            {hasActiveSensitivityJob && (
              <button
                type="button"
                className="secondary-button"
                disabled={isCanceling || executionDisabled}
                onClick={onCancelActive}
              >
                {isCanceling ? 'Canceling...' : 'Cancel Active Experiment'}
              </button>
            )}
          </div>
        </>
      )}
    </article>
  );
}

function buildSensitivitySampleValues(
  parameter: NumericParameter | null,
  minRaw: string,
  maxRaw: string,
  sampleCountRaw: string
): string[] {
  if (!parameter) {
    return [];
  }

  const min = Number.parseFloat(minRaw);
  const max = Number.parseFloat(maxRaw);
  const baseline = Number(parameter.defaultValue);
  const sampleCount = Number.parseFloat(sampleCountRaw);
  if (
    !Number.isFinite(min) ||
    !Number.isFinite(max) ||
    !Number.isFinite(baseline) ||
    !Number.isFinite(sampleCount) ||
    !Number.isInteger(sampleCount) ||
    sampleCount < 2 ||
    !(min < max)
  ) {
    return [];
  }

  const normalize = (value: number) => {
    const rounded = parameter.type === 'integer' ? Math.round(value) : value;
    return Object.is(rounded, -0) ? 0 : rounded;
  };
  const values = new Set<number>();
  for (let index = 0; index < sampleCount; index += 1) {
    const value = index === sampleCount - 1 ? max : min + ((max - min) * index) / (sampleCount - 1);
    values.add(normalize(value));
  }
  if (baseline >= min && baseline <= max) {
    values.add(normalize(baseline));
  }

  return [...values].sort((left, right) => left - right).map((value) => (Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)))));
}
