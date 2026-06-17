import type {
  KpiMetricKey,
  KpiMetricSummary,
  ResultsCompareIndicator,
  ResultsIndicatorAvailability,
  ResultsRunSummary
} from '../../shared/types';

export const DEFAULT_MANUAL_BASELINE_RUN_ID = 'v0-output';
export const DEFAULT_MANUAL_COMPARISON_RUN_ID = 'v4.0-output';
const DEFAULT_MANUAL_OVERLAY_INDICATOR_ID = 'core_ooLTI';
const KPI_BASELINE_EPSILON = 1e-12;
const KPI_DELTA_DECIMALS = 2;

export interface GroupedIndicatorSection {
  id: 'core_indicator' | 'output';
  title: string;
  items: ResultsIndicatorAvailability[];
}

export interface ManualRunSelection {
  baselineRunId: string;
  comparisonRunId: string;
}

export interface KpiDetailRow {
  key: KpiMetricKey;
  label: string;
  units: 'dynamic' | 'ratio';
}

export const KPI_DETAIL_ROWS: KpiDetailRow[] = [
  { key: 'mean', label: 'Mean (month)', units: 'dynamic' },
  { key: 'cv', label: 'CV (month)', units: 'ratio' },
  { key: 'range', label: 'Month Range (month)', units: 'dynamic' }
];

export function groupIndicatorsBySource(
  indicators: ResultsIndicatorAvailability[]
): GroupedIndicatorSection[] {
  const groups: GroupedIndicatorSection[] = [
    { id: 'core_indicator', title: 'Core indicators', items: [] },
    { id: 'output', title: 'Output', items: [] }
  ];

  for (const indicator of indicators) {
    const group = groups.find((entry) => entry.id === indicator.source);
    if (group) {
      group.items.push(indicator);
    }
  }

  return groups.filter((group) => group.items.length > 0);
}

export function resolveSelectedIndicatorIds(
  indicators: ResultsIndicatorAvailability[],
  current: string[]
): string[] {
  const availableIds = indicators.filter((indicator) => indicator.available).map((indicator) => indicator.id);
  const availableSet = new Set(availableIds);
  const filtered = current.filter((id) => availableSet.has(id));
  return filtered.length > 0 ? filtered : availableIds;
}

export function resolveActiveIndicatorId(
  selectedIndicatorIds: string[],
  compareIndicators: ResultsCompareIndicator[],
  current: string
): string {
  const compareIds = compareIndicators.map((indicatorPayload) => indicatorPayload.indicator.id);
  const selectableIds = compareIds.length > 0 ? compareIds : selectedIndicatorIds;
  if (selectableIds.length === 0) {
    return '';
  }
  if (selectableIds.includes(current)) {
    return current;
  }
  if (selectableIds.includes(DEFAULT_MANUAL_OVERLAY_INDICATOR_ID)) {
    return DEFAULT_MANUAL_OVERLAY_INDICATOR_ID;
  }
  return selectableIds[0];
}

export function resolveActiveIndicatorPayload(
  compareIndicators: ResultsCompareIndicator[],
  selectedIndicatorIds: string[],
  current: string
): ResultsCompareIndicator | null {
  const resolvedIndicatorId = resolveActiveIndicatorId(selectedIndicatorIds, compareIndicators, current);
  return (
    compareIndicators.find((indicatorPayload) => indicatorPayload.indicator.id === current) ??
    compareIndicators.find((indicatorPayload) => indicatorPayload.indicator.id === resolvedIndicatorId) ??
    compareIndicators[0] ??
    null
  );
}

export function sortKpis(kpis: KpiMetricSummary[]): KpiMetricSummary[] {
  return [...kpis].sort((left, right) => left.title.localeCompare(right.title));
}

function findPreferredRunId(
  runs: ResultsRunSummary[],
  preferredRunId: string,
  excludeRunId = ''
): string {
  const matched = runs.find((run) => run.runId === preferredRunId && run.runId !== excludeRunId);
  return matched?.runId ?? '';
}

function findFirstDistinctRunId(runs: ResultsRunSummary[], excludeRunId = ''): string {
  return runs.find((run) => run.runId !== excludeRunId)?.runId ?? '';
}

