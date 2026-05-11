// Author: Max Stoddard
import { CollapsibleSection } from '../../components/CollapsibleSection';
import type { ModelRunParameterDefinition } from '../../../shared/types';

type FormValue = string | boolean;
type ControlMode = 'manual' | 'sensitivity';
const HIDDEN_GENERAL_MODEL_CONTROL_KEYS = new Set(['TARGET_POPULATION', 'CUMULATIVE_WEIGHT_BEYOND_YEAR']);

interface GeneralModelControlProps {
  mode: ControlMode;
  parameters: ModelRunParameterDefinition[];
  formValues: Record<string, FormValue>;
  executionDisabled: boolean;
  onFormValueChange: (parameter: ModelRunParameterDefinition, value: FormValue) => void;
  maxWorkers?: string;
  onMaxWorkersChange?: (value: string) => void;
  maxWorkersHint?: string;
  showRecordSettings?: boolean;
}

export function isRecordSetting(parameter: ModelRunParameterDefinition): boolean {
  return parameter.key.startsWith('record') || parameter.key === 'TIME_TO_START_RECORDING_TRANSACTIONS';
}

function shouldShowParameter(parameter: ModelRunParameterDefinition, mode: ControlMode): boolean {
  if (parameter.group !== 'General model control') {
    return false;
  }

  if (HIDDEN_GENERAL_MODEL_CONTROL_KEYS.has(parameter.key)) {
    return false;
  }

  if (mode === 'sensitivity' && parameter.key === 'SEED') {
    return false;
  }

  return true;
}

function displayParameter(parameter: ModelRunParameterDefinition, mode: ControlMode): ModelRunParameterDefinition {
  if (mode === 'sensitivity' && parameter.key === 'N_SIMS') {
    return {
      ...parameter,
      title: 'Seeds per sampled point',
      description: 'Independent seed runs to execute for every sampled parameter value.'
    };
  }

  return parameter;
}

interface ParameterInputProps {
  parameter: ModelRunParameterDefinition;
  value: FormValue | undefined;
  executionDisabled: boolean;
  onChange: (parameter: ModelRunParameterDefinition, value: FormValue) => void;
}

export function ParameterInput({ parameter, value, executionDisabled, onChange }: ParameterInputProps) {
  return (
    <label className="run-param-item">
      <span>{parameter.title}</span>
      <small>{parameter.key}</small>
      {parameter.type === 'boolean' ? (
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={executionDisabled}
          onChange={(event) => onChange(parameter, event.target.checked)}
        />
      ) : (
        <input
          type="number"
          step={parameter.type === 'integer' ? 1 : 'any'}
          value={String(value ?? '')}
          disabled={executionDisabled}
          onChange={(event) => onChange(parameter, event.target.value)}
        />
      )}
      <small>{parameter.description}</small>
    </label>
  );
}

export function GeneralModelControl({
  mode,
  parameters,
  formValues,
  executionDisabled,
  onFormValueChange,
  maxWorkers,
  onMaxWorkersChange,
  maxWorkersHint,
  showRecordSettings = true
}: GeneralModelControlProps) {
  const visibleParameters = parameters
    .filter((parameter) => shouldShowParameter(parameter, mode))
    .map((parameter) => displayParameter(parameter, mode));
  const modelParameters = visibleParameters.filter((parameter) => !isRecordSetting(parameter));
  const recordParameters = visibleParameters.filter(isRecordSetting);
  const summaryCount = modelParameters.length + (showRecordSettings ? recordParameters.length : 0) + (onMaxWorkersChange ? 1 : 0);

  return (
    <CollapsibleSection
      title="General model control"
      defaultOpen
      summary={`${summaryCount} controls`}
      className="general-model-control"
    >
      <div className="run-param-grid">
        {modelParameters.map((parameter) => (
          <ParameterInput
            key={parameter.key}
            parameter={parameter}
            value={formValues[parameter.key]}
            executionDisabled={executionDisabled}
            onChange={onFormValueChange}
          />
        ))}

        {onMaxWorkersChange && (
          <label className="run-param-item">
            <span>Max workers</span>
            <small>experiment max workers</small>
            <input
              type="number"
              step={1}
              min={1}
              value={maxWorkers ?? ''}
              disabled={executionDisabled}
              onChange={(event) => onMaxWorkersChange(event.target.value)}
            />
            <small>{maxWorkersHint ?? 'Maximum independent model runs to execute in parallel.'}</small>
          </label>
        )}
      </div>

      {showRecordSettings && (
        <RecordSettingsControl
          parameters={recordParameters}
          formValues={formValues}
          executionDisabled={executionDisabled}
          onFormValueChange={onFormValueChange}
        />
      )}
    </CollapsibleSection>
  );
}

interface RecordSettingsControlProps {
  parameters: ModelRunParameterDefinition[];
  formValues: Record<string, FormValue>;
  executionDisabled: boolean;
  onFormValueChange: (parameter: ModelRunParameterDefinition, value: FormValue) => void;
}

export function RecordSettingsControl({
  parameters,
  formValues,
  executionDisabled,
  onFormValueChange
}: RecordSettingsControlProps) {
  if (parameters.length === 0) {
    return null;
  }

  return (
    <CollapsibleSection
      title="Record settings"
      defaultOpen={false}
      summary={`${parameters.length} controls`}
      className="record-settings-control"
    >
      <div className="run-param-grid">
        {parameters.map((parameter) => (
          <ParameterInput
            key={parameter.key}
            parameter={parameter}
            value={formValues[parameter.key]}
            executionDisabled={executionDisabled}
            onChange={onFormValueChange}
          />
        ))}
      </div>
    </CollapsibleSection>
  );
}
