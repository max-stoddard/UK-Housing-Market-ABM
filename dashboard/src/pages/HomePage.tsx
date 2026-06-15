import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import type { EChartsOption } from 'echarts';
import type { HomePreviewItem } from '../../shared/types';
import {
  API_RETRY_DELAY_MS,
  fetchHomePreview,
  fetchVersions,
  isRetryableApiError
} from '../lib/api';
import { EChart } from '../components/EChart';
import { getAxisSpec } from '../lib/chartAxes';
import { jointHeatmapOption, resolveAdaptiveHeatmapLayout } from '../lib/jointHeatmapOption';
import {
  binnedSingleOption,
  curveSingleOption,
  formatChartNumber,
  jointLayoutOverrides,
  scalarSingleOption
} from '../lib/compareChartOptions';
import { LoadingSkeleton } from '../components/LoadingSkeleton';

const PREVIEW_PARAMETER_IDS = [
  'wealth_given_income_joint',
  'house_price_lognormal',
  'downpayment_oo_lognormal',
  'btl_probability_bins'
];
const BUY_QUAD_CURVE_LAYOUT_OVERRIDES = { gridLeft: 108, gridRight: 30, yAxisNameGap: 76 };

type HomeLoadState = 'loading' | 'waiting' | 'ready' | 'error';

function buildSingleMedianLegendMarkers(value: number): Array<{ x: number; name: string; color: string }> {
  return Number.isFinite(value)
    ? [
        {
          x: value,
          name: 'Median',
          color: '#495057'
        }
      ]
    : [];
}

function buildPreviewOption(item: HomePreviewItem): EChartsOption {
  const axisSpec = getAxisSpec(item.id);

  switch (item.visualPayload.type) {
    case 'scalar':
      return scalarSingleOption(item.visualPayload.values, item.rightVersion, axisSpec.scalar.xTitle, axisSpec.scalar.yTitle);

    case 'binned_distribution':
      return binnedSingleOption(item, axisSpec.binned.xTitle, axisSpec.binned.yTitle);

    case 'joint_distribution': {
      const payload = item.visualPayload;
      const leftValues = payload.matrix.left.map((cell) => cell.value);
      const rightValues = payload.matrix.right.map((cell) => cell.value);
      const min = Math.min(...leftValues, ...rightValues);
      const max = Math.max(...leftValues, ...rightValues);
      return jointHeatmapOption({
        title: item.rightVersion,
        cells: payload.matrix.right,
        xLabels: payload.matrix.xAxis.labels,
        yLabels: payload.matrix.yAxis.labels,
        min,
        max,
        colors: ['#eff6ff', '#1d4ed8'],
        xAxisName: axisSpec.joint.xTitle,
        yAxisName: axisSpec.joint.yTitle,
        layout: resolveAdaptiveHeatmapLayout({
          context: 'preview',
          xLabels: payload.matrix.xAxis.labels,
          yLabels: payload.matrix.yAxis.labels,
          xAxisName: axisSpec.joint.xTitle,
          yAxisName: axisSpec.joint.yTitle,
          layout: jointLayoutOverrides(item.id)
        })
      });
    }

    case 'lognormal_pair':
      return curveSingleOption(
        item.rightVersion,
        item.visualPayload.curveRight,
        axisSpec.curve.xTitle,
        axisSpec.curve.yTitle,
        (value) => formatChartNumber(value),
        undefined,
        undefined,
        undefined,
        buildSingleMedianLegendMarkers(item.visualPayload.median.right)
      );

    case 'power_law_pair':
      return curveSingleOption(
        item.rightVersion,
        item.visualPayload.curveRight,
        axisSpec.curve.xTitle,
        axisSpec.curve.yTitle,
        (value) => formatChartNumber(value)
      );

    case 'buy_quad':
      return curveSingleOption(
        item.rightVersion,
        item.visualPayload.budgetRight,
        axisSpec.buyBudget.xTitle,
        axisSpec.buyBudget.yTitle,
        (value) => formatChartNumber(value),
        undefined,
        undefined,
        BUY_QUAD_CURVE_LAYOUT_OVERRIDES
      );

    default:
      return {};
  }
}

