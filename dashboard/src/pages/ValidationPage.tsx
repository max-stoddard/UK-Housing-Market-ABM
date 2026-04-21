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
  isRetryableApiError
} from '../lib/api';

type ValidationSortMode =
  | 'highest_loss'
  | 'lowest_loss'
  | 'metric_name'
  | 'most_inside_band'
  | 'least_inside_band'
  | 'status_severity';

const DEFAULT_SORT_MODE: ValidationSortMode = 'highest_loss';

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

function formatInsideRate(value: number | null): string {
  if (value === null) {
    return 'Unsupported';
  }
  return `${(value * 100).toLocaleString('en-GB', { maximumFractionDigits: 1 })}%`;
}

function formatStatusLabel(status: ValidationMetricSummary['status']): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatLoss(value: number | null): string {
  return value === null ? 'Unsupported' : formatNumber(value, 4);
}

function formatMetricWeight(value: number): string {
  return value.toLocaleString('en-GB', {
    maximumFractionDigits: 4
  });
}

function formatLossScaleBasis(metric: ValidationMetricSummary): string | null {
  if (metric.lossScale === null || metric.lossScaleBasis === null) {
    return null;
  }
  const basisLabel =
    metric.lossScaleBasis === 'source_value'
      ? 'source target level'
      : metric.lossScaleBasis === 'target_band_midpoint'
        ? 'target-band midpoint'
        : 'target-band upper bound';
  return `Loss scale ${formatNumber(metric.lossScale, 4)} from ${basisLabel}`;
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

function buildChartOption(overview: ValidationOverviewPayload): EChartsOption {
  const selectedIndex = overview.trend.points.findIndex((point) => point.version === overview.selectedVersion);
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (rawParams: unknown) => {
        const rows = Array.isArray(rawParams) ? rawParams : [rawParams];
        const point = rows[0] as { axisValue?: string; data?: number };
        if (!point) {
          return '';
        }
        return `${String(point.axisValue ?? '')}<br/>Validation loss: ${formatNumber(point.data ?? null, 4)}`;
      }
    },
    grid: { left: 64, right: 28, top: 22, bottom: 56, containLabel: true },
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
    series: [
      {
        type: 'line',
        name: 'Validation loss',
        smooth: true,
        data: overview.trend.points.map((point) => point.overallCompositeLoss),
        lineStyle: { color: '#0b7285', width: 2.4 },
        itemStyle: { color: '#0b7285' },
        markPoint:
          selectedIndex >= 0
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
                    xAxis: overview.trend.points[selectedIndex]?.version,
                    yAxis: overview.trend.points[selectedIndex]?.overallCompositeLoss
                  }
                ]
              }
            : undefined
      }
    ]
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

function metricStatusSeverity(status: ValidationMetricSummary['status']): number {
  switch (status) {
    case 'fail':
      return 0;
    case 'warn':
      return 1;
    case 'pass':
      return 2;
    case 'unsupported':
      return 3;
    default:
      return 4;
  }
}

function buildMetricSearchText(metric: ValidationMetricSummary): string {
  return [metric.label, metric.metricId, metric.status, metric.sourceLabel, metric.sourceIndicatorLabel ?? '']
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
    } else if (sortMode === 'status_severity') {
      const severityComparison = metricStatusSeverity(left.status) - metricStatusSeverity(right.status);
      if (severityComparison !== 0) {
        return severityComparison;
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
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isWaitingForApi, setIsWaitingForApi] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
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
        const response = await fetchValidationOverview(selectedVersion || undefined);
        if (cancelled) {
          return;
        }
        setOverview(response);
        setSelectedVersion(response.selectedVersion);
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
  }, [selectedVersion]);

  const chartOption = useMemo(() => {
    if (!overview || overview.trend.points.length === 0) {
      return null;
    }
    return buildChartOption(overview);
  }, [overview]);

  const summary = overview?.selectedSummary ?? null;
  const openMetricIdSet = useMemo(() => new Set(openMetricIds), [openMetricIds]);

  useEffect(() => {
    setOpenMetricIds([]);
  }, [summary?.version]);

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

  return (
    <section className="validation-layout validation-framework-layout">
      <article className="results-card">
        <h2>Validation</h2>
        <div className="validation-intro-copy">
          <p>
            This page compares each version of the model against tracked 2024 target bands using eight-seed validation
            summaries. The table below is the main decision tool because it shows which real-world patterns the model
            matches, misses, or cannot yet support.
          </p>
          <p>
            The line chart is a secondary overview for ranking and trend-checking only. Validation matters because a
            housing-market ABM needs to be realistic against external evidence and robust across multiple seeds, not
            just tuned to look good in a single run.
          </p>
          <p className="validation-formula">
            <strong>Metric loss</strong> = distance relative to target level + 0.25 x spread relative to target level
            + 0.50 x seeds outside band share
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
              Lower validation loss means the model is closer to the external targets and more stable across seeds. The
              selected point controls the metric results below.
            </p>
          </div>
          <label className="validation-selector">
            <span>Version</span>
            <select value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)}>
              {overview?.availableVersions.map((version) => (
                <option key={version} value={version}>
                  {version}
                </option>
              ))}
            </select>
          </label>
        </div>
        {isLoading ? (
          <p className="loading-banner">Loading validation overview...</p>
        ) : chartOption ? (
          <EChart option={chartOption} className="chart validation-chart" />
        ) : (
          <p className="info-banner">No tracked validation summaries are available.</p>
        )}
      </article>

      <article className="results-card">
        <h3>Validation Results by Metric for {summary?.version ?? selectedVersion}</h3>
        <p className="validation-card-subtitle">
          Each row shows one validation metric, the target band it is checked against, the model summary across seeds,
          the status, and the raw metric weight supplied in the validation payload.
        </p>
        <div className="results-controls validation-table-controls">
          <label>
            <span>Search metrics</span>
            <input
              type="search"
              value={metricSearch}
              onChange={(event) => setMetricSearch(event.target.value)}
              placeholder="Search by metric, status, or source"
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
              <option value="status_severity">Status severity</option>
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
                  <th>Target band</th>
                  <th>Mean</th>
                  <th>p25-p75</th>
                  <th>Seeds inside band</th>
                  <th>Weight</th>
                  <th>Loss</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredMetrics.map((metric) => {
                  const isSourcesOpen = openMetricIdSet.has(metric.metricId);

                  return (
                    <tr key={metric.metricId}>
                      <td>
                        <strong>{metric.label}</strong>
                        <div className="validation-metric-meta">{metric.metricId}</div>
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
                            {formatLossScaleBasis(metric) && (
                              <div className="validation-source-note">{formatLossScaleBasis(metric)}</div>
                            )}
                            {metric.bandNotes && <div className="validation-source-note">{metric.bandNotes}</div>}
                          </div>
                        )}
                      </td>
                      <td>{formatTargetBand(metric)}</td>
                      <td>{formatNumber(metric.seedMean, 3)}</td>
                      <td>
                        {formatNumber(metric.p25, 3)} to {formatNumber(metric.p75, 3)}
                      </td>
                      <td>{formatInsideRate(metric.insideRate)}</td>
                      <td>{formatMetricWeight(metric.metricWeight)}</td>
                      <td
                        className={`validation-loss-cell ${metric.metricLoss === null ? 'validation-loss-unsupported' : ''}`}
                      >
                        {formatLoss(metric.metricLoss)}
                      </td>
                      <td>
                        <span className={`validation-status-pill validation-status-${metric.status}`}>
                          {formatStatusLabel(metric.status)}
                        </span>
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
