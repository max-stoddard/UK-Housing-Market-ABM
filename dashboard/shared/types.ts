export type VersionId = string;

export type ParameterGroup =
  | 'Household Demographics & Wealth'
  | 'Government & Tax'
  | 'Housing & Rental Market'
  | 'Purchase & Mortgage'
  | 'Bank & Credit Policy'
  | 'BTL & Investor Behavior';

export type ParameterFormat =
  | 'scalar'
  | 'scalar_pair'
  | 'binned_distribution'
  | 'joint_distribution'
  | 'lognormal_pair'
  | 'power_law_pair'
  | 'gaussian_pair'
  | 'hpa_expectation_line'
  | 'buy_quad';

export interface ParameterCardMeta {
  id: string;
  title: string;
  group: ParameterGroup;
  format: ParameterFormat;
  configKeys: string[];
  dataFileConfigKeys?: string[];
  explanation: string;
}

export interface DataSourceInfo {
  configPathLeft: string;
  configPathRight: string;
  configKeys: string[];
  dataFilesLeft: string[];
  dataFilesRight: string[];
  datasetsLeft: DatasetAttribution[];
  datasetsRight: DatasetAttribution[];
}

export type ValidationStatus = 'complete' | 'in_progress';

export interface MethodVariationNote {
  configParameters: string[];
  improvementSummary: string;
  whyChanged: string;
  methodChosen?: string;
  decisionLogic?: string;
}

export interface ParameterChange {
  configParameter: string;
  datasetSource: string | null;
}

export interface DatasetAttribution {
  tag: string;
  fullName: string;
  year: string;
  edition?: string;
  evidence?: string;
}

export interface VersionChangeOrigin {
  versionId: string;
  description: string;
  updatedDataSources: string[];
  calibrationFiles: string[];
  configParameters: string[];
  parameterChanges: ParameterChange[];
  validationStatus: ValidationStatus;
  methodVariations: MethodVariationNote[];
}

export interface DeltaStat {
  absolute: number;
  percent: number | null;
}

export interface ScalarDatum {
  key: string;
  left: number;
  right: number;
  delta: DeltaStat;
}

export interface BinnedDatum {
  label: string;
  lower: number;
  upper: number;
  left: number;
  right: number;
  delta: number;
}

export type AxisScaleType = 'linear' | 'log';

export interface AxisMeta {
  edges: number[];
  labels: string[];
  scaleType: AxisScaleType;
}

export interface JointCell {
  xIndex: number;
  yIndex: number;
  value: number;
}

export interface JointPayload {
  xAxis: AxisMeta;
  yAxis: AxisMeta;
  left: JointCell[];
  right: JointCell[];
  delta: JointCell[];
}

export interface CurvePoint {
  x: number;
  y: number;
}

export type VisualPayload =
  | { type: 'scalar'; values: ScalarDatum[] }
  | { type: 'binned_distribution'; bins: BinnedDatum[] }
  | { type: 'joint_distribution'; matrix: JointPayload }
  | {
      type: 'lognormal_pair';
      parameters: ScalarDatum[];
      curveLeft: CurvePoint[];
      curveRight: CurvePoint[];
      median: {
        left: number;
        right: number;
        delta: DeltaStat;
      };
      domain: { min: number; max: number };
    }
  | {
      type: 'power_law_pair';
      parameters: ScalarDatum[];
      curveLeft: CurvePoint[];
      curveRight: CurvePoint[];
      domain: { min: number; max: number };
    }
  | {
      type: 'gaussian_pair';
      parameters: ScalarDatum[];
      logCurveLeft: CurvePoint[];
      logCurveRight: CurvePoint[];
      percentCurveLeft: CurvePoint[];
      percentCurveRight: CurvePoint[];
      logDomain: { min: number; max: number };
      percentDomain: { min: number; max: number };
      percentCap: number;
      percentCapMassLeft: number;
      percentCapMassRight: number;
      logMedian: {
        left: number;
        right: number;
        delta: DeltaStat;
      };
      percentMedian: {
        left: number;
        right: number;
        delta: DeltaStat;
      };
    }
  | {
      type: 'hpa_expectation_line';
      parameters: ScalarDatum[];
      curveLeft: CurvePoint[];
      curveRight: CurvePoint[];
      domain: { min: number; max: number };
      dt: number;
    }
  | {
      type: 'buy_quad';
      parameters: ScalarDatum[];
      budgetLeft: CurvePoint[];
      budgetRight: CurvePoint[];
      multiplierLeft: CurvePoint[];
      multiplierRight: CurvePoint[];
      medianMultiplier: {
        left: number;
        right: number;
        delta: DeltaStat;
      };
      expectedMultiplier: {
        left: number;
        right: number;
        delta: DeltaStat;
      };
      domain: { min: number; max: number };
    };

