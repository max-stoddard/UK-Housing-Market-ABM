import { Link } from 'react-router-dom';
import type { ModelRunParameterDefinition, ModelRunSnapshotOption, ModelRunWarning } from '../../../shared/types';
import {
  formatExperimentModelOption,
  orderExperimentModelOptions
} from '../../lib/experimentVersionOptions';
import { GeneralModelControl } from './GeneralModelControl';

type FormValue = string | boolean;

interface ManualRunSetupCardProps {
  executionDisabled: boolean;
  isLoadingOptions: boolean;
  selectedBaseline: string;
  onBaselineChange: (baseline: string) => void;
  snapshots: ModelRunSnapshotOption[];
  title: string;
  onTitleChange: (value: string) => void;
  parameters: ModelRunParameterDefinition[];
  policyParameters: ModelRunParameterDefinition[];
  formValues: Record<string, FormValue>;
  onFormValueChange: (parameter: ModelRunParameterDefinition, value: FormValue) => void;
  warnings: ModelRunWarning[];
  isSubmitting: boolean;
  manualSubmissionLockedBySensitivity: boolean;
  lockMessage: string | null;
  onSubmit: (confirmWarnings: boolean) => void;
}

export function ManualRunSetupCard({
  executionDisabled,
  isLoadingOptions,
  selectedBaseline,
  onBaselineChange,
  snapshots,
  title,
  onTitleChange,
  parameters,
  policyParameters,
  formValues,
  onFormValueChange,
  warnings,
  isSubmitting,
  manualSubmissionLockedBySensitivity,
  lockMessage,
  onSubmit
}: ManualRunSetupCardProps) {
  const orderedSnapshots = orderExperimentModelOptions(snapshots);

  return (
    <article className="results-card">
      <h3>Manual Parameters</h3>
      <p>Choose a calibration parameter version, set USER SET parameters, then queue a model run.</p>
      {manualSubmissionLockedBySensitivity && lockMessage && <p className="info-banner">{lockMessage}</p>}

      {isLoadingOptions ? (
        <p className="loading-banner">Loading run options...</p>
      ) : (
        <>
          <div className="run-form-head">
            <label>
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
              <Link className="summary-link-inline" to={`/compare?mode=single&version=${encodeURIComponent(selectedBaseline)}`}>
                View in Calibration Versions
              </Link>
            </label>

            <label>
              Optional run title
              <input
                type="text"
                value={title}
                disabled={executionDisabled}
                onChange={(event) => onTitleChange(event.target.value)}
                maxLength={120}
                placeholder="Policy scenario label"
              />
              <small>Output folder uses: &lt;title&gt; &lt;calibration-version&gt;.</small>
            </label>
          </div>

          {warnings.length > 0 && (
            <div className="run-warning-card">
              <h4>Warnings detected</h4>
              <p>Confirm to submit anyway.</p>
              <ul>
                {warnings.map((warning) => (
                  <li key={`${warning.code}-${warning.message}`}>{warning.message}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="run-param-groups">
            <GeneralModelControl
              mode="manual"
              parameters={parameters}
              formValues={formValues}
              executionDisabled={executionDisabled}
              onFormValueChange={onFormValueChange}
            />

            {policyParameters.length > 0 && (
              <section className="run-param-group">
                <h4>Central Bank policy</h4>
                <div className="run-param-grid">
                  {policyParameters.map((parameter) => (
                    <label key={parameter.key} className="run-param-item">
                      <span>{parameter.title}</span>
                      <small>{parameter.key}</small>
                      <input
                        type="number"
                        step={parameter.type === 'integer' ? 1 : 'any'}
                        value={String(formValues[parameter.key] ?? '')}
                        disabled={executionDisabled}
                        onChange={(event) => onFormValueChange(parameter, event.target.value)}
                      />
                      <small>{parameter.description}</small>
                    </label>
                  ))}
                </div>
              </section>
            )}
          </div>

          <div className="run-form-actions">
            <button
              type="button"
              className="primary-button"
              disabled={isSubmitting || executionDisabled || manualSubmissionLockedBySensitivity}
              onClick={() => onSubmit(false)}
            >
              {isSubmitting ? 'Submitting...' : 'Queue Run'}
            </button>
            {warnings.length > 0 && (
              <button
                type="button"
                className="secondary-button"
                disabled={isSubmitting || executionDisabled || manualSubmissionLockedBySensitivity}
                onClick={() => onSubmit(true)}
              >
                Confirm and Queue
              </button>
            )}
          </div>
        </>
      )}
    </article>
  );
}
