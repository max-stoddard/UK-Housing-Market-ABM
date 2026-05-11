import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type {
  KpiMetricKey,
  SensitivityDeltaTrendSeries,
  SensitivityExperimentChartsPayload,
  SensitivityExperimentMetadata,
  SensitivityExperimentResultsPayload,
  SensitivityExperimentSummary,
  SensitivityIndicatorPointMetric
} from '../../../../shared/types';
import type { EChartsOption } from 'echarts';
import { EChart } from '../../../components/EChart';
import {
  API_RETRY_DELAY_MS,
  fetchSensitivityExperiment,
  fetchSensitivityExperimentCharts,
  fetchSensitivityExperimentResults,
  fetchSensitivityExperiments,
  isRetryableApiError
} from '../../../lib/api';
import { buildExperimentsPath } from '../routeState';
import { DEFAULT_EXPERIMENT_ROUTE_STATE } from '../types';

const KPI_OPTIONS: Array<{ key: KpiMetricKey; label: string }> = [
  { key: 'mean', label: 'Mean (monthly)' },
  { key: 'cv', label: 'CV (monthly)' },
  { key: 'annualisedTrend', label: 'Annualised Trend (annualised)' },
  { key: 'range', label: 'Range (monthly, P95-P5)' }
];

interface SensitivityResultsViewProps {
  requestedExperimentId: string;
  onSelectedExperimentIdChange: (experimentId: string) => void;
  sidebarSubtitle: string;
}

function statusClass(status: SensitivityExperimentSummary['status']): string {
  switch (status) {
    case 'succeeded':
      return 'status-pill complete';
    case 'running':
      return 'status-pill partial';
    case 'queued':
    case 'canceled':
      return 'coverage-pill unsupported';
    default:
      return 'status-pill invalid';
  }
}

function formatStatus(status: SensitivityExperimentSummary['status']): string {
  return status.replace('_', ' ');
}

function formatMetric(value: number | null): string {
  if (value === null) {
    return 'n/a';
  }
  return value.toLocaleString('en-GB', { maximumFractionDigits: 6 });
}

function formatSignedPercent(value: number | null): string {
  if (value === null) {
    return 'n/a';
  }
  return `${value >= 0 ? '+' : ''}${value.toLocaleString('en-GB', { maximumFractionDigits: 6 })}%`;
}

function buildTornadoOption(charts: SensitivityExperimentChartsPayload, kpi: KpiMetricKey): EChartsOption {
  const sorted = [...charts.tornado].sort((left, right) => {
    const leftValue = left.maxAbsDeltaByKpi[kpi] ?? Number.NEGATIVE_INFINITY;
    const rightValue = right.maxAbsDeltaByKpi[kpi] ?? Number.NEGATIVE_INFINITY;
    return rightValue - leftValue;
  });

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: unknown) => {
        if (typeof value !== 'number' || Number.isNaN(value)) {
          return 'n/a';
        }
        return `${value.toLocaleString('en-GB', { maximumFractionDigits: 6 })}%`;
      }
    },
    grid: {
      left: 80,
      right: 24,
      top: 20,
      bottom: 160
    },
    xAxis: {
      type: 'category',
      axisLabel: {
        interval: 0,
        rotate: 45
      },
      data: sorted.map((item) => item.title)
    },
    yAxis: {
      type: 'value',
      name: `Max |% diff ${KPI_OPTIONS.find((option) => option.key === kpi)?.label ?? kpi}|`,
      nameGap: 42,
      nameLocation: 'middle'
    },
    series: [
      {
        type: 'bar',
        data: sorted.map((item) => item.maxAbsDeltaByKpi[kpi]),
        itemStyle: {
          color: '#0b7285'
        }
      }
    ]
  };
}