export function HomePage() {
  const [previewItems, setPreviewItems] = useState<HomePreviewItem[]>([]);
  const [previewIndex, setPreviewIndex] = useState<number>(0);
  const [isPreviewPaused, setIsPreviewPaused] = useState<boolean>(false);
  const [loadState, setLoadState] = useState<HomeLoadState>('loading');
  const [loadError, setLoadError] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    const resetHomeStats = () => {
      setPreviewItems([]);
    };

    const load = async () => {
      setLoadState('loading');
      setLoadError('');

      try {
        const versionsPayload = await fetchVersions();

        if (cancelled) {
          return;
        }

        const versions = versionsPayload.versions;

        const latest = versions[versions.length - 1] ?? '';
        if (latest) {
          const previewPayload = await fetchHomePreview(latest);
          if (cancelled) {
            return;
          }
          const byId = new Map(previewPayload.items.map((item) => [item.id, item]));
          const ordered = PREVIEW_PARAMETER_IDS.map((id) => byId.get(id)).filter((item): item is HomePreviewItem =>
            Boolean(item)
          );
          setPreviewItems(ordered);
        } else {
          setPreviewItems([]);
        }

        setLoadState('ready');
      } catch (error) {
        if (cancelled) {
          return;
        }

        resetHomeStats();

        if (isRetryableApiError(error)) {
          setLoadState('waiting');
          retryTimer = window.setTimeout(() => {
            void load();
          }, API_RETRY_DELAY_MS);
          return;
        }

        setLoadError((error as Error).message);
        setLoadState('error');
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
    };
  }, []);

  useEffect(() => {
    if (previewItems.length === 0) {
      setPreviewIndex(0);
      return;
    }
    setPreviewIndex((current) => (current >= previewItems.length ? 0 : current));
  }, [previewItems]);

  useEffect(() => {
    if (previewItems.length <= 1 || isPreviewPaused) {
      return;
    }
    const timer = window.setInterval(() => {
      setPreviewIndex((current) => (current + 1) % previewItems.length);
    }, 7600);
    return () => window.clearInterval(timer);
  }, [previewItems.length, isPreviewPaused]);

  const previewItem = previewItems[previewIndex];

  return (
    <section className="home-layout">
      {loadState === 'waiting' && (
        <p className="waiting-banner">Waiting for API to become available. Retrying every 2 seconds...</p>
      )}
      {loadState === 'error' && <p className="error-banner">{loadError}</p>}

      <div className="summary-card fade-up">
        <p className="eyebrow">Project Summary</p>
        <h2>Purpose and Model Context</h2>
        <p>
          I&apos;m Max Stoddard, and this website is the primary interface for my Imperial College London BEng Individual
          project: improving the UK Housing Market ABM based on the ABM developed by the Bank of England.
        </p>
        <p>
          My work focuses on speeding up the model, updating calibration inputs to reflect post-COVID UK conditions,
          strengthening validation against real-world patterns, and improving interpretability through clearer visual tools.
        </p>
        <p>
          The aim of this website is to make the model genuinely interactive: a place where anyone can explore the UK housing
          market dynamics, run and compare scenarios, and see key outputs in a clear, visual form.
        </p>
        <div className="summary-links">
          <a href="https://github.com/max-stoddard/UK-Housing-Market-ABM" target="_blank" rel="noreferrer">
            <span className="summary-link-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" role="img" focusable="false">
                <path
                  fill="currentColor"
                  d="M3 5.5A2.5 2.5 0 015.5 3h5A2.5 2.5 0 0113 5.5v13a2.5 2.5 0 01-2.5 2.5h-5A2.5 2.5 0 013 18.5v-13zm2.5-.5a.5.5 0 00-.5.5v13a.5.5 0 00.5.5h5a.5.5 0 00.5-.5v-13a.5.5 0 00-.5-.5h-5zM14 6h4.5A2.5 2.5 0 0121 8.5v10a2.5 2.5 0 01-2.5 2.5H14V19h4.5a.5.5 0 00.5-.5v-10a.5.5 0 00-.5-.5H14V6z"
                />
              </svg>
            </span>
            <span>Source Code</span>
          </a>
          <a href="https://github.com/max-stoddard" target="_blank" rel="noreferrer">
            <span className="summary-link-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" role="img" focusable="false">
                <path
                  fill="currentColor"
                  d="M12 2C6.48 2 2 6.58 2 12.23c0 4.52 2.87 8.35 6.84 9.71.5.1.68-.22.68-.49 0-.24-.01-1.03-.01-1.86-2.78.62-3.37-1.22-3.37-1.22-.45-1.19-1.11-1.5-1.11-1.5-.9-.63.07-.62.07-.62 1 .07 1.52 1.05 1.52 1.05.88 1.54 2.31 1.1 2.87.84.09-.66.35-1.1.63-1.35-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.04 1.03-2.76-.1-.26-.45-1.31.1-2.72 0 0 .84-.28 2.75 1.05A9.34 9.34 0 0112 6.84a9.2 9.2 0 012.5.35c1.9-1.33 2.74-1.05 2.74-1.05.56 1.41.21 2.46.11 2.72.64.72 1.03 1.64 1.03 2.76 0 3.93-2.35 4.8-4.6 5.05.36.32.68.95.68 1.92 0 1.39-.01 2.5-.01 2.84 0 .27.18.59.69.49A10.28 10.28 0 0022 12.23C22 6.58 17.52 2 12 2z"
                />
              </svg>
            </span>
            <span>GitHub</span>
          </a>
          <a href="https://www.linkedin.com/in/maxstoddard/" target="_blank" rel="noreferrer">
            <span className="summary-link-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" role="img" focusable="false">
                <path
                  fill="currentColor"
                  d="M6.94 8.5a1.73 1.73 0 110-3.46 1.73 1.73 0 010 3.46zM5.4 9.8h3.08V19H5.4V9.8zm5.02 0h2.95v1.26h.04c.41-.78 1.4-1.6 2.89-1.6 3.1 0 3.67 2.08 3.67 4.79V19h-3.08v-4.17c0-.99-.02-2.27-1.35-2.27-1.35 0-1.55 1.08-1.55 2.2V19h-3.08V9.8z"
                />
              </svg>
            </span>
            <span>LinkedIn</span>
          </a>
        </div>
      </div>

      <div className="hero-card fade-up">
        <div className="hero-label-row">
          <p className="eyebrow">Interactive ABM Workspace</p>
          <span className="tag-pill">Just Launched</span>
        </div>
        <h2>Visualize and track calibrated UK housing model parameters</h2>
        {previewItem ? (
          <div
            className="hero-preview"
            onMouseEnter={() => setIsPreviewPaused(true)}
            onMouseLeave={() => setIsPreviewPaused(false)}
          >
            <div className="hero-preview-head">
              <p>Preview from Calibration Versions</p>
              <strong>{previewItem.title}</strong>
            </div>
            <div key={previewItem.id} className="hero-preview-chart-shell">
              <EChart option={buildPreviewOption(previewItem)} className="chart hero-preview-chart" />
            </div>
            <div className="hero-preview-dots" role="tablist" aria-label="Parameter preview selector">
              {previewItems.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  className={index === previewIndex ? 'active' : ''}
                  onClick={() => setPreviewIndex(index)}
                  aria-label={`Show preview ${index + 1}: ${item.title}`}
                />
              ))}
            </div>
          </div>
        ) : loadState !== 'error' ? (
          <LoadingSkeleton
            className="hero-preview-loading loading-skeleton-chart"
            ariaLabel="Loading calibration preview chart"
          />
        ) : null}
        <Link to="/compare" className="primary-button">
          Open Calibration Versions
        </Link>
      </div>
    </section>
  );
}