export interface CompareResult {
  id: string;
  title: string;
  group: ParameterGroup;
  format: ParameterFormat;
  unchanged: boolean;
  sourceInfo: DataSourceInfo;
  explanation: string;
  leftVersion: VersionId;
  rightVersion: VersionId;
  changeOriginsInRange: VersionChangeOrigin[];
  visualPayload: VisualPayload;
}

export interface CompareResponse {
  left: VersionId;
  right: VersionId;
  items: CompareResult[];
}

export interface HomePreviewItem {
  id: string;
  title: string;
  rightVersion: VersionId;
  visualPayload: VisualPayload;
}

export interface HomePreviewPayload {
  version: VersionId;
  items: HomePreviewItem[];
}

export type ValidationMetricStatus = 'pass' | 'warn' | 'fail' | 'unsupported';
export type ValidationMetricRequirement = 'required' | 'diagnostic';

export interface ValidationTargetBand {
  lower: number;
  upper: number;
}

export interface ValidationStatusCounts {
  pass: number;
  warn: number;
  fail: number;
  unsupported: number;
}

export interface ValidationFamilySummary {
  familyId: string;
  label: string;
  loss: number;
  statusCounts: ValidationStatusCounts;
}

export interface ValidationMetricSummary {
  metricId: string;
  familyId: string;
  label: string;
  status: ValidationMetricStatus;
  requirement: ValidationMetricRequirement;
  units: string;
  sourceLabel: string;
  targetBand: ValidationTargetBand | null;
  seedMean: number;
  p25: number;
  p75: number;
  insideRate: number | null;
  normalizedDistance: number | null;
  normalizedIqr: number | null;
  metricLoss: number | null;
}

export interface ValidationVersionSummary {
  schemaVersion: number;
  version: string;
  generatedAt: string;
  seeds: number[];
  window: {
    startIndex: number;
    endIndex: number;
  };
  overallCompositeLoss: number;
  familySummaries: ValidationFamilySummary[];
  metrics: ValidationMetricSummary[];
}

export interface ValidationCompositeTrendPoint {
  version: string;
  overallCompositeLoss: number;
}

export interface ValidationCompositeTrendPayload {
  points: ValidationCompositeTrendPoint[];
}

export interface ValidationOverviewPayload {
  availableVersions: string[];
  selectedVersion: string;
  trend: ValidationCompositeTrendPayload;
  selectedSummary: ValidationVersionSummary;
}

export type ResultsRunStatus = 'complete' | 'partial' | 'invalid';

export type ResultsFileType =
  | 'output'
  | 'core_indicator'
  | 'transaction'
  | 'micro_snapshot'
  | 'config'
  | 'other';

export type ResultsCoverageStatus = 'supported' | 'empty' | 'unsupported' | 'error';

export type ResultsSeriesSource = 'core_indicator' | 'output';

export interface ResultsIndicatorMeta {
  id: string;
  title: string;
  units: string;
  description: string;
  source: ResultsSeriesSource;
}

export type KpiMetricKey = 'mean' | 'cv' | 'annualisedTrend' | 'range';

export interface KpiMetricValues {
  mean: number | null;
  cv: number | null;
  annualisedTrend: number | null;
  range: number | null;
}

export interface KpiMetricSummary {
  indicatorId: string;
  title: string;
  units: string;
  windowType: 'tail_120';
  mean: number | null;
  cv: number | null;
  annualisedTrend: number | null;
  range: number | null;
}

export interface ResultsCoverageSummary {
  requiredCount: number;
  supportedCount: number;
  emptyCount: number;
  errorCount: number;
}

export interface ResultsRunSummary {
  runId: string;
  path: string;
  modifiedAt: string;
  createdAt: string;
  sizeBytes: number;
  fileCount: number;
  status: ResultsRunStatus;
  configAvailable: boolean;
  parseCoverage: ResultsCoverageSummary;
}

export interface ResultsIndicatorAvailability extends ResultsIndicatorMeta {
  available: boolean;
  coverageStatus: ResultsCoverageStatus;
  note?: string;
}

