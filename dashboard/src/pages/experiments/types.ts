export const EXPERIMENT_TYPES = ['manual', 'sensitivity'] as const;
export type ExperimentType = (typeof EXPERIMENT_TYPES)[number];

export const EXPERIMENT_MODES = ['run', 'view'] as const;
export type ExperimentMode = (typeof EXPERIMENT_MODES)[number];

export interface ExperimentRouteState {
  type: ExperimentType;
  mode: ExperimentMode;
  baselineRunId: string;
  comparisonRunId: string;
  experimentId: string;
  jobRef: string;
}

export const DEFAULT_EXPERIMENT_ROUTE_STATE: ExperimentRouteState = {
  type: 'sensitivity',
  mode: 'run',
  baselineRunId: '',
  comparisonRunId: '',
  experimentId: '',
  jobRef: ''
};
