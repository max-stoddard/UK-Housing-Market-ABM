// Author: Max Stoddard
import { useEffect, useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import type {
  ValidationMetricSummary,
  ValidationOverviewPayload
} from '../../shared/types';
import { EChart } from '../components/EChart';
import {
  API_RETRY_DELAY_MS,
  fetchValidationOverview,
  fetchVersions,
  isRetryableApiError
} from '../lib/api';
import {
  buildVersionLabelState,
  formatVersionOptionLabel,
  getLatestStableVersion
} from '../lib/versionLabels';

type ValidationSortMode =
  | 'highest_loss'
  | 'lowest_loss'
  | 'metric_name'
  | 'most_inside_band'
  | 'least_inside_band';

const DEFAULT_SORT_MODE: ValidationSortMode = 'highest_loss';
const DEFAULT_VALIDATION_TARGET_YEAR = 2024;
const REFERENCE_VALIDATION_TARGET_YEAR = 2011;
const TRACKED_VALIDATION_SERIES_NAME = '2024 validation';
const V0_REFERENCE_SERIES_NAME = '2011 validation (v0 and v0o2)';

function formatNumber(value: number | null, digits = 3): string {
  if (value === null) {
    return 'Unsupported';
  }
  return value.toLocaleString('en-GB', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits > 0 ? Math.min(1, digits) : 0
  });
}

function formatTargetBand(metric: ValidationMetricSummary): string {
  if (!metric.targetBand) {
    return 'Unsupported';
  }
  return `${formatNumber(metric.targetBand.lower, 2)} to ${formatNumber(metric.targetBand.upper, 2)}`;
}

function formatTargetValue(metric: ValidationMetricSummary): string {
  return formatNumber(metric.sourceValue, 2);
}

function formatAcceptanceRange(metric: ValidationMetricSummary): string {
  if (metric.sourceValue === null) {
    return 'Unsupported';
  }
  const halfWidth = Math.abs(metric.sourceValue) * 0.25;
  return `${formatNumber(metric.sourceValue - halfWidth, 2)} to ${formatNumber(metric.sourceValue + halfWidth, 2)}`;
}

function formatInsideRate(value: number | null): string {
  if (value === null) {
    return 'Unsupported';
  }
  return `${(value * 100).toLocaleString('en-GB', { maximumFractionDigits: 1 })}%`;
}

function formatLoss(value: number | null): string {
  return value === null ? 'Unsupported' : formatNumber(value, 4);
}

function formatLossDelta(value: number | null): string {
  if (value === null) {
    return 'Unsupported';
  }
  if (Math.abs(value) < 1e-12) {
    return formatLoss(0);
  }
  return `${value > 0 ? '+' : '-'}${formatLoss(Math.abs(value))}`;
}

function formatLossDeltaPercent(value: number | null): string {
  if (value === null) {
    return 'Unsupported';
  }
  if (Math.abs(value) < 1e-12) {
    return '0%';
  }
  return `${value > 0 ? '+' : '-'}${Math.abs(value).toLocaleString('en-GB', { maximumFractionDigits: 1 })}%`;
}

function lossDeltaClassName(value: number | null): string {
  return [
    'validation-loss-cell',
    value === null ? 'validation-loss-unsupported' : '',
    value !== null && value > 0 ? 'validation-loss-delta-positive' : '',
    value !== null && value < 0 ? 'validation-loss-delta-negative' : ''
  ]
    .filter(Boolean)
    .join(' ');
}

function formatMetricWeight(value: number): string {
  return value.toLocaleString('en-GB', {
    maximumFractionDigits: 4
  });
}

function formatLossFamily(metric: ValidationMetricSummary): string | null {
  if (!metric.lossFamily) {
    return null;
  }
  const familyLabel =
    metric.lossFamily === 'positive_level'
      ? 'Positive level'
      : metric.lossFamily === 'signed_additive'
        ? 'Signed additive'
        : metric.lossFamily === 'bounded_low_is_better'
          ? 'Bounded low-is-better'
          : metric.lossFamily === 'bounded_share'
            ? 'Bounded share'
            : 'Diagnostic';
  const transform = metric.lossTransform ? `, ${metric.lossTransform.replace(/_/gu, ' ')}` : '';
  return `Loss family: ${familyLabel}${transform}`;
}