export interface ResultsRunDetail {
  runId: string;
  path: string;
  modifiedAt: string;
  createdAt: string;
  sizeBytes: number;
  fileCount: number;
  status: ResultsRunStatus;
  configAvailable: boolean;
  parseCoverage: ResultsCoverageSummary;
  indicators: ResultsIndicatorAvailability[];
  kpiSummary: KpiMetricSummary[];
}

export interface ResultsFileManifestEntry {
  fileName: string;
  filePath: string;
  sizeBytes: number;
  modifiedAt: string;
  fileType: ResultsFileType;
  coverageStatus: ResultsCoverageStatus;
  note?: string;
}

export interface ResultsSeriesPoint {
  modelTime: number;
  value: number | null;
}

export interface ResultsSeriesPayload {
  runId: string;
  indicator: ResultsIndicatorMeta;
  smoothWindow: 0 | 3 | 12;
  points: ResultsSeriesPoint[];
}

export interface ResultsCompareSeries {
  runId: string;
  points: ResultsSeriesPoint[];
}

export interface ResultsCompareIndicator {
  indicator: ResultsIndicatorMeta;
  seriesByRun: ResultsCompareSeries[];
}

export interface ResultsComparePayload {
  runIds: string[];
  indicatorIds: string[];
  smoothWindow: 0 | 3 | 12;
  window: 'post200' | 'tail120' | 'full';
  indicators: ResultsCompareIndicator[];
}

export interface ResultsStorageSummary {
  usedBytes: number;
  capBytes: number;
}

export interface AuthStatusPayload {
  authEnabled: boolean;
  canWrite: boolean;
  authMisconfigured: boolean;
  modelRunsEnabled: boolean;
  modelRunsConfigured: boolean;
  modelRunsDisabledReason: string | null;
}

export interface AuthLoginRequest {
  username: string;
  password: string;
}

export interface AuthLoginResponse {
  ok: boolean;
  token?: string;
  canWrite: boolean;
}

export interface AuthLogoutResponse {
  ok: boolean;
}

export type ModelRunSnapshotStatus = 'stable' | 'in_progress';
export type ModelRunParameterType = 'integer' | 'number' | 'boolean';
export type ModelRunParameterGroup = 'General model control' | 'Central Bank policy';
export type ModelRunJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled';

export interface ModelRunSnapshotOption {
  version: string;
  status: ModelRunSnapshotStatus;
}

export interface ModelRunParameterDefinition {
  key: string;
  title: string;
  description: string;
  group: ModelRunParameterGroup;
  type: ModelRunParameterType;
  defaultValue: number | boolean;
}

export interface ModelRunWarning {
  code: string;
  message: string;
  severity: 'warning';
}

export interface ModelRunJob {
  jobId: string;
  runId: string;
  title?: string;
  baseline: string;
  status: ModelRunJobStatus;
  createdAt: string;
  startedAt?: string;
  endedAt?: string;
  outputPath: string;
  configPath: string;
  exitCode?: number | null;
  signal?: string | null;
}

export interface ModelRunOptionsPayload {
  executionEnabled: boolean;
  snapshots: ModelRunSnapshotOption[];
  defaultBaseline: string;
  requestedBaseline: string;
  parameters: ModelRunParameterDefinition[];
}

export interface ModelRunSubmitRequest {
  baseline: string;
  title?: string;
  overrides: Record<string, number | boolean>;
  confirmWarnings?: boolean;
}

export interface ModelRunSubmitResponse {
  accepted: boolean;
  warnings: ModelRunWarning[];
  job?: ModelRunJob;
}

export interface ModelRunJobsPayload {
  jobs: ModelRunJob[];
}

export interface ModelRunJobClearResponse {
  jobId: string;
  cleared: boolean;
}

export interface ModelRunJobLogsPayload {
  jobId: string;
  cursor: number;
  nextCursor: number;
  lines: string[];
  hasMore: boolean;
  done: boolean;
  truncated: boolean;
}

export interface ResultsRunDeleteResponse {
  runId: string;
  deleted: boolean;
}

export type SensitivityExperimentStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled';
export type SensitivitySampleSlot = 'min' | 'mid_lower' | 'baseline' | 'mid_upper' | 'max';

export interface SensitivitySamplePoint {
  pointId: string;
  value: number;
  label: string;
  slotLabels: SensitivitySampleSlot[];
  isBaseline: boolean;
}