function buildDeltaTrendOption(series: SensitivityDeltaTrendSeries, parameterKey: string, kpi: KpiMetricKey): EChartsOption {
  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: unknown) => {
        if (typeof value !== 'number' || Number.isNaN(value)) {
          return 'n/a';
        }
        return `${value.toLocaleString('en-GB', { maximumFractionDigits: 6 })}%`;
      }
    },
    grid: {
      left: 80,
      right: 24,
      top: 20,
      bottom: 48
    },
    xAxis: {
      type: 'value',
      name: parameterKey,
      nameGap: 30,
      nameLocation: 'middle'
    },
    yAxis: {
      type: 'value',
      name: `% diff ${KPI_OPTIONS.find((option) => option.key === kpi)?.label ?? kpi}`,
      nameLocation: 'middle',
      nameGap: 48
    },
    series: [
      {
        type: 'line',
        showSymbol: true,
        connectNulls: false,
        data: series.points.map((point) => [point.parameterValue, point.deltaByKpi[kpi]])
      }
    ]
  };
}

export function SensitivityResultsView({
  requestedExperimentId,
  onSelectedExperimentIdChange,
  sidebarSubtitle
}: SensitivityResultsViewProps) {
  const [experiments, setExperiments] = useState<SensitivityExperimentSummary[]>([]);
  const [selectedExperimentId, setSelectedExperimentId] = useState<string>('');
  const [detail, setDetail] = useState<SensitivityExperimentMetadata | null>(null);
  const [results, setResults] = useState<SensitivityExperimentResultsPayload | null>(null);
  const [charts, setCharts] = useState<SensitivityExperimentChartsPayload | null>(null);
  const [selectedIndicatorId, setSelectedIndicatorId] = useState<string>('');
  const [selectedKpiKey, setSelectedKpiKey] = useState<KpiMetricKey>('mean');
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [pageError, setPageError] = useState<string>('');

  useEffect(() => {
    onSelectedExperimentIdChange(selectedExperimentId);
  }, [onSelectedExperimentIdChange, selectedExperimentId]);

  const refreshHistory = async () => {
    try {
      const payload = await fetchSensitivityExperiments();
      setExperiments(payload.experiments);
      setSelectedExperimentId((current) => {
        if (current && payload.experiments.some((item) => item.experimentId === current)) {
          return current;
        }
        return payload.experiments[0]?.experimentId ?? '';
      });
    } catch (error) {
      if (!isRetryableApiError(error)) {
        setPageError((error as Error).message);
      }
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const refreshDetail = async (experimentId: string) => {
    if (!experimentId) {
      setDetail(null);
      setResults(null);
      setCharts(null);
      return;
    }

    setIsLoadingDetail(true);
    try {
      const [detailPayload, resultsPayload, chartsPayload] = await Promise.all([
        fetchSensitivityExperiment(experimentId),
        fetchSensitivityExperimentResults(experimentId),
        fetchSensitivityExperimentCharts(experimentId)
      ]);

      setDetail(detailPayload.experiment);
      setResults(resultsPayload);
      setCharts(chartsPayload);
      setSelectedIndicatorId((current) => {
        if (current && chartsPayload.deltaTrend.some((series) => series.indicatorId === current)) {
          return current;
        }
        return chartsPayload.deltaTrend[0]?.indicatorId ?? '';
      });
    } catch (error) {
      if (!isRetryableApiError(error)) {
        setPageError((error as Error).message);
      }
    } finally {
      setIsLoadingDetail(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    const load = async () => {
      await refreshHistory();
    };

    void load().catch((error: unknown) => {
      if (cancelled) {
        return;
      }
      if (isRetryableApiError(error)) {
        retryTimer = window.setTimeout(() => {
          void load();
        }, API_RETRY_DELAY_MS);
        return;
      }
      setPageError((error as Error).message);
    });

    return () => {
      cancelled = true;
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
    };
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refreshHistory();
    }, 3000);

    return () => {
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!requestedExperimentId || experiments.length === 0) {
      return;
    }

    if (!experiments.some((experiment) => experiment.experimentId === requestedExperimentId)) {
      return;
    }

    setSelectedExperimentId(requestedExperimentId);
  }, [experiments, requestedExperimentId]);

  useEffect(() => {
    void refreshDetail(selectedExperimentId);
  }, [selectedExperimentId]);

  const activeDeltaSeries = useMemo(() => {
    if (!charts || !selectedIndicatorId) {
      return null;
    }
    return charts.deltaTrend.find((series) => series.indicatorId === selectedIndicatorId) ?? null;
  }, [charts, selectedIndicatorId]);

  const selectedIndicatorMetricByPoint = useMemo(() => {
    if (!results || !selectedIndicatorId) {
      return [];
    }

    return results.points.map((point) => {
      const metric = point.indicatorMetrics.find((item) => item.indicatorId === selectedIndicatorId) ?? null;
      return { point, metric };
    });
  }, [results, selectedIndicatorId]);

  const selectedIndicatorTitle = useMemo(() => {
    if (!activeDeltaSeries) {
      return '';
    }
    return activeDeltaSeries.title;
  }, [activeDeltaSeries]);

  return (
    <section className="results-layout">
      {pageError && <p className="error-banner">{pageError}</p>}

      <article className="results-card">
        <h2>Sensitivity Results</h2>
        <p>
          Inspect tornado charts, KPI % differences from baseline, and per-point metrics for completed or in-progress sensitivity experiments.
        </p>
        <div className="summary-links">
          <Link
            className="summary-link-inline"
            to={buildExperimentsPath({
              ...DEFAULT_EXPERIMENT_ROUTE_STATE,
              type: 'manual',
              mode: 'view'
            })}
          >
            Open Model Runs
          </Link>
          <Link
            className="summary-link-inline"
            to={buildExperimentsPath({
              ...DEFAULT_EXPERIMENT_ROUTE_STATE,
              type: 'sensitivity',
              mode: 'run'
            })}
          >
            Run Sensitivity
          </Link>
        </div>
      </article>

      <div className="results-grid">
        <aside className="results-panel">
          <div className="results-panel-header">
            <h2>Runs</h2>
            <p>{sidebarSubtitle}</p>
          </div>
          {isLoadingHistory ? (
            <p className="loading-banner">Loading experiments...</p>
          ) : experiments.length === 0 ? (
            <p className="info-banner">No sensitivity experiments yet.</p>
          ) : (
            <ul className="run-list">
              {experiments.map((experiment) => (
                <li
                  key={experiment.experimentId}
                  className={`run-item ${selectedExperimentId === experiment.experimentId ? 'focused' : ''}`}
                >
                  <button
                    type="button"
                    className="run-focus-btn"
                    onClick={() => setSelectedExperimentId(experiment.experimentId)}
                  >
                    {selectedExperimentId === experiment.experimentId ? 'Viewing' : 'View'}
                  </button>
                  <strong>{experiment.title || experiment.experimentId}</strong>
                  <p>
                    Parameter: {experiment.parameter.title} ({experiment.parameter.key})
                  </p>
                  <p>
                    <span className={statusClass(experiment.status)}>{formatStatus(experiment.status)}</span>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="results-main">
          <article className="results-card">
            <h3>Experiment Detail</h3>
            {isLoadingDetail ? (
              <p className="loading-banner">Loading experiment detail...</p>
            ) : !detail ? (
              <p className="info-banner">Select an experiment to view analytics.</p>
            ) : (
              <div className="sensitivity-detail-grid">
                <p>
                  <strong>Experiment:</strong> {detail.title || detail.experimentId}
                </p>
                <p>
                  <strong>Status:</strong> <span className={statusClass(detail.status)}>{formatStatus(detail.status)}</span>
                </p>
                <p>
                  <strong>Baseline:</strong> {detail.baseline}
                </p>
                <p>
                  <strong>Parameter:</strong> {detail.parameter.title} ({detail.parameter.key})
                </p>
                <p>
                  <strong>Range:</strong> {detail.parameter.min} to {detail.parameter.max}
                </p>
                <p>
                  <strong>Seeds:</strong> {detail.seeds?.join(', ') || detail.seedsPerPoint || 1}
                </p>
                <p>
                  <strong>Max workers:</strong> {detail.maxWorkers ?? 1}
                </p>
                {detail.failureReason && <p className="error-banner">Failure reason: {detail.failureReason}</p>}
              </div>
            )}
          </article>

          {charts && (
            <article className="results-card">
              <div className="sensitivity-trend-header">
                <h3>Tornado + Delta Trend</h3>
                <label>
                  KPI basis
                  <select
                    value={selectedKpiKey}
                    onChange={(event) => setSelectedKpiKey(event.target.value as KpiMetricKey)}
                  >
                    {KPI_OPTIONS.map((option) => (
                      <option key={option.key} value={option.key}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <EChart className="validation-chart" option={buildTornadoOption(charts, selectedKpiKey)} />

              <div className="sensitivity-trend-header">
                <h4>Indicator Delta Trend</h4>
                <label>
                  Indicator
                  <select
                    value={selectedIndicatorId}
                    onChange={(event) => setSelectedIndicatorId(event.target.value)}
                  >
                    {charts.deltaTrend.map((series) => (
                      <option key={series.indicatorId} value={series.indicatorId}>
                        {series.title}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {activeDeltaSeries ? (
                <EChart
                  className="validation-chart"
                  option={buildDeltaTrendOption(activeDeltaSeries, charts.parameter.key, selectedKpiKey)}
                />
              ) : (
                <p className="info-banner">No trend data available.</p>
              )}
            </article>
          )}

          {results && (
            <article className="results-card">
              <h3>Per-Point KPI Table {selectedIndicatorTitle ? `(${selectedIndicatorTitle})` : ''}</h3>
              {selectedIndicatorMetricByPoint.length === 0 ? (
                <p className="info-banner">No executed points yet.</p>
              ) : (
                <div className="sensitivity-table-wrap">
                  <table className="sensitivity-point-table">
                    <thead>
                      <tr>
                        <th>Point</th>
                        <th>Value</th>
                        <th>Status</th>
                        <th>Mean (monthly)</th>
                        <th>% diff Mean (monthly)</th>
                        <th>CV (monthly)</th>
                        <th>% diff CV (monthly)</th>
                        <th>Annualised Trend (annualised)</th>
                        <th>% diff Annualised Trend (annualised)</th>
                        <th>Range (monthly, P95-P5)</th>
                        <th>% diff Range (monthly, P95-P5)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedIndicatorMetricByPoint.map(({ point, metric }) => {
                        const values = metric as SensitivityIndicatorPointMetric | null;
                        return (
                          <tr key={point.pointId}>
                            <td>{point.label}</td>
                            <td>{point.value}</td>
                            <td>
                              <span className={statusClass(point.status)}>{formatStatus(point.status)}</span>
                            </td>
                            <td>{formatMetric(values?.kpi.mean ?? null)}</td>
                            <td>{formatSignedPercent(values?.deltaFromBaseline.mean ?? null)}</td>
                            <td>{formatMetric(values?.kpi.cv ?? null)}</td>
                            <td>{formatSignedPercent(values?.deltaFromBaseline.cv ?? null)}</td>
                            <td>{formatMetric(values?.kpi.annualisedTrend ?? null)}</td>
                            <td>{formatSignedPercent(values?.deltaFromBaseline.annualisedTrend ?? null)}</td>
                            <td>{formatMetric(values?.kpi.range ?? null)}</td>
                            <td>{formatSignedPercent(values?.deltaFromBaseline.range ?? null)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </article>
          )}
        </div>
      </div>
    </section>
  );
}