function formatLossScaleBasisLabel(basis: ValidationMetricSummary['lossScaleBasis']): string {
  if (basis === 'source_value') {
    return 'source target level';
  }
  if (basis === 'target_band_midpoint') {
    return 'target-band midpoint';
  }
  if (basis === 'target_band_upper') {
    return 'target-band upper bound';
  }
  if (basis === 'target_band_lower_abs') {
    return 'absolute target lower bound';
  }
  if (basis === 'target_band_upper_abs') {
    return 'absolute target upper bound';
  }
  if (basis === 'target_band_half_width') {
    return 'target-band half-width';
  }
  if (basis === 'target_band_width') {
    return 'target-band width';
  }
  if (basis === 'bounded_share_domain_width') {
    return 'bounded share domain width';
  }
  if (basis === 'metric_floor') {
    return 'metric floor';
  }
  return 'not applicable';
}

function formatLossScaleBasis(metric: ValidationMetricSummary): string | null {
  const notes: string[] = [];
  if (metric.lossScale !== null && metric.lossScaleBasis !== null && metric.lossScaleBasis !== 'not_applicable') {
    notes.push(`Loss scale ${formatNumber(metric.lossScale, 4)} from ${formatLossScaleBasisLabel(metric.lossScaleBasis)}`);
  }
  if (
    metric.additiveScale !== null &&
    metric.additiveScaleBasis !== null &&
    metric.additiveScaleBasis !== 'not_applicable'
  ) {
    notes.push(
      `Additive scale ${formatNumber(metric.additiveScale, 4)} from ${formatLossScaleBasisLabel(metric.additiveScaleBasis)}`
    );
  }
  return notes.length > 0 ? notes.join(' · ') : null;
}

function getPathTail(pathValue: string | null): string | null {
  if (!pathValue) {
    return null;
  }
  const parts = pathValue.split('/');
  return parts[parts.length - 1] ?? pathValue;
}

function formatSourceReference(metric: ValidationMetricSummary, index: number): {
  key: string;
  label: string;
  title: string;
} {
  const reference = metric.sourceReferences[index];
  const documentLabel = getPathTail(reference?.sourceDocumentPath ?? null) ?? reference?.label ?? metric.sourceLabel;
  const parts = [documentLabel];
  if (reference?.sourcePage !== null && reference?.sourcePage !== undefined) {
    parts.push(`p.${reference.sourcePage}`);
  }
  if (reference?.sourceTable) {
    parts.push(reference.sourceTable);
  }
  const title = [
    reference?.label ?? metric.sourceLabel,
    reference?.sourceDocumentPath ?? metric.sourceDocumentPath ?? '',
    reference?.notes ?? ''
  ]
    .filter(Boolean)
    .join('\n');
  return {
    key: `${metric.metricId}-${index}`,
    label: parts.join(' · '),
    title
  };
}

function buildSourceReferences(metric: ValidationMetricSummary): Array<{ key: string; label: string; title: string }> {
  if (metric.sourceReferences.length > 0) {
    return metric.sourceReferences.map((_, index) => formatSourceReference(metric, index));
  }
  const documentLabel = getPathTail(metric.sourceDocumentPath) ?? metric.sourceLabel;
  const parts = [documentLabel];
  if (metric.sourcePage !== null) {
    parts.push(`p.${metric.sourcePage}`);
  }
  if (metric.sourceTable) {
    parts.push(metric.sourceTable);
  }
  return [
    {
      key: `${metric.metricId}-primary`,
      label: parts.join(' · '),
      title: [metric.sourceLabel, metric.sourceDocumentPath ?? '', metric.bandNotes ?? ''].filter(Boolean).join('\n')
    }
  ];
}

interface ValidationTooltipRow {
  axisValue?: string;
  data?: number | null | { value?: number | null };
  marker?: string;
  seriesName?: string;
}

interface ValidationChartClickParams {
  name?: string;
  seriesName?: string;
}

function formatValidationTargetYearLabel(validationTargetYear: number): string {
  return `${validationTargetYear} evidence`;
}

function formatValidationYearOptionLabel(validationTargetYear: number): string {
  return `${validationTargetYear} validation`;
}