export interface SensitivityExperimentParameterSelection {
  key: string;
  title: string;
  description: string;
  type: Extract<ModelRunParameterType, 'integer' | 'number'>;
  baselineValue: number;
  min: number;
  max: number;
}

export interface SensitivityExperimentCreateRequest {
  baseline: string;
  title?: string;
  parameterKey: string;
  min: number;
  max: number;
  retainFullOutput?: boolean;
  confirmWarnings?: boolean;
}

export interface SensitivityExperimentSummary {
  experimentId: string;
  title?: string;
  baseline: string;
  status: SensitivityExperimentStatus;
  createdAt: string;
  startedAt?: string;
  endedAt?: string;
  retainFullOutput: boolean;
  parameter: SensitivityExperimentParameterSelection;
}

export interface SensitivityExperimentWarningSummary {
  byPoint: Record<string, string[]>;
}

export interface SensitivityExperimentMetadata extends SensitivityExperimentSummary {
  warnings: ModelRunWarning[];
  warningSummary: SensitivityExperimentWarningSummary;
  failureReason?: string;
  canceledByUser?: boolean;
  sampledPoints: SensitivitySamplePoint[];
  collapsedSlots: Record<SensitivitySampleSlot, string>;
  runCommand: {
    mavenBin: string;
    commandTemplate: string;
  };
}

export interface SensitivityIndicatorPointMetric {
  indicatorId: string;
  title: string;
  units: string;
  kpi: KpiMetricValues;
  deltaFromBaseline: KpiMetricValues;
}

export interface SensitivityPointResult extends SensitivitySamplePoint {
  status: 'succeeded' | 'failed' | 'canceled';
  runId: string;
  outputPath: string | null;
  error?: string;
  indicatorMetrics: SensitivityIndicatorPointMetric[];
}

export interface SensitivityTornadoBar {
  indicatorId: string;
  title: string;
  units: string;
  maxAbsDeltaByKpi: KpiMetricValues;
}

export interface SensitivityDeltaTrendPoint {
  parameterValue: number;
  deltaByKpi: KpiMetricValues;
}

export interface SensitivityDeltaTrendSeries {
  indicatorId: string;
  title: string;
  units: string;
  points: SensitivityDeltaTrendPoint[];
}

export interface SensitivityExperimentResultsPayload {
  experimentId: string;
  baselinePointId: string | null;
  points: SensitivityPointResult[];
}

export interface SensitivityExperimentChartsPayload {
  experimentId: string;
  parameter: SensitivityExperimentParameterSelection;
  windowType: 'tail_120';
  tornado: SensitivityTornadoBar[];
  deltaTrend: SensitivityDeltaTrendSeries[];
}

export interface SensitivityExperimentDetailPayload {
  experiment: SensitivityExperimentMetadata;
}

export interface SensitivityExperimentListPayload {
  experiments: SensitivityExperimentSummary[];
}

export interface SensitivityExperimentSubmitResponse {
  accepted: boolean;
  warnings: ModelRunWarning[];
  warningSummary?: SensitivityExperimentWarningSummary;
  experiment?: SensitivityExperimentSummary;
}

export interface SensitivityExperimentLogsPayload {
  experimentId: string;
  cursor: number;
  nextCursor: number;
  lines: string[];
  hasMore: boolean;
  done: boolean;
  truncated: boolean;
}

export type ExperimentJobType = 'manual' | 'sensitivity';
export type ExperimentJobStatus = ModelRunJobStatus | SensitivityExperimentStatus;

export interface ExperimentJobSummary {
  jobRef: string;
  type: ExperimentJobType;
  id: string;
  title: string;
  status: ExperimentJobStatus;
  createdAt: string;
  startedAt?: string;
  endedAt?: string;
  baseline?: string;
  runId?: string;
}

export interface ExperimentExecutionLocks {
  manualSubmissionLocked: boolean;
  sensitivitySubmissionLocked: boolean;
  activeManualJobRef: string | null;
  activeSensitivityJobRef: string | null;
}

export interface ExperimentJobsPayload {
  jobs: ExperimentJobSummary[];
  locks: ExperimentExecutionLocks;
}

export interface ExperimentJobLogsPayload {
  jobRef: string;
  type: ExperimentJobType;
  cursor: number;
  nextCursor: number;
  lines: string[];
  hasMore: boolean;
  done: boolean;
  truncated: boolean;
}

export interface ExperimentJobCancelResponse {
  job: ExperimentJobSummary;
}
