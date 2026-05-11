import type {
  BasePolicyId,
  BasePolicyOption,
  ModelRunParameterDefinition,
  ModelRunSnapshotOption,
  ModelRunWarning,
  SensitivityPolicyPackageDefinition
} from '../../../shared/types';
import {
  formatExperimentModelOption,
  orderExperimentModelOptions
} from '../../lib/experimentVersionOptions';
import {
  GeneralModelControl,
  isRecordSetting,
  RecordSettingsControl
} from './GeneralModelControl';
import { InfoLabel } from './InfoLabel';
import { SETTING_HELP } from './settingHelp';

interface SensitivitySetupCardProps {
  executionDisabled: boolean;
  isLoadingOptions: boolean;
  selectedBaseline: string;
  onBaselineChange: (baseline: string) => void;
  snapshots: ModelRunSnapshotOption[];
  basePolicies: BasePolicyOption[];
  basePolicy: BasePolicyId;
  onBasePolicyChange: (basePolicy: BasePolicyId) => void;
  policyPackages: SensitivityPolicyPackageDefinition[];
  policyPackageId: string;
  onPolicyPackageChange: (value: string) => void;
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
  selectedPackage: SensitivityPolicyPackageDefinition | null;
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
  basePolicies,
  basePolicy,
  onBasePolicyChange,
  policyPackages,
  policyPackageId,
  onPolicyPackageChange,
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
  selectedPackage,
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
  const selectedBasePolicy = basePolicies.find((policy) => policy.id === basePolicy) ?? null;
  const recordParameters = parameters.filter((parameter) => parameter.group === 'General model control' && isRecordSetting(parameter));
  const sampleValues = buildSensitivitySampleValues(selectedPackage, selectedBasePolicy, minValue, maxValue, sampleCount);
  const basePolicyValues = selectedPackage && selectedBasePolicy ? formatPackageBaseValues(selectedPackage, selectedBasePolicy) : null;
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
              <InfoLabel label="Sensitivity policy package" info={SETTING_HELP.sensitivityPolicyPackage} />
              <select
                value={policyPackageId}
                disabled={executionDisabled}
                onChange={(event) => onPolicyPackageChange(event.target.value)}
              >
                {policyPackages.map((policyPackage) => (
                  <option key={policyPackage.id} value={policyPackage.id}>
                    {policyPackage.title}
                  </option>
                ))}
              </select>
            </label>

            <label className="sensitivity-title-field">
              <InfoLabel label="Optional experiment title" info={SETTING_HELP.optionalExperimentTitle} />
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
              <InfoLabel label="Calibration Parameter Version" info={SETTING_HELP.calibrationParameterVersion} />
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

            <label className="sensitivity-base-policy-field">
              <InfoLabel label="Base policy" info={SETTING_HELP.basePolicy} />
              <select
                value={basePolicy}
                disabled={executionDisabled}
                onChange={(event) => onBasePolicyChange(event.target.value as BasePolicyId)}
              >
                {basePolicies.map((policy) => (
                  <option key={policy.id} value={policy.id}>
                    {policy.title}
                  </option>
                ))}
              </select>
            </label>

            <label className="sensitivity-min-field">
              <InfoLabel label="Min value" info={SETTING_HELP.minValue} />
              <input
                type="number"
                step={selectedPackage?.type === 'integer' ? 1 : 'any'}
                value={minValue}
                disabled={executionDisabled}
                onChange={(event) => onMinValueChange(event.target.value)}
              />
            </label>

            <label className="sensitivity-max-field">
              <InfoLabel label="Max value" info={SETTING_HELP.maxValue} />
              <input
                type="number"
                step={selectedPackage?.type === 'integer' ? 1 : 'any'}
                value={maxValue}
                disabled={executionDisabled}
                onChange={(event) => onMaxValueChange(event.target.value)}
              />
            </label>

            <label className="sensitivity-sample-field">
              <InfoLabel label="Sample count" info={SETTING_HELP.sampleCount} />
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