function getCanonicalValidationVersionRank(label: string): number {
  if (label.startsWith('Optimised 2011 model')) {
    return 0;
  }
  if (label.startsWith('Original 2011 model')) {
    return 1;
  }
  if (label.startsWith('Best 2024 model')) {
    return 2;
  }
  if (label.startsWith('Latest 2024 model')) {
    return 3;
  }
  return 4;
}

function orderValidationVersionOptions(
  versions: readonly string[],
  formatVersionLabel: (version: string) => string
): string[] {
  return versions
    .map((version, index) => ({
      version,
      index,
      rank: getCanonicalValidationVersionRank(formatVersionLabel(version))
    }))
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .map((item) => item.version);
}

function formatReferenceLineLabel(label: string, validationTargetYear: number): string {
  return `${label} (${validationTargetYear} comparator)`;
}

function getTooltipValue(data: ValidationTooltipRow['data']): number | null {
  if (typeof data === 'number') {
    return data;
  }
  if (data && typeof data === 'object' && typeof data.value === 'number') {
    return data.value;
  }
  return null;
}

function buildChartOption(overview: ValidationOverviewPayload): EChartsOption {
  const selectedTrackedIndex =
    overview.selectedValidationTargetYear === DEFAULT_VALIDATION_TARGET_YEAR
      ? overview.trend.points.findIndex((point) => point.version === overview.selectedVersion)
      : -1;
  const pointsByVersion = new Map(overview.trend.points.map((point) => [point.version, point]));
  const referencePointsByVersion = new Map(overview.trend.referencePoints.map((point) => [point.version, point]));
  const selectedReferencePoint =
    overview.selectedValidationTargetYear === REFERENCE_VALIDATION_TARGET_YEAR
      ? referencePointsByVersion.get(overview.selectedVersion)
      : null;
  const referenceLine = overview.trend.referenceLine;
  const referenceLineLabel = referenceLine
    ? formatReferenceLineLabel(referenceLine.label, referenceLine.validationTargetYear)
    : null;
  const series: NonNullable<EChartsOption['series']> = [];

  if (referenceLine && referenceLineLabel) {
    series.push({
      type: 'line',
      name: referenceLineLabel,
      smooth: false,
      symbol: 'none',
      data: overview.trend.points.map(() => referenceLine.overallCompositeLoss),
      lineStyle: {
        color: '#8f5b00',
        width: 1.8,
        type: 'dashed'
      },
      emphasis: {
        disabled: true
      },
      z: 1
    });
  }

  series.push({
    type: 'line',
    name: TRACKED_VALIDATION_SERIES_NAME,
    smooth: true,
    showSymbol: true,
    symbol: 'circle',
    symbolSize: 10,
    cursor: 'pointer',
    data: overview.trend.points.map((point) => ({
      name: point.version,
      value: point.overallCompositeLoss
    })),
    lineStyle: { color: '#0b7285', width: 2.4 },
    itemStyle: { color: '#0b7285' },
    z: 2,
    markPoint:
      selectedTrackedIndex >= 0
        ? {
            symbol: 'circle',
            symbolSize: 18,
            itemStyle: {
              color: '#d9480f',
              borderColor: '#fff4e6',
              borderWidth: 3
            },
            label: {
              show: true,
              formatter: overview.selectedVersion,
              position: 'top',
              distance: 10,
              color: '#8f3b13',
              backgroundColor: '#fff4e6',
              borderColor: '#ffd8a8',
              borderWidth: 1,
              borderRadius: 999,
              padding: [4, 8],
              fontWeight: 700
            },
            data: [
              {
                name: overview.selectedVersion,
                xAxis: overview.trend.points[selectedTrackedIndex]?.version,
                yAxis: overview.trend.points[selectedTrackedIndex]?.overallCompositeLoss
              }
            ]
          }
        : undefined
  });

  const referenceSeriesData = overview.trend.points.map((point) => {
    const referencePoint = referencePointsByVersion.get(point.version);
    if (!referencePoint) {
      return null;
    }
    return {
      name: point.version,
      value: referencePoint.overallCompositeLoss
    };
  });
  if (referenceSeriesData.some((point) => point !== null)) {
    series.push({
      type: 'line',
      name: V0_REFERENCE_SERIES_NAME,
      smooth: false,
      showSymbol: true,
      symbol: 'diamond',
      symbolSize: 11,
      connectNulls: false,
      data: referenceSeriesData,
      lineStyle: { color: '#6741d9', width: 2.2 },
      itemStyle: { color: '#6741d9' },
      z: 3,
      markPoint:
        selectedReferencePoint
          ? {
              symbol: 'diamond',
              symbolSize: 20,
              itemStyle: {
                color: '#d9480f',
                borderColor: '#fff4e6',
                borderWidth: 3
              },
              label: {
                show: true,
                formatter: overview.selectedVersion,
                position: 'top',
                distance: 10,
                color: '#8f3b13',
                backgroundColor: '#fff4e6',
                borderColor: '#ffd8a8',
                borderWidth: 1,
                borderRadius: 999,
                padding: [4, 8],
                fontWeight: 700
              },
              data: [
                {
                  name: overview.selectedVersion,
                  xAxis: overview.selectedVersion,
                  yAxis: selectedReferencePoint.overallCompositeLoss
                }
              ]
            }
          : undefined
    });
  }

  return {
    legend: {
      top: 8,
      left: 56,
      textStyle: { color: '#50625a' }
    },
    tooltip: {
      trigger: 'axis',
      formatter: (rawParams: unknown) => {
        const rows = (Array.isArray(rawParams) ? rawParams : [rawParams]) as ValidationTooltipRow[];
        const axisValue = String(rows[0]?.axisValue ?? '');
        const point = pointsByVersion.get(axisValue);
        const referencePoint = referencePointsByVersion.get(axisValue);
        if (!point) {
          return '';
        }

        const tooltipRows = [
          `<strong>${point.version}</strong>`,
          `Tracked summary: ${formatValidationTargetYearLabel(point.validationTargetYear)}`
        ];

        for (const row of rows) {
          const value = getTooltipValue(row.data);
          if (value === null) {
            continue;
          }
          const seriesName = row.seriesName ?? TRACKED_VALIDATION_SERIES_NAME;
          const evidenceLabel =
            seriesName === V0_REFERENCE_SERIES_NAME && referencePoint
              ? formatValidationTargetYearLabel(referencePoint.validationTargetYear)
              : seriesName === referenceLineLabel && referenceLine
                ? formatValidationTargetYearLabel(referenceLine.validationTargetYear)
                : formatValidationTargetYearLabel(point.validationTargetYear);
          tooltipRows.push(`${row.marker ?? ''}${seriesName}: ${formatNumber(value, 4)} (${evidenceLabel})`);
        }

        return tooltipRows.join('<br/>');
      }
    },
    grid: { left: 64, right: 28, top: 52, bottom: 56, containLabel: true },
    xAxis: {
      type: 'category',
      data: overview.trend.points.map((point) => point.version),
      axisLabel: { color: '#50625a' }
    },
    yAxis: {
      type: 'value',
      name: 'Validation loss',
      nameLocation: 'middle',
      nameGap: 52,
      axisLabel: { color: '#50625a' }
    },
    series
  };
}