export function resolveManualRunSelection(
  runs: ResultsRunSummary[],
  requestedBaselineRunId: string,
  requestedComparisonRunId: string
): ManualRunSelection {
  if (runs.length === 0) {
    return {
      baselineRunId: '',
      comparisonRunId: ''
    };
  }

  const availableRunIds = new Set(runs.map((run) => run.runId));
  const hasRequestedBaseline = requestedBaselineRunId.trim().length > 0;
  const hasRequestedComparison = requestedComparisonRunId.trim().length > 0;
  const requestedBaseline = availableRunIds.has(requestedBaselineRunId) ? requestedBaselineRunId : '';
  const requestedComparison = availableRunIds.has(requestedComparisonRunId) ? requestedComparisonRunId : '';

  if (requestedBaseline) {
    return {
      baselineRunId: requestedBaseline,
      comparisonRunId: requestedComparison && requestedComparison !== requestedBaseline ? requestedComparison : ''
    };
  }

  if (hasRequestedBaseline || hasRequestedComparison) {
    return {
      baselineRunId:
        findPreferredRunId(runs, DEFAULT_MANUAL_BASELINE_RUN_ID) || findFirstDistinctRunId(runs),
      comparisonRunId: ''
    };
  }

  const baselineRunId =
    findPreferredRunId(runs, DEFAULT_MANUAL_BASELINE_RUN_ID) || findFirstDistinctRunId(runs);
  const comparisonRunId =
    findPreferredRunId(runs, DEFAULT_MANUAL_COMPARISON_RUN_ID, baselineRunId) ||
    findFirstDistinctRunId(runs, baselineRunId);

  return {
    baselineRunId,
    comparisonRunId
  };
}

export function computeKpiPercentDelta(
  baselineValue: number | null,
  comparisonValue: number | null
): number | null {
  if (
    baselineValue === null ||
    comparisonValue === null ||
    !Number.isFinite(baselineValue) ||
    !Number.isFinite(comparisonValue) ||
    Math.abs(baselineValue) < KPI_BASELINE_EPSILON
  ) {
    return null;
  }

  return ((comparisonValue - baselineValue) / baselineValue) * 100;
}

export function getKpiMetricValue(kpi: KpiMetricSummary | null, key: KpiMetricKey): number | null {
  return kpi ? kpi[key] : null;
}

function isPointDeltaUnit(units: string): boolean {
  return units === '%' || units === 'rate';
}

function formatSignedFixed(value: number, suffix: string): string {
  const normalizedValue = Math.abs(value) < KPI_BASELINE_EPSILON ? 0 : value;
  const sign = normalizedValue >= 0 ? '+' : '';
  return `${sign}${normalizedValue.toLocaleString('en-GB', {
    minimumFractionDigits: KPI_DELTA_DECIMALS,
    maximumFractionDigits: KPI_DELTA_DECIMALS
  })}${suffix}`;
}

export function formatKpiValue(value: number | null, units: string): string {
  if (value === null || !Number.isFinite(value)) {
    return 'n/a';
  }

  if (units === 'GBP') {
    return `£${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
  }
  if (units === '%') {
    return `${value.toLocaleString('en-GB', { maximumFractionDigits: 2 })}%`;
  }
  if (units === 'rate') {
    return `${(value * 100).toLocaleString('en-GB', { maximumFractionDigits: 2 })}%`;
  }
  if (units === 'ratio') {
    return `${value.toLocaleString('en-GB', { maximumFractionDigits: 3 })}x`;
  }
  if (units === 'count' || units === 'count/month') {
    return value.toLocaleString('en-GB', { maximumFractionDigits: 0 });
  }
  return value.toLocaleString('en-GB', { maximumFractionDigits: 3 });
}

export function computeKpiDeltaValue(
  baselineValue: number | null,
  comparisonValue: number | null,
  units: string
): number | null {
  if (
    baselineValue === null ||
    comparisonValue === null ||
    !Number.isFinite(baselineValue) ||
    !Number.isFinite(comparisonValue)
  ) {
    return null;
  }

  if (units === '%') {
    return comparisonValue - baselineValue;
  }
  if (units === 'rate') {
    return (comparisonValue - baselineValue) * 100;
  }
  return computeKpiPercentDelta(baselineValue, comparisonValue);
}

export function getKpiDeltaLabel(units: string): string {
  return isPointDeltaUnit(units) ? 'pp delta' : '% delta';
}

export function formatKpiDeltaValue(value: number | null, units: string): string {
  if (value === null || !Number.isFinite(value)) {
    return 'n/a';
  }

  if (isPointDeltaUnit(units)) {
    return formatSignedFixed(value, ' pp');
  }
  return formatSignedFixed(value, '%');
}
