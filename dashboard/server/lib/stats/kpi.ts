import type { KpiMetricValues } from '../../../shared/types';

const KPI_EPSILON = 1e-12;
const DEFAULT_WINDOW_SIZE = 120;
const POST_BURN_IN_START_INDEX = 200;

function percentile(sortedValues: number[], percentileValue: number): number | null {
  if (sortedValues.length === 0) {
    return null;
  }
  if (sortedValues.length === 1) {
    return sortedValues[0];
  }

  const clamped = Math.max(0, Math.min(100, percentileValue));
  const position = (clamped / 100) * (sortedValues.length - 1);
  const lowerIndex = Math.floor(position);
  const upperIndex = Math.ceil(position);
  if (lowerIndex === upperIndex) {
    return sortedValues[lowerIndex];
  }

  const fraction = position - lowerIndex;
  const lowerValue = sortedValues[lowerIndex];
  const upperValue = sortedValues[upperIndex];
  return lowerValue + (upperValue - lowerValue) * fraction;
}

export function buildEmptyKpiValues(): KpiMetricValues {
  return {
    mean: null,
    cv: null,
    annualisedTrend: null,
    range: null
  };
}

export function selectTailWindow(values: readonly number[], windowSize = DEFAULT_WINDOW_SIZE): number[] {
  if (values.length === 0) {
    return [];
  }
  return values.slice(Math.max(0, values.length - windowSize));
}

export function selectPost200Window(values: readonly number[], startIndex = POST_BURN_IN_START_INDEX): number[] {
  if (values.length <= startIndex) {
    return [];
  }
  return values.slice(startIndex);
}

export function computeKpiFromValues(values: readonly number[]): KpiMetricValues {
  if (values.length === 0) {
    return buildEmptyKpiValues();
  }

  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => {
    const delta = value - mean;
    return sum + delta * delta;
  }, 0) / values.length;
  const stdev = Math.sqrt(Math.max(0, variance));
  const cv = Math.abs(mean) < KPI_EPSILON ? null : stdev / Math.abs(mean);

  let annualisedTrend: number | null = null;
  if (values.length >= 2) {
    const n = values.length;
    const sumX = ((n - 1) * n) / 2;
    const sumXX = ((n - 1) * n * (2 * n - 1)) / 6;
    const sumY = values.reduce((sum, value) => sum + value, 0);
    const sumXY = values.reduce((sum, value, index) => sum + index * value, 0);
    const denominator = n * sumXX - sumX * sumX;
    if (Math.abs(denominator) >= KPI_EPSILON) {
      const slopePerMonth = (n * sumXY - sumX * sumY) / denominator;
      annualisedTrend = slopePerMonth * 12;
    }
  }

  const sorted = [...values].sort((left, right) => left - right);
  const p95 = percentile(sorted, 95);
  const p5 = percentile(sorted, 5);
  const range = p95 !== null && p5 !== null ? p95 - p5 : null;

  return {
    mean,
    cv,
    annualisedTrend,
    range
  };
}

export function computeTail120Kpi(values: readonly number[]): KpiMetricValues {
  return computeKpiFromValues(selectTailWindow(values, DEFAULT_WINDOW_SIZE));
}

export function computePost200Kpi(values: readonly number[]): KpiMetricValues {
  return computeKpiFromValues(selectPost200Window(values));
}