function compareNullableNumbers(left: number | null, right: number | null, descending = false): number {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }
  return descending ? right - left : left - right;
}

function buildMetricSearchText(metric: ValidationMetricSummary): string {
  return [metric.label, metric.metricId, metric.sourceLabel, metric.sourceIndicatorLabel ?? '']
    .join(' ')
    .toLowerCase();
}

function sortMetrics(metrics: ValidationMetricSummary[], sortMode: ValidationSortMode): ValidationMetricSummary[] {
  return [...metrics].sort((left, right) => {
    if (sortMode === 'highest_loss') {
      const lossComparison = compareNullableNumbers(left.metricLoss, right.metricLoss, true);
      if (lossComparison !== 0) {
        return lossComparison;
      }
    } else if (sortMode === 'lowest_loss') {
      const lossComparison = compareNullableNumbers(left.metricLoss, right.metricLoss);
      if (lossComparison !== 0) {
        return lossComparison;
      }
    } else if (sortMode === 'metric_name') {
      const metricComparison = left.label.localeCompare(right.label);
      if (metricComparison !== 0) {
        return metricComparison;
      }
    } else if (sortMode === 'most_inside_band') {
      const insideBandComparison = compareNullableNumbers(left.insideRate, right.insideRate, true);
      if (insideBandComparison !== 0) {
        return insideBandComparison;
      }
    } else if (sortMode === 'least_inside_band') {
      const insideBandComparison = compareNullableNumbers(left.insideRate, right.insideRate);
      if (insideBandComparison !== 0) {
        return insideBandComparison;
      }
    }

    const weightComparison = right.metricWeight - left.metricWeight;
    if (weightComparison !== 0) {
      return weightComparison;
    }
    return left.label.localeCompare(right.label);
  });
}

