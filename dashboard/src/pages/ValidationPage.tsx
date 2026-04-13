// Author: Max Stoddard
import { useEffect, useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import type {
  ValidationFamilySummary,
  ValidationMetricSummary,
  ValidationOverviewPayload
} from '../../shared/types';
import { EChart } from '../components/EChart';
import {
  API_RETRY_DELAY_MS,
  fetchValidationOverview,
  isRetryableApiError
} from '../lib/api';

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
        return `${String(point.axisValue ?? '')}<br/>Composite loss: ${formatNumber(point.data ?? null, 4)}`;
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
      name: 'Composite loss',
      nameLocation: 'middle',
      nameGap: 52,
      axisLabel: { color: '#50625a' }
    },
    series: [
      {
        type: 'line',
        name: 'Composite loss',
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

function familyStatusTone(family: ValidationFamilySummary): 'pass' | 'warn' | 'fail' {
  if (family.statusCounts.fail > 0) {
    return 'fail';
  }
  if (family.statusCounts.warn > 0) {
    return 'warn';
  }
  return 'pass';
}

function sortMetrics(metrics: ValidationMetricSummary[]): ValidationMetricSummary[] {
  return [...metrics].sort((left, right) => {
    if (left.familyId !== right.familyId) {
      return left.familyId.localeCompare(right.familyId);
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
  const sortedMetrics = useMemo(() => (summary ? sortMetrics(summary.metrics) : []), [summary]);

  return (
    <section className="validation-layout validation-framework-layout">
      <article className="results-card">
        <h2>Validation</h2>
        <p>
          The 2024 framework scores each version against tracked multi-seed summaries. The trend is a compact ranking
          aid, while the family cards and metric table remain the primary evidence.
        </p>
      </article>

      {error && <p className="error-banner">{error}</p>}
      {isWaitingForApi && (
        <p className="waiting-banner">Waiting for API to become available. Retrying every 2 seconds...</p>
      )}

      <article className="results-card">
        <div className="validation-overview-header">
          <div>
            <h3>Overall composite trend</h3>
            <p>Lower composite loss is better. The selected point drives the family and metric drill-down below.</p>
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
        <h3>Family summary</h3>
        <div className="validation-family-grid">
          {summary?.familySummaries.map((family) => (
            <section
              key={family.familyId}
              className={`validation-family-card validation-family-card-${familyStatusTone(family)}`}
            >
              <p className="validation-family-eyebrow">{family.familyId}</p>
              <h4>{family.label}</h4>
              <p className="validation-family-loss">Loss {formatNumber(family.loss, 4)}</p>
              <p className="validation-family-counts">
                Pass {family.statusCounts.pass} · Warn {family.statusCounts.warn} · Fail {family.statusCounts.fail} ·
                Unsupported {family.statusCounts.unsupported}
              </p>
            </section>
          ))}
        </div>
      </article>

      <article className="results-card">
        <h3>Metric scorecard for {summary?.version ?? selectedVersion}</h3>
        <div className="validation-table-wrap">
          <table className="validation-metrics-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Family</th>
                <th>Target band</th>
                <th>Mean</th>
                <th>p25-p75</th>
                <th>Seeds inside band</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedMetrics.map((metric) => (
                <tr key={metric.metricId}>
                  <td>
                    <strong>{metric.label}</strong>
                    <div className="validation-metric-meta">{metric.metricId}</div>
                  </td>
                  <td>{metric.familyId}</td>
                  <td>{formatTargetBand(metric)}</td>
                  <td>{formatNumber(metric.seedMean, 3)}</td>
                  <td>
                    {formatNumber(metric.p25, 3)} to {formatNumber(metric.p75, 3)}
                  </td>
                  <td>{formatInsideRate(metric.insideRate)}</td>
                  <td>
                    <span className={`validation-status-pill validation-status-${metric.status}`}>{metric.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