          <section className="policy-summary-panel sensitivity-policy-summary" aria-label="Sensitivity policy summaries">
            {selectedBasePolicy ? (
              <div className="policy-summary-item">
                <span>Base policy</span>
                <h4>{selectedBasePolicy.title}</h4>
                <p>{selectedBasePolicy.summary}</p>
              </div>
            ) : null}
            {selectedPackage ? (
              <div className="policy-summary-item">
                <span>Sensitivity package</span>
                <h4>{selectedPackage.title}</h4>
                <p>{selectedPackage.description}</p>
              </div>
            ) : null}
          </section>

          <div className="run-param-groups">
            <GeneralModelControl
              mode="sensitivity"
              parameters={parameters}
              formValues={formValues}
              executionDisabled={executionDisabled}
              onFormValueChange={onFormValueChange}
              maxWorkers={maxWorkers}
              onMaxWorkersChange={onMaxWorkersChange}
              maxWorkersHint={SETTING_HELP.maxWorkers}
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
                  <dt>Package varied</dt>
                  <dd>{selectedPackage ? selectedPackage.title : 'No package selected'}</dd>
                </div>
                <div>
                  <dt>Base policy</dt>
                  <dd>{selectedBasePolicy ? selectedBasePolicy.title : 'Not set'}</dd>
                </div>
                <div>
                  <dt>Base policy values</dt>
                  <dd>{basePolicyValues ?? 'Not set'}</dd>
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
  policyPackage: SensitivityPolicyPackageDefinition | null,
  basePolicy: BasePolicyOption | null,
  minRaw: string,
  maxRaw: string,
  sampleCountRaw: string
): string[] {
  if (!policyPackage || !basePolicy) {
    return [];
  }

  const min = Number.parseFloat(minRaw);
  const max = Number.parseFloat(maxRaw);
  const baseValues = getPackageBaseValues(policyPackage, basePolicy);
  const baseline = getCommonValue(baseValues);
  const sampleCount = Number.parseFloat(sampleCountRaw);
  if (
    !Number.isFinite(min) ||
    !Number.isFinite(max) ||
    !Number.isFinite(sampleCount) ||
    !Number.isInteger(sampleCount) ||
    sampleCount < 2 ||
    !(min < max)
  ) {
    return [];
  }

  const normalize = (value: number) => {
    const rounded = policyPackage.type === 'integer' ? Math.round(value) : value;
    return Object.is(rounded, -0) ? 0 : rounded;
  };
  const values = new Set<number>();
  for (let index = 0; index < sampleCount; index += 1) {
    const value = index === sampleCount - 1 ? max : min + ((max - min) * index) / (sampleCount - 1);
    values.add(normalize(value));
  }
  if (baseline !== null && baseline >= min && baseline <= max) {
    values.add(normalize(baseline));
  }

  const formattedValues = [...values]
    .sort((left, right) => left - right)
    .map((value) => formatPolicyValue(value, policyPackage.type));
  const usesDistinctBaseValues = baseline === null && baseValues.every((value) => value >= min && value <= max);
  return usesDistinctBaseValues ? [`base policy values (${formatPackageBaseValues(policyPackage, basePolicy)})`, ...formattedValues] : formattedValues;
}

function getPackageBaseValues(policyPackage: SensitivityPolicyPackageDefinition, basePolicy: BasePolicyOption): number[] {
  return policyPackage.parameterKeys
    .map((parameterKey) => Number(basePolicy.values[parameterKey]))
    .filter((value) => Number.isFinite(value));
}

function getCommonValue(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  const [firstValue] = values;
  return values.every((value) => value === firstValue) ? firstValue : null;
}

function formatPackageBaseValues(policyPackage: SensitivityPolicyPackageDefinition, basePolicy: BasePolicyOption): string {
  const values = getPackageBaseValues(policyPackage, basePolicy);
  if (values.length === 0) {
    return 'Not set';
  }
  const commonValue = getCommonValue(values);
  if (commonValue !== null) {
    return formatPolicyValue(commonValue, policyPackage.type);
  }
  return values.map((value) => formatPolicyValue(value, policyPackage.type)).join(', ');
}

function formatPolicyValue(value: number, type: SensitivityPolicyPackageDefinition['type']): string {
  const normalized = type === 'integer' ? Math.round(value) : value;
  return Number.isInteger(normalized) ? String(normalized) : String(Number(normalized.toFixed(6)));
}