export function ValidationPage() {
  const [overview, setOverview] = useState<ValidationOverviewPayload | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<string>('');
  const [selectedValidationTargetYear, setSelectedValidationTargetYear] =
    useState<number>(DEFAULT_VALIDATION_TARGET_YEAR);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isWaitingForApi, setIsWaitingForApi] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [inProgressVersions, setInProgressVersions] = useState<string[]>([]);
  const [metricSearch, setMetricSearch] = useState<string>('');
  const [sortMode, setSortMode] = useState<ValidationSortMode>(DEFAULT_SORT_MODE);
  const [openMetricIds, setOpenMetricIds] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    const load = async () => {
      setIsLoading(true);
      setIsWaitingForApi(false);
      setError('');

      try {
        const [response, versionsPayload] = await Promise.all([
          fetchValidationOverview(selectedVersion || undefined, selectedValidationTargetYear),
          fetchVersions()
        ]);
        if (cancelled) {
          return;
        }
        setOverview(response);
        setSelectedVersion(response.selectedVersion);
        setSelectedValidationTargetYear(response.selectedValidationTargetYear);
        setInProgressVersions(versionsPayload.inProgressVersions);
      } catch (loadError) {
        if (cancelled) {
          return;
        }
        if (isRetryableApiError(loadError)) {
          setIsWaitingForApi(true);
          retryTimer = window.setTimeout(() => {
            void load();
          }, API_RETRY_DELAY_MS);
          return;
        }
        setError((loadError as Error).message);
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
    };
  }, [selectedVersion, selectedValidationTargetYear]);

  const chartOption = useMemo(() => {
    if (!overview || overview.trend.points.length === 0) {
      return null;
    }
    return buildChartOption(overview);
  }, [overview]);

  const summary = overview?.selectedSummary ?? null;
  const displayedValidationTargetYear =
    overview?.selectedValidationTargetYear ?? summary?.validationTargetYear ?? selectedValidationTargetYear;
  const availableValidationTargetYears =
    overview?.availableValidationTargetYearsByVersion[selectedVersion] ?? [DEFAULT_VALIDATION_TARGET_YEAR];
  const openMetricIdSet = useMemo(() => new Set(openMetricIds), [openMetricIds]);
  const inProgressVersionSet = useMemo(() => new Set(inProgressVersions), [inProgressVersions]);
  const latestStableValidationVersion = useMemo(
    () => getLatestStableVersion(overview?.availableVersions ?? [], inProgressVersions),
    [overview, inProgressVersions]
  );

  useEffect(() => {
    setOpenMetricIds([]);
  }, [summary?.version, summary?.validationTargetYear]);

  const filteredMetrics = useMemo(() => {
    if (!summary) {
      return [];
    }

    const searchTerm = metricSearch.trim().toLowerCase();
    const searchFilteredMetrics = searchTerm
      ? summary.metrics.filter((metric) => buildMetricSearchText(metric).includes(searchTerm))
      : summary.metrics;

    return sortMetrics(searchFilteredMetrics, sortMode);
  }, [summary, metricSearch, sortMode]);

  const toggleMetricSources = (metricId: string) => {
    setOpenMetricIds((current) =>
      current.includes(metricId) ? current.filter((value) => value !== metricId) : [...current, metricId]
    );
  };

  const formatValidationVersionOptionLabel = (version: string) =>
    formatVersionOptionLabel(version, buildVersionLabelState(version, latestStableValidationVersion, inProgressVersionSet));
  const orderedValidationVersions = orderValidationVersionOptions(
    overview?.availableVersions ?? [],
    formatValidationVersionOptionLabel
  );

  const selectVersionAndValidationYear = (version: string, validationTargetYear: number) => {
    if (version === selectedVersion && validationTargetYear === selectedValidationTargetYear) {
      return;
    }
    setSelectedVersion(version);
    setSelectedValidationTargetYear(validationTargetYear);
  };

  const handleVersionChange = (version: string) => {
    const availableYears =
      overview?.availableValidationTargetYearsByVersion[version] ?? [DEFAULT_VALIDATION_TARGET_YEAR];
    selectVersionAndValidationYear(
      version,
      availableYears.includes(selectedValidationTargetYear)
        ? selectedValidationTargetYear
        : DEFAULT_VALIDATION_TARGET_YEAR
    );
  };

  const handleChartClick = (rawParams: unknown) => {
    if (!rawParams || typeof rawParams !== 'object') {
      return;
    }

    const params = rawParams as ValidationChartClickParams;
    if (typeof params.name !== 'string') {
      return;
    }

    if (params.seriesName === TRACKED_VALIDATION_SERIES_NAME) {
      selectVersionAndValidationYear(params.name, DEFAULT_VALIDATION_TARGET_YEAR);
    } else if (params.seriesName === V0_REFERENCE_SERIES_NAME) {
      selectVersionAndValidationYear(params.name, REFERENCE_VALIDATION_TARGET_YEAR);
    }
  };

  return (
    <section className="validation-layout validation-framework-layout">
      <article className="results-card">
        <h2>Validation</h2>
        <div className="validation-intro-copy">
          <p>
            This page keeps the trend chart on the tracked 2024 timeline, overlays the original <code>v0</code> and
            optimised <code>v0o2</code> 2011 validation comparisons, and lets you switch the metric table between the
            2024 summary and the available 2011 comparator for the selected version. Other pre-<code>v1.0</code>
            optimised/candidate versions are hidden from validation.
          </p>
          {displayedValidationTargetYear === REFERENCE_VALIDATION_TARGET_YEAR && (
            <p>
              The 2011 validation summary keeps <code>core_hpiStd</code> benchmarked to the same
              2005-01..2024-12 official std used in the 2024 view, while <code>core_hpiCyclePeriod</code> remains
              2011-anchored.
            </p>
          )}
          <p>
            The line chart is a secondary overview for ranking and trend-checking only. Validation matters because a
            housing-market ABM needs to be realistic against external evidence and robust across multiple seeds, not
            just tuned to look good in a single run.
          </p>
          <p className="validation-formula">
            <strong>Metric loss</strong> uses family-aware distance: log-ratio for positive levels, robust additive
            distance for signed metrics, bounded-domain-normalized percentage-point distance for tenure shares, and
            bounded low-is-better scoring for JSD, plus spread and seeds outside band components. Target bands still
            determine pass, warn, and fail status.
          </p>
        </div>
      </article>

      {error && <p className="error-banner">{error}</p>}
      {isWaitingForApi && (
        <p className="waiting-banner">Waiting for API to become available. Retrying every 2 seconds...</p>
      )}

      <article className="results-card">
        <div className="validation-overview-header">
          <div>
            <h3>Validation Loss Across Versions</h3>
            <p className="validation-card-subtitle">
              Lower validation loss means the model is closer to the external targets and more stable across seeds.
              Click a 2024 validation point or a sparse <code>v0</code>/<code>v0o2</code> 2011 validation point to load
              that version and year in the metric results below.
            </p>
          </div>
        </div>
        {isLoading ? (
          <p className="loading-banner">Loading validation overview...</p>
        ) : chartOption ? (
          <EChart option={chartOption} className="chart validation-chart" onClick={handleChartClick} />
        ) : (
          <p className="info-banner">No tracked validation summaries are available.</p>
        )}
      </article>

      <article className="results-card">
        <h3>Validation Results by Metric</h3>
        <p className="validation-card-subtitle">
          Each row shows one validation metric for {summary?.version ?? selectedVersion} against{' '}
          {displayedValidationTargetYear} targets, the model summary across seeds, the signed loss delta versus{' '}
          <code>v0 2011</code> where negative is better and positive is worse, and the raw metric weight
          supplied in the validation payload.
        </p>
        <div className="results-controls validation-mode-row">
          <label className="validation-selector">
            <span>Version</span>
            <select value={selectedVersion} onChange={(event) => handleVersionChange(event.target.value)}>
              {orderedValidationVersions.map((version) => (
                <option key={version} value={version}>
                  {formatValidationVersionOptionLabel(version)}
                </option>
              ))}
            </select>
          </label>
          <label className="validation-selector">
            <span>Validation Year</span>
            <select
              value={displayedValidationTargetYear}
              onChange={(event) => setSelectedValidationTargetYear(Number.parseInt(event.target.value, 10))}
            >
              {availableValidationTargetYears.map((validationTargetYear) => (
                <option key={validationTargetYear} value={validationTargetYear}>
                  {formatValidationYearOptionLabel(validationTargetYear)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="results-controls validation-table-controls">
          <label>
            <span>Search metrics</span>
            <input
              type="search"
              value={metricSearch}
              onChange={(event) => setMetricSearch(event.target.value)}
              placeholder="Search by metric or source"
            />
          </label>
          <label>
            <span>Sort by</span>
            <select value={sortMode} onChange={(event) => setSortMode(event.target.value as ValidationSortMode)}>
              <option value="highest_loss">Highest loss first</option>
              <option value="lowest_loss">Lowest loss first</option>
              <option value="metric_name">Metric name A-Z</option>
              <option value="most_inside_band">Most inside-band seeds</option>
              <option value="least_inside_band">Least inside-band seeds</option>
            </select>
          </label>
          <div className="validation-control-summary">Showing {filteredMetrics.length} metrics</div>
        </div>
        {filteredMetrics.length === 0 ? (
          <p className="info-banner validation-table-empty">No validation metrics match the current search term.</p>
        ) : (
          <div className="validation-table-wrap">
            <table className="validation-metrics-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Target value</th>
                  <th>Target band</th>
                  <th>Acceptance range</th>
                  <th>Sim. mean</th>
                  <th>Sim. IQR</th>
                  <th>Seeds in band</th>
                  <th>Loss delta vs v0 2011</th>
                  <th>Loss delta % vs v0 2011</th>
                  <th>Weight</th>
                  <th>Loss</th>
                </tr>
              </thead>
              <tbody>
                {filteredMetrics.map((metric) => {
                  const isSourcesOpen = openMetricIdSet.has(metric.metricId);

                  return (
                    <tr key={metric.metricId}>
                      <td>
                        <div className="validation-metric-cell">
                          <strong>{metric.label}</strong>
                          <button
                            type="button"
                            className="table-toggle validation-source-toggle"
                            onClick={() => toggleMetricSources(metric.metricId)}
                          >
                            {isSourcesOpen ? 'Hide provenance & sources' : 'Provenance & sources'}
                          </button>
                          {isSourcesOpen && (
                            <div className="validation-source-panel">
                              <div className="validation-source-label">{metric.sourceLabel}</div>
                              {buildSourceReferences(metric).map((reference) => (
                                <div key={reference.key} className="validation-source-ref" title={reference.title}>
                                  {reference.label}
                                </div>
                              ))}
                              {formatLossFamily(metric) && (
                                <div className="validation-source-note">{formatLossFamily(metric)}</div>
                              )}
                              {formatLossScaleBasis(metric) && (
                                <div className="validation-source-note">{formatLossScaleBasis(metric)}</div>
                              )}
                              {metric.bandNotes && <div className="validation-source-note">{metric.bandNotes}</div>}
                            </div>
                          )}
                        </div>
                      </td>
                      <td>{formatTargetValue(metric)}</td>
                      <td>{formatTargetBand(metric)}</td>
                      <td>{formatAcceptanceRange(metric)}</td>
                      <td>{formatNumber(metric.seedMean, 3)}</td>
                      <td>
                        {formatNumber(metric.p25, 3)} to {formatNumber(metric.p75, 3)}
                      </td>
                      <td>{formatInsideRate(metric.insideRate)}</td>
                      <td className={lossDeltaClassName(metric.lossDeltaVsReference2011)}>
                        {formatLossDelta(metric.lossDeltaVsReference2011)}
                      </td>
                      <td className={lossDeltaClassName(metric.lossDeltaPercentVsReference2011)}>
                        {formatLossDeltaPercent(metric.lossDeltaPercentVsReference2011)}
                      </td>
                      <td>{formatMetricWeight(metric.metricWeight)}</td>
                      <td
                        className={`validation-loss-cell ${metric.metricLoss === null ? 'validation-loss-unsupported' : ''}`}
                      >
                        {formatLoss(metric.metricLoss)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
