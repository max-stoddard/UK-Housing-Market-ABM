import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { PassThrough } from 'node:stream';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  compareParameters,
  getHomePreview,
  getInProgressVersions,
  getParameterCatalog,
  getValidationOverview,
  getVersions
} from '../server/lib/service.js';
import { readValidationSummary } from '../server/lib/validationSummaries.js';
import {
  deleteResultsRun,
  getResultsCompare,
  getResultsRunDetail,
  getResultsRunFiles,
  getResultsRuns,
  getResultsSeries
} from '../server/lib/results.js';
import {
  __resetModelRunManagerForTests,
  __setModelRunSpawnForTests,
  cancelModelRunJob,
  clearModelRunJob,
  getModelRunJobLogs,
  getModelRunOptions,
  getResultsStorageSummary,
  listModelRunJobs,
  submitModelRun
} from '../server/lib/modelRuns.js';
import {
  __resetSensitivityRunsForTests,
  __setSensitivityRunSpawnForTests,
  cancelSensitivityExperiment,
  getSensitivityExperiment,
  getSensitivityExperimentCharts,
  getSensitivityExperimentLogs,
  getSensitivityExperimentResults,
  hasActiveSensitivityExperiment,
  listSensitivityExperiments,
  submitSensitivityExperiment
} from '../server/lib/sensitivityRuns.js';
import { cancelExperimentJob, getExperimentJobLogs, listExperimentJobs } from '../server/lib/experimentJobs.js';
import { getConfigPath, parseConfigFile, readNumericCsvRows, resolveConfigDataFilePath } from '../server/lib/io.js';
import { createWriteAuthController, getWriteAuthConfigurationError, resolveDashboardWriteAccess } from '../server/lib/writeAuth.js';
import { loadDashboardInputVersionHistory } from '../server/lib/dashboardInputVersionHistory.js';
import { assertAxisSpecComplete, getAxisSpec } from '../src/lib/chartAxes.js';
import { binnedOption } from '../src/lib/compareChartOptions.js';
import {
  buildExperimentSearchParams,
  normaliseExperimentRouteState,
  parseExperimentRouteState
} from '../src/pages/experiments/routeState.js';
import {
  KPI_DETAIL_ROWS,
  computeKpiDeltaValue,
  computeKpiPercentDelta,
  formatKpiDeltaValue,
  formatKpiValue,
  getKpiMetricValue,
  getKpiDeltaLabel,
  groupIndicatorsBySource,
  resolveActiveIndicatorId,
  resolveManualRunSelection,
  resolveSelectedIndicatorIds
} from '../src/lib/manualResultsView.js';
import { ManualSelectionStatusPills } from '../src/components/ManualSelectionStatusPills.js';
import { buildManualOverlayOption } from '../src/lib/manualOverlayChartOption.js';
import {
  buildResultsRunVersionLabelState,
  buildVersionLabelState,
  extractVersionFromResultsRunId,
  formatVersionOptionLabel,
  getLatestStableVersion
} from '../src/lib/versionLabels.js';
import { computeKpiFromValues } from '../server/lib/stats/kpi.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../..');

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function sumBinnedDensityMass(rows: number[][]): number {
  return sum(rows.map((row) => (row[1] - row[0]) * row[2]));
}

function assertClose(actual: number, expected: number, tolerance: number, message: string): void {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${message}: expected ${expected}, got ${actual}`);
}

function gaussianPercentDensity(percent: number, mu: number, sigma: number): number {
  const denominator = percent * sigma * Math.sqrt(2 * Math.PI);
  const exponent = -((Math.log(percent) - mu) ** 2) / (2 * sigma ** 2);
  return Math.exp(exponent) / denominator;
}

function waitForAsyncTick(ms = 0): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function waitUntil(predicate: () => boolean, timeoutMs = 3000): Promise<void> {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error('Timed out while waiting for asynchronous condition.');
    }
    await waitForAsyncTick(10);
  }
}

const kpiStats = computeKpiFromValues([1, 2, 3, 4, 5]);
assertClose(kpiStats.mean ?? NaN, 3, 1e-9, 'Expected KPI mean to be correct');
assertClose(kpiStats.annualisedTrend ?? NaN, 12, 1e-9, 'Expected annualised trend to be monthly OLS slope x12');
assertClose(kpiStats.range ?? NaN, 3.6, 1e-9, 'Expected KPI range to be p95-p5 with linear interpolation');
assertClose(kpiStats.cv ?? NaN, Math.sqrt(2) / 3, 1e-9, 'Expected KPI CV to use stdev/abs(mean)');

const kpiZeroMean = computeKpiFromValues([-1, 1]);
assert.equal(kpiZeroMean.cv, null, 'Expected KPI CV to be null when mean is near zero');

const kpiSmallWindow = computeKpiFromValues([1, 2]);
assertClose(kpiSmallWindow.range ?? NaN, 0.9, 1e-9, 'Expected KPI percentile interpolation for small window');

const groupedIndicators = groupIndicatorsBySource([
  {
    id: 'core-price',
    title: 'Core price',
    units: 'GBP',
    description: '',
    source: 'core_indicator',
    available: true,
    coverageStatus: 'supported'
  },
  {
    id: 'output-sales',
    title: 'Output sales',
    units: 'count',
    description: '',
    source: 'output',
    available: true,
    coverageStatus: 'supported'
  }
]);
assert.deepEqual(
  groupedIndicators.map((group) => ({ id: group.id, ids: group.items.map((item) => item.id) })),
  [
    { id: 'core_indicator', ids: ['core-price'] },
    { id: 'output', ids: ['output-sales'] }
  ],
  'Expected manual results indicators to group by core_indicator and output'
);

const resolvedDefaultIndicators = resolveSelectedIndicatorIds(
  [
    {
      id: 'core-price',
      title: 'Core price',
      units: 'GBP',
      description: '',
      source: 'core_indicator',
      available: true,
      coverageStatus: 'supported'
    },
    {
      id: 'output-sales',
      title: 'Output sales',
      units: 'count',
      description: '',
      source: 'output',
      available: true,
      coverageStatus: 'supported'
    },
    {
      id: 'hidden',
      title: 'Hidden',
      units: 'count',
      description: '',
      source: 'output',
      available: false,
      coverageStatus: 'unsupported'
    }
  ],
  []
);
assert.deepEqual(
  resolvedDefaultIndicators,
  ['core-price', 'output-sales'],
  'Expected manual results to default-select all available indicators'
);

assert.equal(
  resolveActiveIndicatorId(
    ['core_ooLTI', 'core-price', 'output-sales'],
    [
      {
        indicator: {
          id: 'core_ooLTI',
          title: 'Owner-Occupier LTI (Mean Above Median)',
          units: 'ratio',
          description: '',
          source: 'core_indicator'
        },
        seriesByRun: []
      },
      {
        indicator: {
          id: 'core-price',
          title: 'Core price',
          units: 'GBP',
          description: '',
          source: 'core_indicator'
        },
        seriesByRun: []
      },
      {
        indicator: {
          id: 'output-sales',
          title: 'Output sales',
          units: 'count',
          description: '',
          source: 'output'
        },
        seriesByRun: []
      }
    ],
    ''
  ),
  'core_ooLTI',
  'Expected manual results to default the active overlay indicator to owner-occupier LTI when available'
);

assert.equal(
  resolveActiveIndicatorId(
    ['core_ooLTI', 'output-sales'],
    [
      {
        indicator: {
          id: 'core_ooLTI',
          title: 'Owner-Occupier LTI (Mean Above Median)',
          units: 'ratio',
          description: '',
          source: 'core_indicator'
        },
        seriesByRun: []
      },
      {
        indicator: {
          id: 'output-sales',
          title: 'Output sales',
          units: 'count',
          description: '',
          source: 'output'
        },
        seriesByRun: []
      }
    ],
    'output-sales'
  ),
  'output-sales',
  'Expected active overlay selection to preserve the current indicator when it remains enabled'
);

assert.equal(
  resolveActiveIndicatorId(
    ['output-sales'],
    [
      {
        indicator: {
          id: 'output-sales',
          title: 'Output sales',
          units: 'count',
          description: '',
          source: 'output'
        },
        seriesByRun: []
      }
    ],
    'core-price'
  ),
  'output-sales',
  'Expected active overlay selection to fall back when the previous indicator is no longer enabled'
);

assert.equal(
  resolveActiveIndicatorId([], [], ''),
  '',
  'Expected active overlay selection to return an empty value when no indicators are selectable'
);

const manualSelectionRuns = [
  {
    runId: 'v4.1-output',
    path: 'Results/v4.1-output',
    modifiedAt: '2026-03-09T00:00:00.000Z',
    createdAt: '2026-03-09T00:00:00.000Z',
    sizeBytes: 1,
    fileCount: 1,
    status: 'complete' as const,
    configAvailable: true,
    parseCoverage: {
      requiredCount: 1,
      supportedCount: 1,
      emptyCount: 0,
      errorCount: 0
    }
  },
  {
    runId: 'v4.0-output',
    path: 'Results/v4.0-output',
    modifiedAt: '2026-03-08T00:00:00.000Z',
    createdAt: '2026-03-08T00:00:00.000Z',
    sizeBytes: 1,
    fileCount: 1,
    status: 'complete' as const,
    configAvailable: true,
    parseCoverage: {
      requiredCount: 1,
      supportedCount: 1,
      emptyCount: 0,
      errorCount: 0
    }
  },
  {
    runId: 'v0-output',
    path: 'Results/v0-output',
    modifiedAt: '2026-03-07T00:00:00.000Z',
    createdAt: '2026-03-07T00:00:00.000Z',
    sizeBytes: 1,
    fileCount: 1,
    status: 'complete' as const,
    configAvailable: true,
    parseCoverage: {
      requiredCount: 1,
      supportedCount: 1,
      emptyCount: 0,
      errorCount: 0
    }
  }
];

assert.deepEqual(
  resolveManualRunSelection(manualSelectionRuns, '', ''),
  {
    baselineRunId: 'v0-output',
    comparisonRunId: 'v4.0-output'
  },
  'Expected manual results default selection to prefer v0-output baseline and v4.0-output comparison'
);

assert.deepEqual(
  resolveManualRunSelection(manualSelectionRuns, 'missing-run', 'v4.1-output'),
  {
    baselineRunId: 'v0-output',
    comparisonRunId: ''
  },
  'Expected invalid explicit baseline selection to fall back to the preferred baseline and clear comparison'
);

assert.equal(
  extractVersionFromResultsRunId('v4.0-output'),
  'v4.0',
  'Expected canonical results run ids to map back to their calibration version'
);

assert.equal(
  extractVersionFromResultsRunId('policy-demo-v4.0-output'),
  '',
  'Expected non-canonical results run ids not to resolve to calibration versions'
);

const manualRunVersions = ['v0', 'v4.0', 'v4.1'];
const manualRunInProgressVersions = ['v4.1'];

const originalRunLabelState = buildResultsRunVersionLabelState(
  'v0-output',
  manualRunVersions,
  manualRunInProgressVersions
);
assert.equal(originalRunLabelState?.isOriginal, true, 'Expected v0-output to resolve to the Original label state');

const latestRunLabelState = buildResultsRunVersionLabelState(
  'v4.0-output',
  manualRunVersions,
  manualRunInProgressVersions
);
assert.equal(
  latestRunLabelState?.isLatest,
  true,
  'Expected v4.0-output to resolve to Latest when the newer v4.1 snapshot is still in progress'
);

const inProgressRunLabelState = buildResultsRunVersionLabelState(
  'v4.1-output',
  manualRunVersions,
  manualRunInProgressVersions
);
assert.equal(
  inProgressRunLabelState?.isLatest,
  false,
  'Expected in-progress v4.1-output not to resolve to the Latest label state'
);

assert.equal(
  buildResultsRunVersionLabelState('fixture-complete-output', manualRunVersions, manualRunInProgressVersions),
  null,
  'Expected custom run ids not to render Original/Latest labels'
);

const singleOverlayOption = buildManualOverlayOption(
  {
    indicator: {
      id: 'core_housePrice',
      title: 'House price',
      units: 'GBP',
      description: '',
      source: 'core_indicator'
    },
    seriesByRun: [
      {
        runId: 'v0-output',
        points: [
          { modelTime: 200, value: 100 },
          { modelTime: 201, value: 200 },
          { modelTime: 202, value: null },
          { modelTime: 203, value: 300 }
        ]
      }
    ]
  },
  'v0-output',
  ''
);
const singleOverlaySeries = (singleOverlayOption.series as Array<Record<string, any>>) ?? [];
assert.equal(singleOverlaySeries.length, 1, 'Expected single-run overlay to include one plotted series');
assert.equal(singleOverlaySeries[0]?.lineStyle?.color, '#0b7285', 'Expected baseline overlay series to use the baseline color');
assert.equal(
  singleOverlaySeries[0]?.markLine?.data?.[0]?.yAxis,
  200,
  'Expected overlay mean lines to average only the visible non-null points'
);
assert.equal(
  singleOverlaySeries[0]?.markLine?.lineStyle?.type,
  'dotted',
  'Expected overlay mean reference lines to use a dotted style'
);

const compareOverlayOption = buildManualOverlayOption(
  {
    indicator: {
      id: 'core_mortgageApprovals',
      title: 'Mortgage approvals',
      units: 'count/month',
      description: '',
      source: 'core_indicator'
    },
    seriesByRun: [
      {
        runId: 'v0-output',
        points: [
          { modelTime: 200, value: 10 },
          { modelTime: 201, value: 20 }
        ]
      },
      {
        runId: 'v4.0-output',
        points: [
          { modelTime: 200, value: 30 },
          { modelTime: 201, value: 40 }
        ]
      }
    ]
  },
  'v0-output',
  'v4.0-output'
);
const compareOverlaySeries = (compareOverlayOption.series as Array<Record<string, any>>) ?? [];
assert.equal(compareOverlaySeries.length, 2, 'Expected compare overlay to include both plotted series');
assert.equal(compareOverlaySeries[0]?.name, 'Baseline', 'Expected baseline overlay series to use the baseline role label');
assert.equal(compareOverlaySeries[1]?.name, 'Comparison', 'Expected comparison overlay series to use the comparison role label');
assert.equal(compareOverlaySeries[1]?.lineStyle?.color, '#18958b', 'Expected comparison overlay series to use the comparison color');
assert.equal(compareOverlaySeries[0]?.markLine?.data?.[0]?.yAxis, 15, 'Expected baseline overlay mean to be computed from displayed data');
assert.equal(compareOverlaySeries[1]?.markLine?.data?.[0]?.yAxis, 35, 'Expected comparison overlay mean to be computed from displayed data');
assert.equal(compareOverlaySeries[1]?.markLine?.lineStyle?.type, 'dotted', 'Expected comparison overlay mean line to use the dotted style');

const gapOnlyOverlayOption = buildManualOverlayOption(
  {
    indicator: {
      id: 'core_mortgageApprovals',
      title: 'Mortgage approvals',
      units: 'count/month',
      description: '',
      source: 'core_indicator'
    },
    seriesByRun: [
      {
        runId: 'v0-output',
        points: [
          { modelTime: 200, value: 10 },
          { modelTime: 201, value: 20 }
        ]
      },
      {
        runId: 'v4.0-output',
        points: [
          { modelTime: 200, value: null },
          { modelTime: 201, value: null }
        ]
      }
    ]
  },
  'v0-output',
  'v4.0-output'
);
const gapOnlyOverlaySeries = (gapOnlyOverlayOption.series as Array<Record<string, any>>) ?? [];
assert.equal(gapOnlyOverlaySeries.length, 2, 'Expected gap-only overlay payload to still include both plotted series');
assert.equal(gapOnlyOverlaySeries[0]?.markLine?.data?.[0]?.yAxis, 15, 'Expected gap-only overlay baseline mean to still render');
assert.equal(gapOnlyOverlaySeries[1]?.markLine, undefined, 'Expected gap-only overlay series not to render a mean line');

const latestManualStatusMarkup = renderToStaticMarkup(
  createElement(ManualSelectionStatusPills, {
    status: 'complete',
    versionLabelState: latestRunLabelState
  })
);

assert.ok(
  latestManualStatusMarkup.includes('manual-selection-status-pills'),
  'Expected manual results summary status pills to render in a grouped container'
);

assert.ok(
  latestManualStatusMarkup.includes('>complete<') && latestManualStatusMarkup.includes('>Latest<'),
  'Expected the manual results summary status pills to render the Latest tag alongside the completion status'
);

const originalManualStatusMarkup = renderToStaticMarkup(
  createElement(ManualSelectionStatusPills, {
    status: 'complete',
    versionLabelState: originalRunLabelState
  })
);

assert.ok(
  originalManualStatusMarkup.includes('>complete<') && originalManualStatusMarkup.includes('>Original<'),
  'Expected the manual results summary status pills to render the Original tag alongside the completion status'
);

assert.equal(
  computeKpiPercentDelta(100, 125),
  25,
  'Expected KPI percent deltas to compute relative to the baseline run'
);

assert.equal(
  computeKpiPercentDelta(0, 125),
  null,
  'Expected KPI percent deltas to be null when the baseline magnitude is too small'
);

assert.equal(
  computeKpiPercentDelta(100, null),
  null,
  'Expected KPI percent deltas to be null when either side is missing'
);

assert.deepEqual(
  KPI_DETAIL_ROWS.map((row) => row.key),
  ['mean', 'cv', 'annualisedTrend', 'range'],
  'Expected manual results KPI detail tables to include mean first followed by the remaining aggregate metrics'
);

assert.equal(
  getKpiMetricValue(
    {
      indicatorId: 'house-price',
      title: 'Average house price',
      units: 'GBP',
      windowType: 'tail_120',
      mean: 200000,
      cv: 0.12,
      annualisedTrend: 3500,
      range: 50000
    },
    'mean'
  ),
  200000,
  'Expected KPI metric lookup to expose mean values for the manual results detail tables'
);

assert.equal(formatKpiValue(1.33, '%'), '1.33%', 'Expected percent KPI values to show an explicit percent suffix');

assert.equal(formatKpiValue(4.5, 'ratio'), '4.5x', 'Expected ratio KPI values to show an x suffix');

assert.equal(formatKpiValue(0.035, 'rate'), '3.5%', 'Expected rate KPI values to render as human percentages');

assert.equal(getKpiDeltaLabel('%'), 'pp delta', 'Expected percent-like KPI rows to use percentage-point delta labels');

assertClose(
  computeKpiDeltaValue(-0.96, 1.33, '%') ?? NaN,
  2.29,
  1e-9,
  'Expected House Price Growth deltas to be computed in percentage points'
);

assert.equal(
  formatKpiDeltaValue(computeKpiDeltaValue(-0.96, 1.33, '%'), '%'),
  '+2.29 pp',
  'Expected percent-like KPI deltas to render in percentage points'
);

assert.equal(
  computeKpiDeltaValue(100, 125, 'count'),
  25,
  'Expected non-percent KPI deltas to remain relative percent changes'
);

assert.equal(
  formatKpiDeltaValue(computeKpiDeltaValue(100, 125, 'count'), 'count'),
  '+25.00%',
  'Expected non-percent KPI deltas to keep percent formatting'
);

const defaultExperimentRouteState = parseExperimentRouteState(new URLSearchParams(''));
assert.deepEqual(
  defaultExperimentRouteState,
  {
    type: 'manual',
    mode: 'view',
    baselineRunId: '',
    comparisonRunId: '',
    experimentId: '',
    jobRef: ''
  },
  'Expected empty experiment query params to default to manual results view.'
);

const invalidExperimentRouteState = parseExperimentRouteState(
  new URLSearchParams('type=invalid&mode=wat&runId=abc&experimentId=exp-1&jobRef=manual:job-1')
);
assert.deepEqual(
  invalidExperimentRouteState,
  {
    type: 'manual',
    mode: 'view',
    baselineRunId: 'abc',
    comparisonRunId: '',
    experimentId: '',
    jobRef: ''
  },
  'Expected invalid route selectors to fall back to manual results view and clean incompatible params.'
);

const cleanedViewState = normaliseExperimentRouteState({
  type: 'sensitivity',
  mode: 'view',
  baselineRunId: 'run-1',
  comparisonRunId: 'run-2',
  experimentId: 'exp:42',
  jobRef: 'sensitivity:exp:42'
});
assert.deepEqual(
  cleanedViewState,
  {
    type: 'sensitivity',
    mode: 'view',
    baselineRunId: '',
    comparisonRunId: '',
    experimentId: 'exp:42',
    jobRef: ''
  },
  'Expected sensitivity view state to keep only experimentId.'
);

const cleanedManualViewState = normaliseExperimentRouteState({
  type: 'manual',
  mode: 'view',
  baselineRunId: 'v0-output',
  comparisonRunId: 'v0-output',
  experimentId: 'exp:42',
  jobRef: 'manual:job-1'
});
assert.deepEqual(
  cleanedManualViewState,
  {
    type: 'manual',
    mode: 'view',
    baselineRunId: 'v0-output',
    comparisonRunId: '',
    experimentId: '',
    jobRef: ''
  },
  'Expected manual view state to drop duplicate comparison ids and incompatible params.'
);

const encodedExperimentQuery = buildExperimentSearchParams(cleanedViewState).toString();
assert.equal(
  encodedExperimentQuery,
  'type=sensitivity&mode=view&experimentId=exp%3A42',
  'Expected deterministic encoding for experiment route deep links.'
);

const encodedManualExperimentQuery = buildExperimentSearchParams({
  type: 'manual',
  mode: 'view',
  baselineRunId: 'v0-output',
  comparisonRunId: 'v4.0-output',
  experimentId: '',
  jobRef: ''
}).toString();
assert.equal(
  encodedManualExperimentQuery,
  'type=manual&mode=view&baselineRunId=v0-output&comparisonRunId=v4.0-output',
  'Expected deterministic encoding for manual baseline/comparison deep links.'
);

function writeSizedFile(filePath: string, sizeBytes: number): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, Buffer.alloc(sizeBytes, 0));
}

class FakeModelProcess extends EventEmitter {
  stdout = new PassThrough();
  stderr = new PassThrough();
  private rejectSigterm = false;

  kill(signal: NodeJS.Signals = 'SIGTERM'): boolean {
    if (signal === 'SIGTERM' && this.rejectSigterm) {
      return false;
    }
    setTimeout(() => {
      this.emit('close', signal === 'SIGTERM' ? null : 1, signal);
    }, 0);
    return true;
  }

  disableSigtermDelivery(): void {
    this.rejectSigterm = true;
  }

  emitStdout(line: string): void {
    this.stdout.write(`${line}\n`);
  }

  emitStderr(line: string): void {
    this.stderr.write(`${line}\n`);
  }

  succeed(): void {
    this.emit('close', 0, null);
  }

  fail(): void {
    this.emit('close', 1, null);
  }
}

const expectedIds = [
  'income_given_age_joint',
  'wealth_given_income_joint',
  'age_distribution',
  'uk_housing_stock_totals',
  'household_consumption_fractions',
  'btl_probability_bins',
  'national_insurance_rates',
  'income_tax_rates',
  'government_allowance_support',
  'house_price_lognormal',
  'rental_price_lognormal',
  'desired_rent_power',
  'hpa_expectation_params',
  'hold_period_years',
  'initial_sale_markup_distribution',
  'price_reduction_probabilities',
  'sale_reduction_gaussian',
  'tenancy_length_range',
  'initial_rent_markup_distribution',
  'rent_reduction_gaussian',
  'bidup_multiplier',
  'rent_gross_yield',
  'market_average_price_decay',
  'mortgage_duration_years',
  'downpayment_ftb_lognormal',
  'downpayment_oo_lognormal',
  'downpayment_btl_profile',
  'buy_quad',
  'bank_rate_credit_response',
  'bank_ltv_limits',
  'bank_lti_limits',
  'bank_affordability_icr_limits',
  'btl_strategy_split'
];

const unchangedNewlyAddedIds = [
  'initial_sale_markup_distribution',
  'price_reduction_probabilities',
  'sale_reduction_gaussian',
  'tenancy_length_range',
  'initial_rent_markup_distribution',
  'rent_reduction_gaussian',
  'bidup_multiplier',
  'rent_gross_yield',
  'downpayment_btl_profile',
  'bank_lti_limits',
] as const;

const RESULTS_ROW_COUNT = 2001;

const RESULTS_CORE_FILE_NAMES = [
  'coreIndicator-ooLTV.csv',
  'coreIndicator-ooLTI.csv',
  'coreIndicator-btlLTV.csv',
  'coreIndicator-creditGrowth.csv',
  'coreIndicator-debtToIncome.csv',
  'coreIndicator-ooDebtToIncome.csv',
  'coreIndicator-mortgageApprovals.csv',
  'coreIndicator-housingTransactions.csv',
  'coreIndicator-advancesToFTB.csv',
  'coreIndicator-advancesToBTL.csv',
  'coreIndicator-advancesToHM.csv',
  'coreIndicator-housePriceGrowth.csv',
  'coreIndicator-priceToIncome.csv',
  'coreIndicator-rentalYield.csv',
  'coreIndicator-interestRateSpread.csv'
] as const;

const RESULTS_OUTPUT_COLUMNS = [
  'Model time',
  'nHomeless',
  'nRenting',
  'nOwnerOccupier',
  'nActiveBTL',
  'Sale HPI',
  'Sale AvSalePrice',
  'Sale AvMonthsOnMarket',
  'Rental HPI',
  'Rental AvSalePrice',
  'Rental AvMonthsOnMarket',
  'creditStock',
  'interestRate'
] as const;

interface ResultsFixtureRunIds {
  complete: string;
  emptyOutput: string;
  sparseCore: string;
  noConfig: string;
}

interface ResultsFixtureContext {
  root: string;
  runIds: ResultsFixtureRunIds;
}

interface ResultsFixtureRunOptions {
  runId: string;
  outputMode: 'full' | 'empty';
  includeConfig: boolean;
  includeTransactionFile: boolean;
  microSnapshotFiles?: string[];
  emptyCoreFiles?: Set<string>;
  modifiedAtMs: number;
}

function buildOutputCsv(rowCount: number): string {
  const lines = [RESULTS_OUTPUT_COLUMNS.join(';')];
  for (let modelTime = 0; modelTime < rowCount; modelTime += 1) {
    lines.push(
      [
        String(modelTime),
        String(90 + (modelTime % 13)),
        String(800 + modelTime),
        String(700 + (modelTime % 17)),
        String(120 + (modelTime % 7)),
        String(100 + (modelTime % 37)),
        String(220000 + modelTime * 25),
        (2 + (modelTime % 12) / 10).toFixed(2),
        String(95 + (modelTime % 31)),
        (1250 + modelTime * 0.45).toFixed(2),
        (1 + (modelTime % 8) / 10).toFixed(2),
        String(1_000_000 + modelTime * 1200),
        (0.01 + (modelTime % 24) / 10_000).toFixed(4)
      ].join(';')
    );
  }
  return `${lines.join('\n')}\n`;
}

function buildCoreCsv(seed: number, rowCount: number): string {
  const values: string[] = [];
  for (let index = 0; index < rowCount; index += 1) {
    values.push(String(seed + (index % 9) + index * 0.01));
  }
  return `${values.join(';')}\n`;
}

function writeSensitivityCoreOutputs(outputPath: string, parameterValue: number): void {
  fs.mkdirSync(outputPath, { recursive: true });
  for (let index = 0; index < RESULTS_CORE_FILE_NAMES.length; index += 1) {
    const base = parameterValue * 10_000 + (index + 1) * 10;
    const values: string[] = [];
    for (let offset = 0; offset < 240; offset += 1) {
      values.push(String(base + offset * 0.01));
    }
    fs.writeFileSync(path.join(outputPath, RESULTS_CORE_FILE_NAMES[index]), `${values.join(';')}\n`, 'utf-8');
  }
}

function writeResultsFixtureRun(resultsRoot: string, options: ResultsFixtureRunOptions): void {
  const runPath = path.join(resultsRoot, options.runId);
  fs.mkdirSync(runPath, { recursive: true });

  if (options.outputMode === 'full') {
    fs.writeFileSync(path.join(runPath, 'Output-run1.csv'), buildOutputCsv(RESULTS_ROW_COUNT), 'utf-8');
  } else {
    fs.writeFileSync(path.join(runPath, 'Output-run1.csv'), '', 'utf-8');
  }

  for (let index = 0; index < RESULTS_CORE_FILE_NAMES.length; index += 1) {
    const fileName = RESULTS_CORE_FILE_NAMES[index];
    const content =
      options.emptyCoreFiles?.has(fileName) === true ? '' : buildCoreCsv((index + 1) * 100, RESULTS_ROW_COUNT);
    fs.writeFileSync(path.join(runPath, fileName), content, 'utf-8');
  }

  if (options.includeConfig) {
    fs.writeFileSync(path.join(runPath, 'config.properties'), 'SEED=42\n', 'utf-8');
  }

  if (options.includeTransactionFile) {
    fs.writeFileSync(path.join(runPath, 'RentalTransactions-run1.csv'), 'modelTime;price\n0;1000\n', 'utf-8');
  }

  for (const fileName of options.microSnapshotFiles ?? []) {
    fs.writeFileSync(path.join(runPath, fileName), 'modelTime;value\n0;1\n', 'utf-8');
  }

  const modifiedAt = new Date(options.modifiedAtMs);
  fs.utimesSync(runPath, modifiedAt, modifiedAt);
}

function createResultsFixtureRepo(): ResultsFixtureContext {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dashboard-results-smoke-'));
  const resultsRoot = path.join(root, 'Results');
  fs.mkdirSync(resultsRoot, { recursive: true });

  const runIds: ResultsFixtureRunIds = {
    complete: 'fixture-complete-output',
    emptyOutput: 'fixture-empty-output',
    sparseCore: 'fixture-sparse-core-output',
    noConfig: 'fixture-no-config-output'
  };

  const baseTime = Date.now();
  writeResultsFixtureRun(resultsRoot, {
    runId: runIds.complete,
    outputMode: 'full',
    includeConfig: true,
    includeTransactionFile: true,
    microSnapshotFiles: [
      'TotalDebt-run2.csv',
      'HousingStatus-run2.csv',
      'NonHousingConsumption-run2.csv'
    ],
    modifiedAtMs: baseTime + 4000
  });
  writeResultsFixtureRun(resultsRoot, {
    runId: runIds.noConfig,
    outputMode: 'full',
    includeConfig: false,
    includeTransactionFile: false,
    modifiedAtMs: baseTime + 3000
  });
  writeResultsFixtureRun(resultsRoot, {
    runId: runIds.emptyOutput,
    outputMode: 'empty',
    includeConfig: true,
    includeTransactionFile: false,
    modifiedAtMs: baseTime + 2000
  });
  writeResultsFixtureRun(resultsRoot, {
    runId: runIds.sparseCore,
    outputMode: 'full',
    includeConfig: true,
    includeTransactionFile: false,
    emptyCoreFiles: new Set(['coreIndicator-mortgageApprovals.csv']),
    modifiedAtMs: baseTime + 1000
  });

  return { root, runIds };
}

function buildModelRunConfigText(baseSeed: number): string {
  return `SEED = ${baseSeed}
N_STEPS = 2000
N_SIMS = 1
TARGET_POPULATION = 10000
TIME_TO_START_RECORDING_TRANSACTIONS = 1000
ROLLING_WINDOW_SIZE_FOR_CORE_INDICATORS = 6
CUMULATIVE_WEIGHT_BEYOND_YEAR = 0.25
recordTransactions = true
recordNBidUpFrequency = false
recordCoreIndicators = true
recordQualityBandPrice = false
recordHouseholdID = true
recordEmploymentIncome = true
recordRentalIncome = true
recordBankBalance = true
recordHousingWealth = true
recordTotalDebt = false
recordHousingStatus = false
recordConsumption = false
recordNHousesOwned = true
recordAge = true
recordSavingRate = false
CENTRAL_BANK_INITIAL_BASE_RATE = 0.005
CENTRAL_BANK_LTV_HARD_MAX_FTB = 0.95
CENTRAL_BANK_LTV_HARD_MAX_HM = 0.9
CENTRAL_BANK_LTV_HARD_MAX_BTL = 0.8
CENTRAL_BANK_LTI_SOFT_MAX_FTB = 5.4
CENTRAL_BANK_LTI_SOFT_MAX_HM = 5.6
CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB = 0.15
CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM = 0.15
CENTRAL_BANK_LTI_MONTHS_TO_CHECK = 12
CENTRAL_BANK_AFFORDABILITY_HARD_MAX = 0.4
CENTRAL_BANK_ICR_HARD_MIN = 1.2
DATA_AGE_DISTRIBUTION = "src/main/resources/Age.csv"
DATA_INCOME_GIVEN_AGE = "src/main/resources/Income.csv"
`;
}

function createModelRunFixtureRepo(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dashboard-model-runs-smoke-'));
  const inputDataRoot = path.join(root, 'input-data-versions');
  const resultsRoot = path.join(root, 'Results');
  fs.mkdirSync(inputDataRoot, { recursive: true });
  fs.mkdirSync(resultsRoot, { recursive: true });

  const baselines = ['v1.0', 'v1.1'];
  baselines.forEach((baseline, index) => {
    const baselinePath = path.join(inputDataRoot, baseline);
    fs.mkdirSync(baselinePath, { recursive: true });
    fs.writeFileSync(path.join(baselinePath, 'config.properties'), buildModelRunConfigText(index + 1), 'utf-8');
    fs.writeFileSync(path.join(baselinePath, 'Age.csv'), '0,10,0.1\n', 'utf-8');
    fs.writeFileSync(path.join(baselinePath, 'Income.csv'), '0,10,0.1\n', 'utf-8');
  });

  const dashboardInputVersionHistory = {
    author: 'smoke-test',
    schema_version: 1,
    description: 'fixture',
    entries: [
      {
        version_id: 'v1.1',
        snapshot_folder: 'v1.1',
        validation_dataset: 'R8',
        description: 'fixture in-progress snapshot',
        updated_data_sources: [],
        calibration_files: [],
        config_parameters: [],
        parameter_changes: [],
        method_variations: [],
        validation: {
          status: 'in_progress',
          income_diff_pct: null,
          housing_wealth_diff_pct: null,
          financial_wealth_diff_pct: null
        }
      }
    ]
  };

  fs.writeFileSync(
    path.join(inputDataRoot, 'dashboard-input-version-history.json'),
    JSON.stringify(dashboardInputVersionHistory, null, 2),
    'utf-8'
  );
  return root;
}

const catalog = getParameterCatalog();
assert.deepEqual(
  catalog.map((item) => item.id),
  expectedIds,
  'Catalog should contain exactly all tracked calibrated parameter cards'
);

assertAxisSpecComplete(expectedIds);
for (const id of expectedIds) {
  const spec = getAxisSpec(id);
  const labels = [
    spec.scalar.xTitle,
    spec.scalar.yTitle,
    spec.binned.xTitle,
    spec.binned.yTitle,
    spec.binned.yDeltaTitle,
    spec.joint.xTitle,
    spec.joint.yTitle,
    spec.joint.legendTitle,
    spec.curve.xTitle,
    spec.curve.yTitle,
    spec.buyBudget.xTitle,
    spec.buyBudget.yTitle,
    spec.buyMultiplier.xTitle,
    spec.buyMultiplier.yTitle
  ];
  for (const label of labels) {
    assert.ok(/\(.+\)/.test(label), `Axis label should include unit marker: ${id} -> ${label}`);
    assert.ok(!label.toLowerCase().includes('native units'), `Axis label should not use native units placeholder: ${id}`);
  }
}

const versions = getVersions(repoRoot);
assert.ok(versions.length > 0, 'Expected at least one version folder');
assert.ok(!versions.includes('v1'), 'v1 should be excluded after cleanup');
assert.equal(versions[0], 'v0', 'Oldest version should be v0');
const inProgressVersions = getInProgressVersions(repoRoot);
assert.ok(
  inProgressVersions.every((version) => versions.includes(version)),
  'In-progress versions should resolve to discovered snapshot folders'
);
assert.ok(!inProgressVersions.includes('v4.0'), 'Expected v4.0 to be reported as a stable snapshot');
assert.ok(!inProgressVersions.includes('v4.1'), 'Expected v4.1 to be reported as a stable snapshot after validation refresh');
const latestStableVersion = getLatestStableVersion(versions, inProgressVersions);
const expectedLatestStableVersion = [...versions].reverse().find((version) => !inProgressVersions.includes(version)) ?? '';
assert.equal(latestStableVersion, expectedLatestStableVersion, 'Expected latest stable version helper to return newest non-progress snapshot');
assert.notEqual(latestStableVersion, '', 'Expected at least one stable version to exist');
const originalVersionState = buildVersionLabelState('v0', latestStableVersion, new Set(inProgressVersions));
assert.ok(originalVersionState.isOriginal, 'Expected v0 to be labelled as original');
assert.equal(formatVersionOptionLabel('v0', originalVersionState), 'v0 (Original)', 'Expected v0 select label to include Original');
const combinedLabelState = buildVersionLabelState('v0', 'v0', new Set<string>());
assert.equal(
  formatVersionOptionLabel('v0', combinedLabelState),
  'v0 (Latest, Original)',
  'Expected combined labels to preserve Latest then Original ordering'
);
const latestVersionState = buildVersionLabelState(latestStableVersion, latestStableVersion, new Set(inProgressVersions));
assert.ok(latestVersionState.isLatest, 'Expected latest stable version to be labelled as latest');
assert.ok(!latestVersionState.isInProgress, 'Expected latest stable version to exclude the in-progress label');
assert.equal(
  formatVersionOptionLabel(latestStableVersion, latestVersionState),
  `${latestStableVersion} (Latest)`,
  'Expected latest stable select label to include Latest'
);
const inProgressVersion = inProgressVersions.find((version) => version !== 'v0');
if (inProgressVersion) {
  const inProgressState = buildVersionLabelState(inProgressVersion, latestStableVersion, new Set(inProgressVersions));
  assert.ok(inProgressState.isInProgress, 'Expected in-progress snapshot to be labelled in progress');
  assert.ok(!inProgressState.isLatest, 'Expected in-progress snapshot not to be labelled latest');
  assert.equal(
    formatVersionOptionLabel(inProgressVersion, inProgressState),
    `${inProgressVersion} (In progress)`,
    'Expected in-progress select label to exclude Latest'
  );
}
const latestVersion = versions[versions.length - 1];

const homePreview = getHomePreview(repoRoot, latestVersion, [
  'wealth_given_income_joint',
  'house_price_lognormal',
  'downpayment_oo_lognormal',
  'btl_probability_bins'
]);
assert.equal(homePreview.version, latestVersion, 'Expected home preview payload to report the requested version');
assert.equal(homePreview.items.length, 4, 'Expected home preview payload to include the requested items only');
assert.deepEqual(
  homePreview.items.map((item) => item.id),
  ['wealth_given_income_joint', 'house_price_lognormal', 'downpayment_oo_lognormal', 'btl_probability_bins'],
  'Expected home preview payload to preserve requested item order'
);
assert.ok(
  homePreview.items.every((item) => !('sourceInfo' in item) && !('changeOriginsInRange' in item)),
  'Expected home preview payload to exclude compare-page provenance and source metadata'
);
const homePreviewLognormal = homePreview.items.find((item) => item.id === 'house_price_lognormal');
assert.ok(homePreviewLognormal, 'Expected house_price_lognormal in home preview payload');
assert.ok(
  homePreviewLognormal?.visualPayload.type === 'lognormal_pair',
  'Expected house_price_lognormal preview payload to use lognormal_pair type'
);
if (homePreviewLognormal?.visualPayload.type === 'lognormal_pair') {
  const scaleRight = homePreviewLognormal.visualPayload.parameters.find((row) => row.key === 'HOUSE_PRICES_SCALE')?.right;
  assert.ok(scaleRight !== undefined, 'Expected house-price scale parameter in preview payload');
  assertClose(
    homePreviewLognormal.visualPayload.median.right,
    Math.exp(Number(scaleRight)),
    1e-12,
    'Expected lognormal preview median.right to equal exp(HOUSE_PRICES_SCALE)'
  );
}

const dashboardInputVersionHistory = loadDashboardInputVersionHistory(repoRoot);
assert.ok(
  dashboardInputVersionHistory.length > 0,
  'Expected at least one dashboard input version history entry'
);
for (const entry of dashboardInputVersionHistory) {
  assert.ok(Array.isArray(entry.calibration_files), 'calibration_files should be present for every version entry');
  assert.ok(Array.isArray(entry.config_parameters), 'config_parameters should be present for every version entry');
  assert.ok(Array.isArray(entry.parameter_changes), 'parameter_changes should be present for every version entry');
  for (const parameterChange of entry.parameter_changes) {
    assert.equal(typeof parameterChange.config_parameter, 'string', 'parameter_changes.config_parameter should be a string');
    assert.ok(
      parameterChange.dataset_source === null || typeof parameterChange.dataset_source === 'string',
      'parameter_changes.dataset_source should be string or null'
    );
  }
  assert.ok(Array.isArray(entry.method_variations), 'method_variations should be present for every version entry');
}
const v10Note = dashboardInputVersionHistory.find((entry) => entry.version_id === 'v1.0');
assert.ok(v10Note, 'Expected v1.0 note entry');
assert.ok(
  v10Note?.parameter_changes.some(
    (change) =>
      change.config_parameter === 'DATA_INCOME_GIVEN_AGE' &&
      change.dataset_source === 'src/main/resources/AgeGrossIncomeJointDist.csv'
  ),
  'Expected v1.0 parameter_changes to include DATA_INCOME_GIVEN_AGE dataset source'
);
const v38Note = dashboardInputVersionHistory.find((entry) => entry.version_id === 'v4.0');
assert.ok(v38Note, 'Expected v4.0 note entry');
assert.equal(v38Note?.validation.status, 'complete', 'v4.0 validation should be complete');
assert.equal(v38Note?.validation.income_diff_pct, 7.192856, 'v4.0 income diff should match released value');
assert.equal(v38Note?.validation.housing_wealth_diff_pct, 12.534289, 'v4.0 housing diff should match released value');
assert.equal(v38Note?.validation.financial_wealth_diff_pct, 13.438086, 'v4.0 financial diff should match released value');

const validationOverview = getValidationOverview(repoRoot, 'v4.1');
assert.equal(validationOverview.selectedVersion, 'v4.1');
assert.ok(validationOverview.trend.points.length > 0);
assert.ok(validationOverview.selectedSummary.metrics.some((metric) => metric.metricId === 'core_mortgageApprovals'));
assert.equal(
  validationOverview.selectedSummary.validationTargetYear,
  2024,
  'Selected non-v0 validation summaries should default the target year to 2024 when metadata is absent'
);
assert.equal(
  Object.prototype.hasOwnProperty.call(validationOverview.selectedSummary, 'familySummaries'),
  false,
  'Validation overview should no longer expose family summaries in the dashboard payload'
);
assert.ok(
  validationOverview.trend.points.some((point) => point.version === 'v0' && point.validationTargetYear === 2024),
  'Validation overview trend should keep v0 on the tracked 2024 summary'
);
assert.ok(
  validationOverview.trend.points.some((point) => point.version === 'v4.1' && point.validationTargetYear === 2024),
  'Validation overview trend should keep later versions on 2024 targets by default'
);
const originalValidationOverview = getValidationOverview(repoRoot, 'v0');
assert.equal(
  originalValidationOverview.selectedSummary.validationTargetYear,
  2024,
  'Selecting v0 should keep the metric table on the tracked 2024 summary'
);
const referenceValidationOverview = getValidationOverview(repoRoot, 'v4.1', 'reference_2011');
assert.equal(referenceValidationOverview.selectedVersion, 'v4.1');
assert.equal(
  referenceValidationOverview.selectedSummary.version,
  'v0-2011',
  'Reference validation mode should surface the separate v0-2011 summary as the selected table'
);
assert.equal(
  referenceValidationOverview.selectedSummary.validationTargetYear,
  2011,
  'Reference validation mode should keep the summary table on the 2011 target year'
);
assert.equal(
  referenceValidationOverview.selectedSummary.metrics.find((metric) => metric.metricId === 'core_hpiStd')?.bandNotes,
  'Intentionally benchmarked to the same official UK IndexSA population std over 2005-01 through 2024-12 used by the tracked 2024 view; this 2011 reference summary only changes the displayed comparison window.',
  'The 2011 validation reference summary should explain that core_hpiStd stays benchmarked to the 2024 std window'
);
assert.equal(
  referenceValidationOverview.selectedSummary.metrics.find((metric) => metric.metricId === 'core_hpiCyclePeriod')?.bandNotes,
  'Still 2011-anchored: derived from the tracked official-source UK HPI history through 2011-12 using the locked 12-month moving-average, log-detrend, FFT peak-search method over 60..240 months.',
  'The 2011 validation reference summary should explain that core_hpiCyclePeriod remains 2011-anchored'
);
assert.ok(
  referenceValidationOverview.trend.points.some((point) => point.version === 'v4.1' && point.validationTargetYear === 2024),
  'Reference validation mode should keep the trend chart on the tracked 2024 timeline'
);
assert.equal(
  readValidationSummary(repoRoot, 'v0').validationTargetYear,
  2024,
  'Validation parser should normalise legacy v0 tracked summaries onto the 2024 timeline'
);

const versionOrder = new Map(versions.map((version, index) => [version, index]));
for (let index = 1; index < validationOverview.trend.points.length; index += 1) {
  const previousVersion = validationOverview.trend.points[index - 1]?.version ?? '';
  const currentVersion = validationOverview.trend.points[index]?.version ?? '';
  const previousRank = versionOrder.get(previousVersion);
  const currentRank = versionOrder.get(currentVersion);
  assert.ok(previousRank !== undefined && currentRank !== undefined, 'Validation trend points should map to known versions');
  assert.ok(previousRank < currentRank, 'Validation trend points should be sorted by version');
}

const validationSummaryDir = path.join(repoRoot, 'input-data-versions', 'validation');
const expectedTrendVersions = fs
  .readdirSync(validationSummaryDir, { withFileTypes: true })
  .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
  .map((entry) => entry.name.replace(/\.json$/u, ''))
  .filter((version) => versionOrder.has(version))
  .sort((left, right) => (versionOrder.get(left) ?? -1) - (versionOrder.get(right) ?? -1));
assert.deepEqual(
  validationOverview.trend.points.map((point) => point.version),
  expectedTrendVersions,
  'Validation overview trend versions should match tracked validation summaries'
);

assert.ok(
  validationOverview.trend.points.every(
    (point) => typeof point.overallCompositeLoss === 'number' && Number.isFinite(point.overallCompositeLoss)
  ),
  'Validation overview trend should expose numeric composite losses for every tracked summary'
);

const approvalsMetric = validationOverview.selectedSummary.metrics.find(
  (metric) => metric.metricId === 'core_mortgageApprovals'
);
const referenceApprovalsMetric = referenceValidationOverview.selectedSummary.metrics.find(
  (metric) => metric.metricId === 'core_mortgageApprovals'
);
assert.ok(approvalsMetric, 'Validation overview should include the mortgage approvals metric');
assert.ok(referenceApprovalsMetric, 'Reference validation overview should include the mortgage approvals metric');
assert.ok(
  approvalsMetric?.targetBand && approvalsMetric.targetBand.lower < approvalsMetric.targetBand.upper,
  'Mortgage approvals should expose a valid target band'
);
assert.ok(
  approvalsMetric?.insideRate !== null && approvalsMetric.insideRate !== undefined,
  'Mortgage approvals should expose an inside-rate summary'
);
assert.equal(approvalsMetric?.metricWeight, 1, 'Mortgage approvals should expose the raw metric weight');
assertClose(
  approvalsMetric?.lossDeltaVsReference2011 ?? NaN,
  (approvalsMetric?.metricLoss ?? NaN) - (referenceApprovalsMetric?.metricLoss ?? NaN),
  1e-12,
  'Mortgage approvals should expose the signed loss delta versus the v0-2011 reference'
);
assert.equal(
  Object.prototype.hasOwnProperty.call(approvalsMetric ?? {}, 'familyId'),
  false,
  'Validation overview metrics should no longer expose family ids in the dashboard payload'
);
assert.ok(
  validationOverview.selectedSummary.metrics.every(
    (metric) => typeof metric.metricWeight === 'number' && Number.isFinite(metric.metricWeight)
  ),
  'Validation overview should expose numeric metric weights for every validation metric'
);
assert.ok(
  validationOverview.selectedSummary.metrics.every((metric) =>
    Object.prototype.hasOwnProperty.call(metric, 'lossDeltaVsReference2011')
  ),
  'Validation overview should expose a per-metric loss delta versus the v0-2011 reference summary'
);
assert.ok(
  referenceValidationOverview.selectedSummary.metrics.every(
    (metric) => metric.lossDeltaVsReference2011 === 0 || metric.lossDeltaVsReference2011 === null
  ),
  'Reference validation mode should expose zero loss deltas when the selected table is the v0-2011 baseline'
);

const validationSummaryFixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'validation-summary-'));
const validationSummaryFixtureDir = path.join(validationSummaryFixtureRoot, 'input-data-versions', 'validation');
const validationOverlayFixtureDir = path.join(validationSummaryFixtureRoot, 'input-data-versions', 'validation-overlays');
fs.mkdirSync(validationSummaryFixtureDir, { recursive: true });
fs.mkdirSync(validationOverlayFixtureDir, { recursive: true });
fs.writeFileSync(
  path.join(validationSummaryFixtureDir, 'v-modern.json'),
  JSON.stringify(
    {
      schemaVersion: 2,
      version: 'v-modern',
      generatedAt: '2026-04-14T00:00:00Z',
      seeds: [1, 2, 3, 4, 5, 6, 7, 8],
      window: { startIndex: 200, endIndex: 2000 },
      overallCompositeLoss: 0.5,
      metrics: [
        {
          metricId: 'core_advancesToBTL',
          label: 'Advances to BTL',
          status: 'fail',
          requirement: 'required',
          units: 'count/month',
          sourceLabel: 'UK Finance BTL Mortgage Market Update 2024 (Q1-Q4)',
          sourceIndicatorLabel: 'House purchase BTL loans, annual sum of 2024 quarterly counts',
          sourceDocumentPath: 'input-data-versions/validation-sources/2024/ukf/Buy to let Mortgage Market Update Q4.pdf',
          sourceTextPath: 'input-data-versions/validation-sources/2024/ukf/btl-mortgage-market-update-2024-validation-evidence.txt',
          sourceTable: '2024 house-purchase BTL counts aggregated from Q1-Q4 summary panels',
          sourcePage: 2,
          rawSourceValue: 62055,
          sourceValue: 5.17125,
          sourceAsOf: '2024 annualized monthly mean',
          sourceUnits: 'count/year',
          comparisonUnits: 'thousand count/month',
          mappingStatus: 'derived_match',
          bandMethod: 'fixed_plus_minus_15pct_around_official_monthly_mean',
          bandNotes: 'Quarterly house-purchase counts converted to a monthly mean.',
          sourceReferences: [
            {
              label: 'UK Finance BTL Mortgage Market Update Q1 2024',
              sourceDocumentPath: 'input-data-versions/validation-sources/2024/ukf/Buy to let Mortgage Market Update Q1.pdf',
              sourceTextPath: 'input-data-versions/validation-sources/2024/ukf/btl-mortgage-market-update-2024-validation-evidence.txt',
              sourceTable: 'Latest 2024 Q1 summary panel',
              sourcePage: 2,
              sourceIndicatorLabel: 'House purchase',
              rawSourceValue: 12422,
              sourceAsOf: 'Q1 2024',
              sourceUnits: 'count/quarter',
              notes: 'Quarterly house-purchase BTL count used in the 2024 annual sum.'
            }
          ],
          targetBand: { lower: 4.396, upper: 5.947 },
          seedMean: 9.0,
          p25: 8.8,
          p75: 9.2,
          insideRate: 0,
          lossScale: 5.17125,
          lossScaleBasis: 'source_value',
          normalizedDistance: 0.590878521852958,
          normalizedIqr: 0.077351898525006,
          metricLoss: 1.5,
          metricWeight: 1
        }
      ]
    },
    null,
    2
  )
);
fs.writeFileSync(
  path.join(validationSummaryFixtureDir, 'v-legacy.json'),
  JSON.stringify(
    {
      schemaVersion: 1,
      version: 'v-legacy',
      generatedAt: '2026-04-14T00:00:00Z',
      seeds: [1, 2, 3, 4, 5, 6, 7, 8],
      window: { startIndex: 200, endIndex: 2000 },
      overallCompositeLoss: 0.5,
      metrics: [
        {
          metricId: 'core_mortgageApprovals',
          label: 'Mortgage Approvals',
          status: 'fail',
          requirement: 'required',
          units: 'count/month',
          sourceLabel: 'Bank of England FPC core indicators, June 2024',
          targetBand: { lower: 57, upper: 63 },
          seedMean: 50,
          p25: 49,
          p75: 51,
          insideRate: 0,
          normalizedDistance: 1.0,
          normalizedIqr: 0.1,
          metricLoss: 1.5
        }
      ]
    },
    null,
    2
  )
);
fs.writeFileSync(
  path.join(validationSummaryFixtureDir, 'v0.json'),
  JSON.stringify(
    {
      schemaVersion: 3,
      version: 'v0',
      validationTargetYear: 2011,
      generatedAt: '2026-04-14T00:00:00Z',
      seeds: [1, 2, 3, 4, 5, 6, 7, 8],
      window: { startIndex: 200, endIndex: 2000 },
      overallCompositeLoss: 0.5,
      metrics: [
        {
          metricId: 'core_mortgageApprovals',
          label: 'Mortgage Approvals',
          status: 'fail',
          requirement: 'required',
          units: 'count/month',
          sourceLabel: 'Bank of England FPC core indicators, June 2024',
          targetBand: { lower: 57, upper: 63 },
          seedMean: 50,
          p25: 49,
          p75: 51,
          insideRate: 0,
          normalizedDistance: 1.0,
          normalizedIqr: 0.1,
          metricLoss: 1.5
        }
      ]
    },
    null,
    2
  )
);
fs.writeFileSync(
  path.join(validationOverlayFixtureDir, 'v0-2011.json'),
  JSON.stringify(
    {
      schemaVersion: 3,
      version: 'v0',
      validationTargetYear: 2011,
      generatedAt: '2026-04-14T00:00:00Z',
      seeds: [1],
      window: { startIndex: 200, endIndex: 2000 },
      overallCompositeLoss: 0.8,
      metrics: [
        {
          metricId: 'core_mortgageApprovals',
          label: 'Mortgage Approvals',
          status: 'fail',
          requirement: 'required',
          units: 'count/month',
          sourceLabel: '2011 overlay',
          targetBand: { lower: 42, upper: 53 },
          seedMean: 50,
          p25: 50,
          p75: 50,
          insideRate: 1,
          normalizedDistance: 0,
          normalizedIqr: 0,
          metricLoss: 0
        },
        {
          metricId: 'core_housingTransactions',
          label: 'Housing Transactions',
          status: 'fail',
          requirement: 'required',
          units: 'count/month',
          sourceLabel: '2011 overlay',
          targetBand: { lower: 68, upper: 78 },
          seedMean: 74,
          p25: 73,
          p75: 75,
          insideRate: 1,
          normalizedDistance: 0,
          normalizedIqr: 0.02,
          metricLoss: 0.5
        }
      ]
    },
    null,
    2
  )
);
fs.writeFileSync(
  path.join(validationSummaryFixtureDir, 'v4.0.json'),
  JSON.stringify(
    {
      schemaVersion: 3,
      version: 'v4.0',
      generatedAt: '2026-04-14T00:00:00Z',
      seeds: [1, 2, 3, 4, 5, 6, 7, 8],
      window: { startIndex: 200, endIndex: 2000 },
      overallCompositeLoss: 0.4,
      metrics: [
        {
          metricId: 'core_mortgageApprovals',
          label: 'Mortgage Approvals',
          status: 'pass',
          requirement: 'required',
          units: 'count/month',
          sourceLabel: 'Bank of England FPC core indicators, June 2024',
          targetBand: { lower: 57, upper: 63 },
          seedMean: 60,
          p25: 58,
          p75: 62,
          insideRate: 1,
          normalizedDistance: 0.0,
          normalizedIqr: 0.05,
          metricLoss: 0.05
        },
        {
          metricId: 'core_housingTransactions',
          label: 'Housing Transactions',
          status: 'warn',
          requirement: 'required',
          units: 'count/month',
          sourceLabel: 'Bank of England FPC core indicators, June 2024',
          targetBand: { lower: 84, upper: 100 },
          seedMean: 90,
          p25: 88,
          p75: 92,
          insideRate: 0.5,
          normalizedDistance: 0.1,
          normalizedIqr: 0.05,
          metricLoss: 0.2
        }
      ]
    },
    null,
    2
  )
);
const modernSummary = readValidationSummary(validationSummaryFixtureRoot, 'v-modern');
assert.equal(modernSummary.validationTargetYear, 2024, 'Validation parser should default missing target years to 2024');
assert.equal(modernSummary.metrics[0]?.sourceReferences.length ?? 0, 1, 'Validation parser should preserve source references');
assert.equal(modernSummary.metrics[0]?.lossScaleBasis, 'source_value', 'Validation parser should expose loss scale basis');
assert.equal(modernSummary.metrics[0]?.lossScale, 5.17125, 'Validation parser should expose loss scale values');
assert.equal(modernSummary.metrics[0]?.metricWeight, 1, 'Validation parser should expose raw metric weights');
assert.equal(
  modernSummary.metrics[0]?.lossDeltaVsReference2011 ?? null,
  null,
  'Validation parser should default missing loss deltas to null'
);
assert.equal(
  Object.prototype.hasOwnProperty.call(modernSummary.metrics[0] ?? {}, 'familyId'),
  false,
  'Validation parser should ignore removed metric family ids'
);
assert.equal(
  Object.prototype.hasOwnProperty.call(modernSummary, 'familySummaries'),
  false,
  'Validation parser should ignore removed family summaries'
);
assert.equal(
  modernSummary.metrics[0]?.sourceReferences[0]?.sourceDocumentPath,
  'input-data-versions/validation-sources/2024/ukf/Buy to let Mortgage Market Update Q1.pdf',
  'Validation parser should expose source reference document paths'
);
const legacySummary = readValidationSummary(validationSummaryFixtureRoot, 'v-legacy');
assert.equal(
  legacySummary.validationTargetYear,
  2024,
  'Legacy validation summaries should default missing top-level target years to 2024'
);
assert.equal(legacySummary.metrics[0]?.sourceReferences.length ?? 0, 0, 'Validation parser should default missing source references to an empty list');
assert.equal(legacySummary.metrics[0]?.sourceIndicatorLabel ?? null, null, 'Legacy validation summaries should parse without source detail fields');
assert.equal(legacySummary.metrics[0]?.metricWeight, 1, 'Legacy validation summaries should default missing metric weights to 1');
assert.equal(
  legacySummary.metrics[0]?.lossDeltaVsReference2011 ?? null,
  null,
  'Legacy validation summaries should default missing loss deltas to null'
);
const originalFixtureSummary = readValidationSummary(validationSummaryFixtureRoot, 'v0');
assert.equal(
  originalFixtureSummary.validationTargetYear,
  2024,
  'Validation parser should keep legacy v0 tracked summaries on the ordinary 2024 timeline'
);
assert.equal(
  originalFixtureSummary.referenceLine,
  null,
  'Tracked v0 summaries should not need to embed the separate 2011 comparator payload'
);
const overviewWithReferenceLine = getValidationOverview(validationSummaryFixtureRoot, 'v4.0');
assert.equal(
  overviewWithReferenceLine.trend.points.find((point) => point.version === 'v0')?.overallCompositeLoss,
  0.5,
  'Validation overview should keep the tracked v0 point on its own 2024 summary value'
);
assert.equal(
  overviewWithReferenceLine.trend.points.find((point) => point.version === 'v0')?.validationTargetYear,
  2024,
  'Validation overview should keep the tracked v0 point on the 2024 summary timeline'
);
assert.equal(
  overviewWithReferenceLine.trend.referenceLine?.overallCompositeLoss,
  0.8,
  'Validation overview should source the dashed comparator from the separate referenceLine artifact'
);
assert.equal(
  overviewWithReferenceLine.trend.referenceLine?.validationTargetYear,
  2011,
  'Validation overview should keep the dashed comparator on the 2011 reference timeline'
);
assert.equal(
  overviewWithReferenceLine.selectedSummary.metrics.find((metric) => metric.metricId === 'core_mortgageApprovals')
    ?.lossDeltaVsReference2011,
  0.05,
  'Tracked validation summaries should expose positive signed loss deltas when they score worse than v0-2011'
);
assert.equal(
  overviewWithReferenceLine.selectedSummary.metrics.find((metric) => metric.metricId === 'core_housingTransactions')
    ?.lossDeltaVsReference2011,
  -0.3,
  'Tracked validation summaries should expose negative signed loss deltas when they score better than v0-2011'
);
const referenceOverviewWithDeltas = getValidationOverview(validationSummaryFixtureRoot, 'v4.0', 'reference_2011');
assert.ok(
  referenceOverviewWithDeltas.selectedSummary.metrics.every((metric) => metric.lossDeltaVsReference2011 === 0),
  'Reference validation mode should expose zero deltas for every supported v0-2011 baseline metric'
);

const rangeAtSameVersion = compareParameters(repoRoot, 'v4.0', 'v4.0', ['national_insurance_rates'], 'range');
const throughRightAtSameVersion = compareParameters(repoRoot, 'v4.0', 'v4.0', ['national_insurance_rates'], 'through_right');
assert.equal(
  rangeAtSameVersion.items[0]?.changeOriginsInRange.length ?? 0,
  0,
  'range provenance scope should be empty when left and right are the same version'
);
assert.ok(
  (throughRightAtSameVersion.items[0]?.changeOriginsInRange.length ?? 0) > 0,
  'through_right provenance scope should include historical updates through the selected version'
);
assert.ok(
  throughRightAtSameVersion.items[0]?.changeOriginsInRange.some((origin) => origin.versionId === 'v2.0'),
  'through_right provenance should include NI update origin v2.0'
);

const singleBuyQuad = compareParameters(repoRoot, 'v4.0', 'v4.0', ['buy_quad'], 'through_right').items[0];
const buyQuadV38Origin = singleBuyQuad?.changeOriginsInRange.find((origin) => origin.versionId === 'v4.0');
assert.ok(buyQuadV38Origin, 'Expected buy_quad provenance to include v4.0 origin in through_right scope');
assert.ok(singleBuyQuad && singleBuyQuad.visualPayload.type === 'buy_quad', 'Expected buy_quad payload to use buy_quad type');
if (singleBuyQuad && singleBuyQuad.visualPayload.type === 'buy_quad') {
  const muRow = singleBuyQuad.visualPayload.parameters.find((row) => row.key === 'BUY_MU');
  assert.ok(muRow, 'Expected BUY_MU row in buy_quad parameters');
  assert.ok(
    Number.isFinite(singleBuyQuad.visualPayload.medianMultiplier.left) &&
      singleBuyQuad.visualPayload.medianMultiplier.left > 0,
    'Expected buy_quad medianMultiplier.left to be a positive finite number'
  );
  assert.ok(
    Number.isFinite(singleBuyQuad.visualPayload.medianMultiplier.right) &&
      singleBuyQuad.visualPayload.medianMultiplier.right > 0,
    'Expected buy_quad medianMultiplier.right to be a positive finite number'
  );
  assertClose(
    singleBuyQuad.visualPayload.medianMultiplier.right,
    Math.exp(Number(muRow?.right ?? Number.NaN)),
    1e-12,
    'Expected buy_quad medianMultiplier.right to match exp(BUY_MU)'
  );
}
assert.ok(
  (buyQuadV38Origin?.methodVariations.length ?? 0) > 0,
  'Expected buy_quad v4.0 provenance to include method variation notes'
);
assert.ok(
  buyQuadV38Origin?.methodVariations.some((variation) =>
    variation.configParameters.some((parameter) => parameter.startsWith('BUY_'))
  ),
  'Expected at least one method variation scoped to BUY_* parameters'
);
assert.ok(
  buyQuadV38Origin?.parameterChanges.every(
    (change) => !change.configParameter.startsWith('BUY_') || change.datasetSource === null
  ),
  'Expected v4.0 BUY_* parameter changes to have null dataset_source'
);

const compare = compareParameters(repoRoot, 'v0', versions[versions.length - 1], [
  'mortgage_duration_years',
  'house_price_lognormal',
  'desired_rent_power',
  'buy_quad',
  'income_given_age_joint',
  'national_insurance_rates',
  'income_tax_rates',
  'wealth_given_income_joint',
  'age_distribution'
]);

assert.equal(compare.left, 'v0');
assert.equal(compare.items.length, 9);

const formatSet = new Set(compare.items.map((item) => item.format));
assert.ok(formatSet.has('scalar'));
assert.ok(formatSet.has('lognormal_pair'));
assert.ok(formatSet.has('power_law_pair'));
assert.ok(formatSet.has('buy_quad'));
assert.ok(formatSet.has('joint_distribution'));
assert.ok(formatSet.has('binned_distribution'));

const unchangedCards = compareParameters(repoRoot, 'v0', latestVersion, [...unchangedNewlyAddedIds], 'range');
assert.equal(
  unchangedCards.items.length,
  unchangedNewlyAddedIds.length,
  'Expected all unchanged newly added cards in compare payload'
);
for (const item of unchangedCards.items) {
  assert.equal(item.unchanged, true, `Expected newly added card ${item.id} to remain unchanged across versions`);
}

const householdConsumptionCompare = compareParameters(
  repoRoot,
  'v0',
  latestVersion,
  ['household_consumption_fractions'],
  'range'
);
assert.equal(householdConsumptionCompare.items.length, 1, 'Expected household_consumption_fractions compare payload');
assert.equal(
  householdConsumptionCompare.items[0]?.unchanged,
  false,
  'Expected household_consumption_fractions to differ from v0 once the v4.12 LCFS promotion is included'
);
assert.ok(
  householdConsumptionCompare.items[0]?.changeOriginsInRange.some((origin) => origin.versionId === 'v4.12'),
  'Expected household_consumption_fractions provenance to include the v4.12 LCFS promotion'
);

const hpaExpectationCompare = compareParameters(repoRoot, 'v0', latestVersion, ['hpa_expectation_params'], 'range');
assert.equal(hpaExpectationCompare.items.length, 1, 'Expected hpa_expectation_params compare payload');
assert.equal(
  hpaExpectationCompare.items[0]?.unchanged,
  false,
  'Expected hpa_expectation_params to differ from v0 once the v4.2 HPA promotion is included'
);
assert.ok(
  hpaExpectationCompare.items[0]?.changeOriginsInRange.some((origin) => origin.versionId === 'v4.2'),
  'Expected hpa_expectation_params provenance to include the v4.2 HPA promotion'
);
assert.ok(
  hpaExpectationCompare.items[0]?.changeOriginsInRange.some(
    (origin) => origin.versionId === 'v4.2' && origin.validationStatus === 'complete'
  ),
  'Expected hpa_expectation_params provenance to show v4.2 as validation-complete'
);

const bankLtvCompare = compareParameters(repoRoot, 'v0', latestVersion, ['bank_ltv_limits'], 'range');
assert.equal(bankLtvCompare.items.length, 1, 'Expected bank_ltv_limits compare payload');
assert.equal(
  bankLtvCompare.items[0]?.unchanged,
  false,
  'Expected bank_ltv_limits to change in the latest version due to v4.1 cap alignment'
);
assert.ok(
  bankLtvCompare.items[0]?.changeOriginsInRange.some(
    (origin) => origin.versionId === 'v4.1' && origin.validationStatus === 'complete'
  ),
  'Expected bank_ltv_limits provenance to show the v4.1 alignment as validation-complete'
);

const saleMarkup = unchangedCards.items.find((item) => item.id === 'initial_sale_markup_distribution');
assert.ok(
  saleMarkup && saleMarkup.visualPayload.type === 'binned_distribution',
  'Expected initial_sale_markup_distribution card with binned payload'
);
if (saleMarkup && saleMarkup.visualPayload.type === 'binned_distribution') {
  assert.ok(
    saleMarkup.visualPayload.bins.every((bin) => Math.abs(bin.delta) <= 1e-12),
    'Sale mark-up bins should have zero delta across versions'
  );
}

const rentMarkup = unchangedCards.items.find((item) => item.id === 'initial_rent_markup_distribution');
assert.ok(
  rentMarkup && rentMarkup.visualPayload.type === 'binned_distribution',
  'Expected initial_rent_markup_distribution card with binned payload'
);
if (rentMarkup && rentMarkup.visualPayload.type === 'binned_distribution') {
  assert.ok(
    rentMarkup.visualPayload.bins.every((bin) => Math.abs(bin.delta) <= 1e-12),
    'Rent mark-up bins should have zero delta across versions'
  );
}

const unchangedSingleWithProvenance = compareParameters(
  repoRoot,
  latestVersion,
  latestVersion,
  [...unchangedNewlyAddedIds],
  'through_right'
);
for (const item of unchangedSingleWithProvenance.items) {
  assert.equal(
    item.changeOriginsInRange.length,
    0,
    `Expected no provenance origins for newly added card ${item.id} in through_right scope`
  );
}

const reshapedCards = compareParameters(repoRoot, 'v0', latestVersion, [
  'price_reduction_probabilities',
  'sale_reduction_gaussian',
  'rent_reduction_gaussian',
  'hpa_expectation_params'
]);

const priceReductionProbabilities = reshapedCards.items.find((item) => item.id === 'price_reduction_probabilities');
assert.ok(priceReductionProbabilities, 'Expected price_reduction_probabilities card');
assert.equal(priceReductionProbabilities?.format, 'scalar_pair');
assert.deepEqual(priceReductionProbabilities?.sourceInfo.configKeys, ['P_SALE_PRICE_REDUCE', 'P_RENT_PRICE_REDUCE']);

const saleReductionGaussian = reshapedCards.items.find((item) => item.id === 'sale_reduction_gaussian');
assert.ok(saleReductionGaussian, 'Expected sale_reduction_gaussian card');
assert.equal(saleReductionGaussian?.format, 'gaussian_pair');
assert.ok(
  saleReductionGaussian?.visualPayload.type === 'gaussian_pair',
  'Expected gaussian_pair payload for sale_reduction_gaussian'
);
if (saleReductionGaussian?.visualPayload.type === 'gaussian_pair') {
  assert.equal(saleReductionGaussian.visualPayload.percentDomain.max, 50, 'Sale gaussian percent domain max should be 50');
  assert.ok(
    Number.isFinite(saleReductionGaussian.visualPayload.percentCapMassLeft) &&
      saleReductionGaussian.visualPayload.percentCapMassLeft >= 0 &&
      saleReductionGaussian.visualPayload.percentCapMassLeft <= 1,
    'Sale gaussian left cap mass should be a finite probability in [0, 1]'
  );
  assert.ok(
    Number.isFinite(saleReductionGaussian.visualPayload.percentCapMassRight) &&
      saleReductionGaussian.visualPayload.percentCapMassRight >= 0 &&
      saleReductionGaussian.visualPayload.percentCapMassRight <= 1,
    'Sale gaussian right cap mass should be a finite probability in [0, 1]'
  );
  assert.ok(
    saleReductionGaussian.visualPayload.logDomain.min < saleReductionGaussian.visualPayload.logDomain.max,
    'Sale gaussian log domain should be increasing'
  );
  assert.ok(
    saleReductionGaussian.visualPayload.percentDomain.min < saleReductionGaussian.visualPayload.percentDomain.max,
    'Sale gaussian percent domain should be increasing'
  );
  assert.ok(
    saleReductionGaussian.visualPayload.logCurveRight.every(
      (point) => Number.isFinite(point.x) && Number.isFinite(point.y) && point.y >= 0
    ),
    'Sale gaussian log curve should contain finite non-negative densities'
  );
  assert.ok(
    saleReductionGaussian.visualPayload.percentCurveRight.every(
      (point) => Number.isFinite(point.x) && Number.isFinite(point.y) && point.y >= 0 && point.x > 0 && point.x <= 50
    ),
    'Sale gaussian percent curve should contain finite non-negative densities within (0, 50]'
  );

  const muLeft = saleReductionGaussian.visualPayload.parameters.find((row) => row.key === 'REDUCTION_MU')?.left;
  const muRight = saleReductionGaussian.visualPayload.parameters.find((row) => row.key === 'REDUCTION_MU')?.right;
  const sigmaRight = saleReductionGaussian.visualPayload.parameters.find((row) => row.key === 'REDUCTION_SIGMA')?.right;
  assert.ok(muLeft !== undefined, 'Expected sale reduction mu in left parameters');
  assert.ok(muRight !== undefined, 'Expected sale reduction mu in parameters');
  assert.ok(sigmaRight !== undefined && sigmaRight > 0, 'Expected positive sale reduction sigma in parameters');
  assertClose(
    saleReductionGaussian.visualPayload.logMedian.left,
    Number(muLeft),
    1e-12,
    'Expected sale gaussian logMedian.left to match REDUCTION_MU'
  );
  assertClose(
    saleReductionGaussian.visualPayload.logMedian.right,
    Number(muRight),
    1e-12,
    'Expected sale gaussian logMedian.right to match REDUCTION_MU'
  );
  assertClose(
    saleReductionGaussian.visualPayload.percentMedian.left,
    Math.exp(Number(muLeft)),
    1e-12,
    'Expected sale gaussian percentMedian.left to equal exp(REDUCTION_MU)'
  );
  assertClose(
    saleReductionGaussian.visualPayload.percentMedian.right,
    Math.exp(Number(muRight)),
    1e-12,
    'Expected sale gaussian percentMedian.right to equal exp(REDUCTION_MU)'
  );
  const sample = saleReductionGaussian.visualPayload.percentCurveRight[
    Math.floor(saleReductionGaussian.visualPayload.percentCurveRight.length / 2)
  ];
  assert.ok(sample, 'Expected sample point for sale percent curve');
  const expectedDensity = gaussianPercentDensity(sample.x, muRight as number, sigmaRight as number);
  assertClose(sample.y, expectedDensity, 1e-12, 'Sale percent curve should match transformed Gaussian density');
}

const rentReductionGaussian = reshapedCards.items.find((item) => item.id === 'rent_reduction_gaussian');
assert.ok(rentReductionGaussian, 'Expected rent_reduction_gaussian card');
assert.equal(rentReductionGaussian?.format, 'gaussian_pair');
assert.ok(
  rentReductionGaussian?.visualPayload.type === 'gaussian_pair',
  'Expected gaussian_pair payload for rent_reduction_gaussian'
);
if (rentReductionGaussian?.visualPayload.type === 'gaussian_pair') {
  assert.equal(rentReductionGaussian.visualPayload.percentDomain.max, 50, 'Rent gaussian percent domain max should be 50');
  assert.ok(
    Number.isFinite(rentReductionGaussian.visualPayload.percentCapMassLeft) &&
      rentReductionGaussian.visualPayload.percentCapMassLeft >= 0 &&
      rentReductionGaussian.visualPayload.percentCapMassLeft <= 1,
    'Rent gaussian left cap mass should be a finite probability in [0, 1]'
  );
  assert.ok(
    Number.isFinite(rentReductionGaussian.visualPayload.percentCapMassRight) &&
      rentReductionGaussian.visualPayload.percentCapMassRight >= 0 &&
      rentReductionGaussian.visualPayload.percentCapMassRight <= 1,
    'Rent gaussian right cap mass should be a finite probability in [0, 1]'
  );
  assert.ok(
    rentReductionGaussian.visualPayload.logCurveRight.every(
      (point) => Number.isFinite(point.x) && Number.isFinite(point.y) && point.y >= 0
    ),
    'Rent gaussian log curve should contain finite non-negative densities'
  );
  assert.ok(
    rentReductionGaussian.visualPayload.percentCurveRight.every(
      (point) => Number.isFinite(point.x) && Number.isFinite(point.y) && point.y >= 0 && point.x > 0 && point.x <= 50
    ),
    'Rent gaussian percent curve should contain finite non-negative densities within (0, 50]'
  );

  const muLeft = rentReductionGaussian.visualPayload.parameters.find((row) => row.key === 'RENT_REDUCTION_MU')?.left;
  const muRight = rentReductionGaussian.visualPayload.parameters.find((row) => row.key === 'RENT_REDUCTION_MU')?.right;
  const sigmaRight = rentReductionGaussian.visualPayload.parameters.find((row) => row.key === 'RENT_REDUCTION_SIGMA')?.right;
  assert.ok(muLeft !== undefined, 'Expected rent reduction mu in left parameters');
  assert.ok(muRight !== undefined, 'Expected rent reduction mu in parameters');
  assert.ok(sigmaRight !== undefined && sigmaRight > 0, 'Expected positive rent reduction sigma in parameters');
  assertClose(
    rentReductionGaussian.visualPayload.logMedian.left,
    Number(muLeft),
    1e-12,
    'Expected rent gaussian logMedian.left to match RENT_REDUCTION_MU'
  );
  assertClose(
    rentReductionGaussian.visualPayload.logMedian.right,
    Number(muRight),
    1e-12,
    'Expected rent gaussian logMedian.right to match RENT_REDUCTION_MU'
  );
  assertClose(
    rentReductionGaussian.visualPayload.percentMedian.left,
    Math.exp(Number(muLeft)),
    1e-12,
    'Expected rent gaussian percentMedian.left to equal exp(RENT_REDUCTION_MU)'
  );
  assertClose(
    rentReductionGaussian.visualPayload.percentMedian.right,
    Math.exp(Number(muRight)),
    1e-12,
    'Expected rent gaussian percentMedian.right to equal exp(RENT_REDUCTION_MU)'
  );
  const sample = rentReductionGaussian.visualPayload.percentCurveRight[
    Math.floor(rentReductionGaussian.visualPayload.percentCurveRight.length / 2)
  ];
  assert.ok(sample, 'Expected sample point for rent percent curve');
  const expectedDensity = gaussianPercentDensity(sample.x, muRight as number, sigmaRight as number);
  assertClose(sample.y, expectedDensity, 1e-12, 'Rent percent curve should match transformed Gaussian density');
}

const hpaExpectation = reshapedCards.items.find((item) => item.id === 'hpa_expectation_params');
assert.ok(hpaExpectation, 'Expected hpa_expectation_params card');
assert.equal(hpaExpectation?.format, 'hpa_expectation_line');
assert.ok(
  hpaExpectation?.visualPayload.type === 'hpa_expectation_line',
  'Expected hpa_expectation_line payload for hpa_expectation_params'
);
if (hpaExpectation?.visualPayload.type === 'hpa_expectation_line') {
  assert.equal(hpaExpectation.visualPayload.domain.min, -0.2, 'HPA domain min should be -0.2');
  assert.equal(hpaExpectation.visualPayload.domain.max, 0.2, 'HPA domain max should be 0.2');
  assert.equal(hpaExpectation.visualPayload.dt, 1, 'HPA expectation DT should equal 1');

  const factorRight = hpaExpectation.visualPayload.parameters.find((row) => row.key === 'HPA_EXPECTATION_FACTOR')?.right;
  const constRight = hpaExpectation.visualPayload.parameters.find((row) => row.key === 'HPA_EXPECTATION_CONST')?.right;
  assert.ok(factorRight !== undefined, 'Expected HPA factor in parameters');
  assert.ok(constRight !== undefined, 'Expected HPA const in parameters');

  const sample = hpaExpectation.visualPayload.curveRight[Math.floor(hpaExpectation.visualPayload.curveRight.length / 2)];
  assert.ok(sample, 'Expected mid-point sample for HPA curve');
  const expected = (factorRight as number) * sample.x + (constRight as number);
  assertClose(sample.y, expected, 1e-12, 'HPA curve should satisfy y = factor*x + const');
}

for (const item of compare.items) {
  assert.equal(item.leftVersion, 'v0');
  assert.ok(item.sourceInfo.configPathLeft.endsWith('config.properties'));
  assert.ok(item.sourceInfo.configPathRight.endsWith('config.properties'));
  assert.ok(Array.isArray(item.sourceInfo.datasetsLeft), 'datasetsLeft should be present on every compare item');
  assert.ok(Array.isArray(item.sourceInfo.datasetsRight), 'datasetsRight should be present on every compare item');
  assert.ok(Array.isArray(item.changeOriginsInRange), 'changeOriginsInRange should be present on every compare item');
  for (const origin of item.changeOriginsInRange) {
    assert.ok(Array.isArray(origin.parameterChanges), 'parameterChanges should be present on every provenance origin');
    assert.ok(!('validationDataset' in origin), 'validationDataset should not be exposed on compare origins');
  }
}

const ageDist = compare.items.find((item) => item.id === 'age_distribution');
assert.ok(ageDist && ageDist.visualPayload.type === 'binned_distribution');
if (ageDist && ageDist.visualPayload.type === 'binned_distribution') {
  const leftConfig = parseConfigFile(getConfigPath(repoRoot, 'v0'));
  const rightConfig = parseConfigFile(getConfigPath(repoRoot, compare.right));
  const leftRows = readNumericCsvRows(
    resolveConfigDataFilePath(repoRoot, 'v0', leftConfig.get('DATA_AGE_DISTRIBUTION') ?? '')
  );
  const rightRows = readNumericCsvRows(
    resolveConfigDataFilePath(repoRoot, compare.right, rightConfig.get('DATA_AGE_DISTRIBUTION') ?? '')
  );

  const rawLeftMass = sumBinnedDensityMass(leftRows);
  const rawRightMass = sumBinnedDensityMass(rightRows);
  const rebinnedLeftMass = sum(ageDist.visualPayload.bins.map((bin) => bin.left));
  const rebinnedRightMass = sum(ageDist.visualPayload.bins.map((bin) => bin.right));

  assertClose(rebinnedLeftMass, rawLeftMass, 1e-8, '1D density rebin should preserve left mass');
  assertClose(rebinnedRightMass, rawRightMass, 1e-8, '1D density rebin should preserve right mass');
}

const ageDistV411 = compareParameters(repoRoot, 'v0', 'v4.11', ['age_distribution']).items[0];
assert.ok(ageDistV411 && ageDistV411.visualPayload.type === 'binned_distribution');
if (ageDistV411 && ageDistV411.visualPayload.type === 'binned_distribution') {
  const leftConfig = parseConfigFile(getConfigPath(repoRoot, 'v0'));
  const rightConfig = parseConfigFile(getConfigPath(repoRoot, 'v4.11'));
  const leftRows = readNumericCsvRows(
    resolveConfigDataFilePath(repoRoot, 'v0', leftConfig.get('DATA_AGE_DISTRIBUTION') ?? '')
  );
  const rightRows = readNumericCsvRows(
    resolveConfigDataFilePath(repoRoot, 'v4.11', rightConfig.get('DATA_AGE_DISTRIBUTION') ?? '')
  );
  const sourceBins = ageDistV411.visualPayload.sourceBins;
  assert.ok(sourceBins, 'Expected source bins for age_distribution');
  assert.equal(sourceBins.left.length, 8, 'Expected v0 source age distribution to keep 8 bins');
  assert.equal(sourceBins.right.length, 15, 'Expected v4.11 source age distribution to keep 15 bins');
  assert.equal(sourceBins.left.length, leftRows.length, 'Expected v0 source bins to match raw CSV rows');
  assert.equal(sourceBins.right.length, rightRows.length, 'Expected v4.11 source bins to match raw CSV rows');
  assert.equal(sourceBins.left[0]?.lower, 15, 'Expected v0 first age bin lower edge to be preserved');
  assert.equal(sourceBins.left[0]?.upper, 25, 'Expected v0 first age bin upper edge to be preserved');
  assert.equal(sourceBins.right[0]?.lower, 16, 'Expected v4.11 first age bin lower edge to be preserved');
  assert.equal(sourceBins.right[0]?.upper, 20, 'Expected v4.11 first age bin upper edge to be preserved');

  const rawLeftMass = sumBinnedDensityMass(leftRows);
  const rawRightMass = sumBinnedDensityMass(rightRows);
  const rebinnedLeftMass = sum(ageDistV411.visualPayload.bins.map((bin) => bin.left));
  const rebinnedRightMass = sum(ageDistV411.visualPayload.bins.map((bin) => bin.right));
  assertClose(rebinnedLeftMass, rawLeftMass, 1e-8, 'v4.11 age compare should preserve left mass');
  assertClose(rebinnedRightMass, rawRightMass, 1e-8, 'v4.11 age compare should preserve right mass');

  const option = binnedOption(
    ageDistV411,
    'Age band (years)',
    'Household share (-)',
    'Share delta (-)',
    { leftLabel: 'v0 original', rightLabel: 'v4.11 latest' }
  );
  const xAxis = Array.isArray(option.xAxis) ? option.xAxis[0] : option.xAxis;
  assert.equal((xAxis as any)?.type, 'value', 'Unequal source bins should use a numeric x-axis');
  const series = Array.isArray(option.series) ? option.series : [];
  assert.ok(series.every((entry: any) => entry.type === 'custom'), 'Unequal source bins should use interval series');
  assert.equal((series[0] as any)?.data?.length, 8, 'Left interval series should use v0 source bins');
  assert.equal((series[1] as any)?.data?.length, 15, 'Right interval series should use v4.11 source bins');
}

const incomeAgeV40 = compareParameters(repoRoot, 'v0', 'v4.0', ['income_given_age_joint']);
const incomeAge = incomeAgeV40.items.find((item) => item.id === 'income_given_age_joint');
assert.ok(incomeAge && incomeAge.visualPayload.type === 'joint_distribution');
if (incomeAge && incomeAge.visualPayload.type === 'joint_distribution') {
  const xLabels = incomeAge.visualPayload.matrix.xAxis.labels;
  assert.ok(xLabels.includes('75-85'), 'Expected shared age x-bin 75-85');
  assert.ok(xLabels.includes('85-95'), 'Expected shared age x-bin 85-95');
  assert.ok(!xLabels.includes('75-95'), 'Expected no merged 75-95 x-bin in shared grid');

  const leftConfig = parseConfigFile(getConfigPath(repoRoot, 'v0'));
  const rightConfig = parseConfigFile(getConfigPath(repoRoot, 'v4.0'));
  const leftRows = readNumericCsvRows(
    resolveConfigDataFilePath(repoRoot, 'v0', leftConfig.get('DATA_INCOME_GIVEN_AGE') ?? '')
  );
  const rightRows = readNumericCsvRows(
    resolveConfigDataFilePath(repoRoot, 'v4.0', rightConfig.get('DATA_INCOME_GIVEN_AGE') ?? '')
  );

  const rawLeftMass = sum(leftRows.map((row) => row[4]));
  const rawRightMass = sum(rightRows.map((row) => row[4]));
  const rebinnedLeftMass = sum(incomeAge.visualPayload.matrix.left.map((cell) => cell.value));
  const rebinnedRightMass = sum(incomeAge.visualPayload.matrix.right.map((cell) => cell.value));

  assertClose(rebinnedLeftMass, rawLeftMass, 1e-7, '2D rebin should preserve left mass');
  assertClose(rebinnedRightMass, rawRightMass, 1e-7, '2D rebin should preserve right mass');
}

const wealthIncome = compare.items.find((item) => item.id === 'wealth_given_income_joint');
assert.ok(wealthIncome && wealthIncome.visualPayload.type === 'joint_distribution');
if (wealthIncome && wealthIncome.visualPayload.type === 'joint_distribution') {
  assert.ok(
    wealthIncome.visualPayload.matrix.xAxis.labels.some((label) => label.includes('£')),
    'Expected clean level-space labels on wealth/income x axis'
  );
  assert.ok(
    wealthIncome.visualPayload.matrix.yAxis.labels.some((label) => label.includes('£')),
    'Expected clean level-space labels on wealth/income y axis'
  );
}

const niRates = compare.items.find((item) => item.id === 'national_insurance_rates');
assert.ok(niRates && niRates.visualPayload.type === 'binned_distribution', 'Expected NI rates card in compare payload');
if (niRates && niRates.visualPayload.type === 'binned_distribution') {
  assert.equal(niRates.unchanged, false, 'NI thresholds/rates should be changed between v0 and v4.0');
  assert.ok(
    niRates.visualPayload.bins.some((bin) => Math.abs(bin.delta) > 1e-12),
    'At least one NI step-rate bracket should have non-zero delta'
  );
  assert.ok(
    niRates.changeOriginsInRange.some((origin) => origin.versionId === 'v2.0'),
    'NI card provenance should include v2.0'
  );
}

const buyQuad = compare.items.find((item) => item.id === 'buy_quad');
assert.ok(buyQuad, 'Expected buy_quad card');
assert.ok(
  buyQuad?.changeOriginsInRange.some((origin) => origin.versionId === 'v4.0' && origin.validationStatus === 'complete'),
  'buy_quad provenance should include v4.0 as complete'
);
assert.ok(buyQuad && buyQuad.visualPayload.type === 'buy_quad', 'Expected buy_quad card to return buy_quad payload');
if (buyQuad && buyQuad.visualPayload.type === 'buy_quad') {
  assert.ok(
    Number.isFinite(buyQuad.visualPayload.medianMultiplier.left) && buyQuad.visualPayload.medianMultiplier.left > 0,
    'Expected compare buy_quad medianMultiplier.left to be positive and finite'
  );
  assert.ok(
    Number.isFinite(buyQuad.visualPayload.medianMultiplier.right) && buyQuad.visualPayload.medianMultiplier.right > 0,
    'Expected compare buy_quad medianMultiplier.right to be positive and finite'
  );
}

const unchangedSingleSource = compareParameters(repoRoot, latestVersion, latestVersion, ['uk_housing_stock_totals'], 'through_right')
  .items[0];
assert.ok(unchangedSingleSource, 'Expected uk_housing_stock_totals in single compare payload');
assert.ok(unchangedSingleSource.unchanged, 'Expected uk_housing_stock_totals to be unchanged at same-version compare');
assert.ok(
  unchangedSingleSource.sourceInfo.datasetsRight.length > 0,
  'Expected unchanged single-version card to include source dataset attribution'
);

const wasSingle = compareParameters(repoRoot, 'v4.0', 'v4.0', ['age_distribution'], 'through_right').items[0];
assert.ok(wasSingle, 'Expected age_distribution card in single payload');
const wasDataset = wasSingle?.sourceInfo.datasetsRight.find((dataset) => dataset.tag === 'was');
assert.ok(wasDataset, 'Expected WAS dataset attribution for age_distribution');
assert.equal(wasDataset?.fullName, 'Wealth and Assets Survey', 'Expected WAS full name');
assert.equal(wasDataset?.year, '2022', 'Expected WAS Round 8 year to resolve to 2022');
assert.equal(wasDataset?.edition, 'Round 8', 'Expected WAS edition to resolve to Round 8');

const nmgCompare = compareParameters(repoRoot, 'v1.3', 'v4.0', ['rental_price_lognormal'], 'range').items[0];
assert.ok(nmgCompare, 'Expected rental_price_lognormal card in compare payload');
const nmgLeft = nmgCompare?.sourceInfo.datasetsLeft.find((dataset) => dataset.tag === 'nmg');
const nmgRight = nmgCompare?.sourceInfo.datasetsRight.find((dataset) => dataset.tag === 'nmg');
assert.ok(nmgLeft, 'Expected left-side NMG attribution');
assert.ok(nmgRight, 'Expected right-side NMG attribution');
assert.notEqual(nmgLeft?.year, nmgRight?.year, 'Expected NMG attribution year to vary by version side (left vs right)');
assert.equal(nmgLeft?.year, '2016', 'Expected v1.3 NMG year to be 2016 for rental-price keys');
assert.equal(nmgRight?.year, '2024', 'Expected v4.0 NMG year to be 2024 for rental-price keys');

const fixture = createResultsFixtureRepo();
try {
  const resultsRuns = getResultsRuns(fixture.root);
  assert.equal(resultsRuns.length, 4, 'Expected only synthetic fixture runs to be discovered');
  for (let index = 1; index < resultsRuns.length; index += 1) {
    const prev = Date.parse(resultsRuns[index - 1]?.modifiedAt ?? '');
    const current = Date.parse(resultsRuns[index]?.modifiedAt ?? '');
    assert.ok(prev >= current, 'Expected runs to be sorted by modifiedAt descending');
  }

  const fullRun = resultsRuns.find((run) => run.runId === fixture.runIds.complete);
  assert.ok(fullRun, 'Expected complete fixture run in discovery results');
  assert.equal(fullRun?.status, 'complete', 'Expected complete fixture run to be classified as complete');

  const emptyRun = resultsRuns.find((run) => run.runId === fixture.runIds.emptyOutput);
  assert.ok(emptyRun, 'Expected empty-output fixture run in discovery results');
  assert.equal(emptyRun?.status, 'partial', 'Expected empty-output fixture run to be classified as partial');

  const sparseRun = resultsRuns.find((run) => run.runId === fixture.runIds.sparseCore);
  assert.ok(sparseRun, 'Expected sparse-core fixture run in discovery results');
  assert.equal(sparseRun?.status, 'partial', 'Expected sparse-core fixture run to be classified as partial');

  const runDetail = getResultsRunDetail(fixture.root, fixture.runIds.complete);
  assert.equal(runDetail.kpiSummary.length, 27, 'Expected KPI summary metrics for all 27 indicators');
  assert.equal(runDetail.indicators.length, 27, 'Expected 27 total indicator definitions (15 core + 12 output)');
  assert.ok(runDetail.configAvailable, 'Expected complete fixture run to report config.properties availability');
  const firstKpi = runDetail.kpiSummary[0];
  assert.ok(firstKpi, 'Expected KPI summary entry');
  assert.equal(Object.prototype.hasOwnProperty.call(firstKpi, 'mean'), true, 'Expected KPI payload to include mean');
  assert.equal(Object.prototype.hasOwnProperty.call(firstKpi, 'cv'), true, 'Expected KPI payload to include cv');
  assert.equal(
    Object.prototype.hasOwnProperty.call(firstKpi, 'annualisedTrend'),
    true,
    'Expected KPI payload to include annualisedTrend'
  );
  assert.equal(Object.prototype.hasOwnProperty.call(firstKpi, 'range'), true, 'Expected KPI payload to include range');
  assert.equal(
    Object.prototype.hasOwnProperty.call(firstKpi, 'latest'),
    false,
    'Expected legacy latest KPI field to be removed'
  );
  assert.ok(
    runDetail.indicators.some((indicator) => indicator.id === 'output_interestRate' && indicator.available),
    'Expected output interest rate indicator to be available on complete fixture run'
  );
  assert.ok(
    runDetail.kpiSummary.some((kpi) => kpi.indicatorId === 'output_interestRate'),
    'Expected KPI summary to include output indicators such as output interest rate'
  );

  const scenarioDetail = getResultsRunDetail(fixture.root, fixture.runIds.noConfig);
  assert.equal(
    scenarioDetail.configAvailable,
    false,
    'Expected no-config fixture run to report configAvailable=false'
  );

  const manifestFull = getResultsRunFiles(fixture.root, fixture.runIds.complete);
  assert.ok(
    manifestFull.some(
      (file) => file.fileName === 'Output-run1.csv' && file.coverageStatus === 'supported'
    ),
    'Expected Output-run1.csv to be marked supported in manifest'
  );
  assert.ok(
    manifestFull.some(
      (file) =>
        file.fileName === 'RentalTransactions-run1.csv' &&
        file.coverageStatus === 'unsupported' &&
        file.note?.includes('Manifest only (not charted)')
    ),
    'Expected heavy transaction files to be manifest-only (not charted)'
  );
  for (const fileName of ['TotalDebt-run2.csv', 'HousingStatus-run2.csv', 'NonHousingConsumption-run2.csv']) {
    const manifestEntry = manifestFull.find((file) => file.fileName === fileName);
    assert.equal(manifestEntry?.fileType, 'micro_snapshot', `Expected ${fileName} to be recognized as a micro snapshot`);
    assert.equal(
      manifestEntry?.coverageStatus,
      'unsupported',
      `Expected ${fileName} micro snapshot to remain manifest-only`
    );
  }

  const manifestEmpty = getResultsRunFiles(fixture.root, fixture.runIds.emptyOutput);
  assert.ok(
    manifestEmpty.some((file) => file.fileName === 'Output-run1.csv' && file.coverageStatus === 'empty'),
    'Expected empty Output-run1.csv to be marked empty in manifest'
  );

  const missingMicroManifest = getResultsRunFiles(fixture.root, fixture.runIds.noConfig);
  assert.ok(
    !missingMicroManifest.some((file) => file.fileName === 'BankBalance-run1.csv'),
    'Expected manifest to tolerate runs missing optional micro snapshot files'
  );

  const rawSeries = getResultsSeries(fixture.root, fixture.runIds.complete, 'core_mortgageApprovals', 0);
  const smoothedSeries = getResultsSeries(fixture.root, fixture.runIds.complete, 'core_mortgageApprovals', 12);
  assert.equal(rawSeries.points.length, 2001, 'Expected full run to expose 2001 model-time points');
  assert.equal(smoothedSeries.points.length, rawSeries.points.length, 'Smoothing should preserve point count');
  assert.ok(
    smoothedSeries.points.some((point, index) => point.value !== rawSeries.points[index]?.value),
    'Expected smoothing to modify at least one time point'
  );

  const singleRunCompare = getResultsCompare(
    fixture.root,
    [fixture.runIds.complete],
    ['core_mortgageApprovals'],
    'tail120',
    0
  );
  assert.equal(singleRunCompare.runIds.length, 1, 'Expected compare payload to support single-run manual mode');
  assert.equal(
    singleRunCompare.indicators[0]?.seriesByRun.length,
    1,
    'Expected single-run compare payload to include exactly one aligned series'
  );

  const overlayCompare = getResultsCompare(
    fixture.root,
    [fixture.runIds.complete, fixture.runIds.sparseCore],
    ['core_mortgageApprovals'],
    'tail120',
    0
  );
  assert.equal(overlayCompare.indicators.length, 1, 'Expected single-indicator compare payload');
  const leftSeries = overlayCompare.indicators[0]?.seriesByRun.find((series) => series.runId === fixture.runIds.complete);
  const rightSeries = overlayCompare.indicators[0]?.seriesByRun.find((series) => series.runId === fixture.runIds.sparseCore);
  assert.ok(leftSeries && rightSeries, 'Expected aligned compare series for both selected runs');
  assert.equal(
    leftSeries?.points.length,
    rightSeries?.points.length,
    'Expected compare payload to align series on shared modelTime axis'
  );
  assert.ok(
    rightSeries?.points.every((point) => point.value === null),
    'Expected sparse core run to render as gap-only aligned series'
  );

  const postSpinUpCompare = getResultsCompare(
    fixture.root,
    [fixture.runIds.complete, fixture.runIds.sparseCore],
    ['core_mortgageApprovals'],
    'post200',
    0
  );
  const postSpinUpSeries = postSpinUpCompare.indicators[0]?.seriesByRun.find(
    (series) => series.runId === fixture.runIds.complete
  );
  assert.ok(postSpinUpSeries, 'Expected post200 compare series for complete run');
  assert.ok(
    postSpinUpSeries?.points.every((point) => point.modelTime >= 200),
    'Expected post200 compare window to exclude pre-spin-up ticks'
  );

  assert.throws(
    () =>
      getResultsCompare(
        fixture.root,
        ['r1', 'r2', 'r3'],
        ['core_mortgageApprovals'],
        'tail120',
        0
      ),
    /maximum of 2 runIds/,
    'Expected compare endpoint guardrail for more than two selected runs'
  );

  assert.throws(
    () => getResultsRunDetail(fixture.root, '..'),
    /Unknown run: \.\./,
    'Expected traversal-style run ids to be rejected'
  );

  const deleted = deleteResultsRun(fixture.root, fixture.runIds.noConfig);
  assert.equal(deleted.deleted, true, 'Expected delete results API to report success');
  assert.equal(deleted.runId, fixture.runIds.noConfig, 'Expected delete payload to return the deleted runId');
  assert.ok(
    !getResultsRuns(fixture.root).some((run) => run.runId === fixture.runIds.noConfig),
    'Expected deleted run to be removed from run inventory'
  );
  assert.throws(
    () => deleteResultsRun(fixture.root, '..'),
    /Unknown run: \.\./,
    'Expected traversal-style run ids to be rejected for run deletion'
  );
  for (const protectedRunId of ['v0-output', 'v4.0-output']) {
    assert.throws(
      () => deleteResultsRun(fixture.root, protectedRunId),
      /protected/,
      `Expected baseline run ${protectedRunId} to be protected from deletion`
    );
  }
} finally {
  fs.rmSync(fixture.root, { recursive: true, force: true });
}

const modelRunFixtureRoot = createModelRunFixtureRepo();
const spawnedProcesses: FakeModelProcess[] = [];

try {
  __resetModelRunManagerForTests();
  __setModelRunSpawnForTests(() => {
    const fakeProcess = new FakeModelProcess();
    spawnedProcesses.push(fakeProcess);
    return fakeProcess as never;
  });

  const runOptions = getModelRunOptions(modelRunFixtureRoot, undefined, true);
  assert.equal(runOptions.executionEnabled, true, 'Expected execution flag to be forwarded by options payload');
  const disabledRunOptions = getModelRunOptions(modelRunFixtureRoot, undefined, false);
  assert.equal(disabledRunOptions.executionEnabled, false, 'Expected options payload to preserve disabled execution mode');
  assert.equal(runOptions.parameters.length, 33, 'Expected all 33 USER SET parameters in options payload');
  for (const key of ['recordTotalDebt', 'recordHousingStatus', 'recordConsumption']) {
    const parameter = runOptions.parameters.find((item) => item.key === key);
    assert.equal(parameter?.type, 'boolean', `Expected ${key} to be exposed as a boolean run option`);
    assert.equal(parameter?.defaultValue, false, `Expected ${key} to default to false`);
  }
  assert.equal(runOptions.defaultBaseline, 'v1.0', 'Expected latest stable baseline to exclude in-progress snapshots');
  assert.equal(runOptions.requestedBaseline, 'v1.0', 'Expected requested baseline default to latest stable snapshot');
  assert.ok(
    runOptions.snapshots.some((snapshot) => snapshot.version === 'v1.1' && snapshot.status === 'in_progress'),
    'Expected in-progress snapshot status in options payload'
  );

  const optionsForInProgress = getModelRunOptions(modelRunFixtureRoot, 'v1.1', true);
  assert.equal(optionsForInProgress.requestedBaseline, 'v1.1', 'Expected baseline override selection to be honored');

  const originalResultsCapMb = process.env.DASHBOARD_RESULTS_CAP_MB;
  try {
    process.env.DASHBOARD_RESULTS_CAP_MB = '2';

    const protectedRunPath = path.join(modelRunFixtureRoot, 'Results', 'v0-output');
    fs.mkdirSync(protectedRunPath, { recursive: true });
    writeSizedFile(path.join(protectedRunPath, 'protected.bin'), 1024 * 1024);

    const storageBefore = getResultsStorageSummary(modelRunFixtureRoot);
    assert.equal(storageBefore.capBytes, 2 * 1024 * 1024, 'Expected storage summary to reflect DASHBOARD_RESULTS_CAP_MB');
    assert.ok(storageBefore.usedBytes >= 1024 * 1024, 'Expected storage summary used bytes to include baseline fixture files');

    const overCapSubmit = submitModelRun(modelRunFixtureRoot, {
      baseline: 'v1.0',
      title: 'cap-overflow-visible',
      overrides: { SEED: 12 },
      confirmWarnings: true
    });
    assert.equal(overCapSubmit.accepted, true, 'Expected run submission to be accepted while still under cap');
    assert.equal(spawnedProcesses.length, 1, 'Expected accepted run to start immediately');

    const overCapOutputPath = path.join(modelRunFixtureRoot, overCapSubmit.job?.outputPath ?? '');
    writeSizedFile(path.join(overCapOutputPath, 'overflow.bin'), 1200 * 1024);

    spawnedProcesses[spawnedProcesses.length - 1]?.succeed();
    await waitForAsyncTick();
    const completedOverCapJob = listModelRunJobs().find((job) => job.jobId === overCapSubmit.job?.jobId);
    assert.equal(completedOverCapJob?.status, 'succeeded', 'Expected run to finish successfully when crossing cap');
    assert.ok(fs.existsSync(overCapOutputPath), 'Expected over-cap completed run output folder to remain visible');

    const storageAfter = getResultsStorageSummary(modelRunFixtureRoot);
    assert.ok(storageAfter.usedBytes > storageAfter.capBytes, 'Expected storage usage to exceed cap after completed run');
    assert.throws(
      () =>
        submitModelRun(modelRunFixtureRoot, {
          baseline: 'v1.0',
          title: 'blocked-after-over-cap',
          overrides: { SEED: 13 },
          confirmWarnings: true
        }),
      /Results storage cap reached/,
      'Expected submission to fail when Results storage is at or above configured cap'
    );
    assert.ok(
      fs.existsSync(overCapOutputPath),
      'Expected strict cap mode to keep completed over-cap run output visible'
    );

    const bypassOverCapSubmit = submitModelRun(
      modelRunFixtureRoot,
      {
        baseline: 'v1.0',
        title: 'allowed-over-cap-dev-bypass',
        overrides: { SEED: 14 },
        confirmWarnings: true
      },
      { ignoreStorageCap: true }
    );
    assert.equal(
      bypassOverCapSubmit.accepted,
      true,
      'Expected bypass mode to allow submission even when Results storage is above cap'
    );
    assert.equal(spawnedProcesses.length, 2, 'Expected bypass over-cap submit to start a second process');
    spawnedProcesses[spawnedProcesses.length - 1]?.succeed();
    await waitForAsyncTick();
    const completedBypassJob = listModelRunJobs().find((job) => job.jobId === bypassOverCapSubmit.job?.jobId);
    assert.equal(completedBypassJob?.status, 'succeeded', 'Expected bypass over-cap job to complete successfully');
    clearModelRunJob(bypassOverCapSubmit.job?.jobId ?? '');
    clearModelRunJob(overCapSubmit.job?.jobId ?? '');
  } finally {
    if (originalResultsCapMb === undefined) {
      delete process.env.DASHBOARD_RESULTS_CAP_MB;
    } else {
      process.env.DASHBOARD_RESULTS_CAP_MB = originalResultsCapMb;
    }
  }
  __resetModelRunManagerForTests();
  spawnedProcesses.length = 0;
  __setModelRunSpawnForTests(() => {
    const fakeProcess = new FakeModelProcess();
    spawnedProcesses.push(fakeProcess);
    return fakeProcess as never;
  });

  const warningResponse = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: 'warning-check',
    overrides: { N_STEPS: 5001 },
    confirmWarnings: false
  });
  assert.equal(warningResponse.accepted, false, 'Expected submit to request explicit warning confirmation');
  assert.ok((warningResponse.warnings?.length ?? 0) > 0, 'Expected warning payload when confirmation is missing');
  assert.equal(listModelRunJobs().length, 0, 'Expected warning-only submit not to enqueue a job');

  const firstSubmit = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: 'first-run',
    overrides: { N_STEPS: 5001 },
    confirmWarnings: true
  });
  assert.equal(firstSubmit.accepted, true, 'Expected confirmed warning submit to enqueue run');
  assert.ok(firstSubmit.job, 'Expected accepted submit to include job payload');
  assert.equal(firstSubmit.job?.runId, 'first-run v1.0', 'Expected run title to determine output folder name');
  assert.equal(spawnedProcesses.length, 1, 'Expected first accepted submit to start runner immediately');

  const secondSubmit = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: 'second-run',
    overrides: { SEED: 77 },
    confirmWarnings: true
  });
  assert.equal(secondSubmit.accepted, true, 'Expected second submit to be accepted into queue');
  const queuedJob = listModelRunJobs().find((job) => job.jobId === secondSubmit.job?.jobId);
  assert.equal(queuedJob?.status, 'queued', 'Expected second job to queue while first run is active');

  spawnedProcesses[0]?.emitStdout('sim line');
  spawnedProcesses[0]?.emitStderr('warn line');
  await waitForAsyncTick();
  const firstLogs = getModelRunJobLogs(firstSubmit.job?.jobId ?? '', 0, 50);
  assert.ok(firstLogs.lines.some((line) => line.includes('sim line')), 'Expected stdout log line in polling payload');
  assert.ok(firstLogs.lines.some((line) => line.includes('warn line')), 'Expected stderr log line in polling payload');

  cancelModelRunJob(modelRunFixtureRoot, secondSubmit.job?.jobId ?? '');
  const canceledQueuedJob = listModelRunJobs().find((job) => job.jobId === secondSubmit.job?.jobId);
  assert.equal(canceledQueuedJob?.status, 'canceled', 'Expected queued cancel to mark job as canceled');

  spawnedProcesses[0]?.succeed();
  await waitForAsyncTick();
  const completedFirstJob = listModelRunJobs().find((job) => job.jobId === firstSubmit.job?.jobId);
  assert.equal(completedFirstJob?.status, 'succeeded', 'Expected first job to complete successfully');
  assert.ok(
    completedFirstJob && fs.existsSync(path.join(modelRunFixtureRoot, completedFirstJob.outputPath)),
    'Expected successful run output folder to persist'
  );

  const warningCoreIndicatorsOff = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: 'core-off-warning',
    overrides: { recordCoreIndicators: false },
    confirmWarnings: false
  });
  assert.equal(warningCoreIndicatorsOff.accepted, false, 'Expected submit to block until warnings are confirmed');
  assert.ok(
    warningCoreIndicatorsOff.warnings.some((warning) => warning.code === 'core_indicators_disabled'),
    'Expected warning when recordCoreIndicators is disabled'
  );

  const preexistingRunFolder = path.join(modelRunFixtureRoot, 'Results', 'overwrite-case v1.0');
  fs.mkdirSync(preexistingRunFolder, { recursive: true });
  fs.writeFileSync(path.join(preexistingRunFolder, 'Output-run1.csv'), 'Model time;nRenting\n0;1\n', 'utf-8');

  const overwriteWarning = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: 'overwrite-case',
    overrides: { SEED: 5 },
    confirmWarnings: false
  });
  assert.equal(overwriteWarning.accepted, false, 'Expected overwrite warning to require explicit confirmation');
  assert.ok(
    overwriteWarning.warnings.some((warning) => warning.code === 'output_folder_exists'),
    'Expected overwrite warning when output folder already exists'
  );

  const overwriteSubmit = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: 'overwrite-case',
    overrides: { SEED: 5 },
    confirmWarnings: true
  });
  assert.equal(overwriteSubmit.accepted, true, 'Expected overwrite-confirmed submit to enqueue run');
  assert.equal(spawnedProcesses.length, 2, 'Expected overwrite-confirmed run to start immediately');
  assert.throws(
    () =>
      submitModelRun(modelRunFixtureRoot, {
        baseline: 'v1.0',
        title: 'overwrite-case',
        overrides: { SEED: 6 },
        confirmWarnings: true
      }),
    /already targeting output folder/,
    'Expected active output-folder collision to be rejected'
  );
  assert.throws(
    () => clearModelRunJob(overwriteSubmit.job?.jobId ?? ''),
    /Only finished jobs can be cleared/,
    'Expected running jobs to be non-clearable'
  );
  spawnedProcesses[1]?.succeed();
  await waitForAsyncTick();
  const overwriteCompleted = listModelRunJobs().find((job) => job.jobId === overwriteSubmit.job?.jobId);
  assert.equal(overwriteCompleted?.status, 'succeeded', 'Expected overwrite-confirmed run to complete successfully');

  const thirdSubmit = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: 'cancel-running',
    overrides: { SEED: 9 },
    confirmWarnings: true
  });
  assert.equal(thirdSubmit.accepted, true, 'Expected third submit accepted');
  assert.equal(spawnedProcesses.length, 3, 'Expected third submit to start another process after previous completion');
  cancelModelRunJob(modelRunFixtureRoot, thirdSubmit.job?.jobId ?? '');
  await waitForAsyncTick();
  const canceledRunningJob = listModelRunJobs().find((job) => job.jobId === thirdSubmit.job?.jobId);
  assert.equal(canceledRunningJob?.status, 'canceled', 'Expected running cancel to transition to canceled');
  assert.ok(
    canceledRunningJob && !fs.existsSync(path.join(modelRunFixtureRoot, canceledRunningJob.outputPath)),
    'Expected canceled running job output folder to be removed'
  );

  const lateCancelSubmit = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: 'late-cancel-race',
    overrides: { SEED: 10 },
    confirmWarnings: true
  });
  assert.equal(lateCancelSubmit.accepted, true, 'Expected late-cancel race submit to be accepted');
  const lateCancelProcess = spawnedProcesses[spawnedProcesses.length - 1];
  assert.ok(lateCancelProcess, 'Expected late-cancel race submit to spawn a process');
  lateCancelProcess?.disableSigtermDelivery();
  cancelModelRunJob(modelRunFixtureRoot, lateCancelSubmit.job?.jobId ?? '');
  lateCancelProcess?.succeed();
  await waitForAsyncTick();
  const lateCancelCompleted = listModelRunJobs().find((job) => job.jobId === lateCancelSubmit.job?.jobId);
  assert.equal(
    lateCancelCompleted?.status,
    'succeeded',
    'Expected failed SIGTERM delivery to preserve successful completion status'
  );
  assert.ok(
    lateCancelCompleted && fs.existsSync(path.join(modelRunFixtureRoot, lateCancelCompleted.outputPath)),
    'Expected successful run output folder to be retained when cancel signal is not delivered'
  );

  const firstOutputPath = completedFirstJob?.outputPath;
  clearModelRunJob(firstSubmit.job?.jobId ?? '');
  assert.ok(
    !listModelRunJobs().some((job) => job.jobId === firstSubmit.job?.jobId),
    'Expected clear job action to remove finished job from queue history'
  );
  assert.ok(
    firstOutputPath && fs.existsSync(path.join(modelRunFixtureRoot, firstOutputPath)),
    'Expected clear job action not to delete successful run outputs'
  );

  __resetModelRunManagerForTests();
  __setModelRunSpawnForTests(() => new FakeModelProcess() as never);
  const untitledSubmit = submitModelRun(modelRunFixtureRoot, {
    baseline: 'v1.0',
    title: '   ',
    overrides: { SEED: 88 },
    confirmWarnings: true
  });
  assert.equal(untitledSubmit.accepted, true, 'Expected untitled submit to be accepted with fallback folder naming');
  assert.match(
    untitledSubmit.job?.runId ?? '',
    /^run-\d{8}T\d{6}Z v1\.0$/,
    'Expected untitled submit to use run-<timestamp> <baseline> output folder naming'
  );

  __resetModelRunManagerForTests();
  __setModelRunSpawnForTests(() => new FakeModelProcess() as never);
  for (let index = 0; index < 10; index += 1) {
    const response = submitModelRun(modelRunFixtureRoot, {
      baseline: 'v1.0',
      title: `queue-fill-${index + 1}`,
      overrides: { SEED: index + 1 },
      confirmWarnings: true
    });
    assert.equal(response.accepted, true, 'Expected queue fill submissions to succeed before cap');
  }
  assert.throws(
    () =>
      submitModelRun(modelRunFixtureRoot, {
        baseline: 'v1.0',
        overrides: { SEED: 999 },
        confirmWarnings: true
      }),
    /capacity reached/,
    'Expected queue cap guardrail to reject submissions above limit'
  );
} finally {
  __resetModelRunManagerForTests();
  fs.rmSync(modelRunFixtureRoot, { recursive: true, force: true });
}

const sensitivityFixtureRoot = createModelRunFixtureRepo();
const sensitivityProcesses: FakeModelProcess[] = [];

try {
  __resetModelRunManagerForTests();
  __resetSensitivityRunsForTests();
  __setSensitivityRunSpawnForTests((_repoRoot, configPath, outputPath) => {
    const config = parseConfigFile(configPath);
    const baseRate = Number.parseFloat(config.get('CENTRAL_BANK_INITIAL_BASE_RATE') ?? '0');
    writeSensitivityCoreOutputs(outputPath, baseRate);
    const process = new FakeModelProcess();
    sensitivityProcesses.push(process);
    setTimeout(() => {
      process.emitStdout(`running point ${baseRate}`);
      process.succeed();
    }, 0);
    return process as never;
  });

  const warningSubmit = submitSensitivityExperiment(sensitivityFixtureRoot, {
    baseline: 'v1.0',
    parameterKey: 'TARGET_POPULATION',
    min: 10_000,
    max: 20_000,
    confirmWarnings: false
  });
  assert.equal(warningSubmit.accepted, false, 'Expected sensitivity submit to require warning confirmation');
  assert.ok((warningSubmit.warnings.length ?? 0) > 0, 'Expected warning payload for high target population points');

  const successSubmit = submitSensitivityExperiment(sensitivityFixtureRoot, {
    baseline: 'v1.0',
    title: 'base-rate-sweep',
    parameterKey: 'CENTRAL_BANK_INITIAL_BASE_RATE',
    min: 0.004,
    max: 0.006,
    confirmWarnings: true
  });
  assert.equal(successSubmit.accepted, true, 'Expected sensitivity submit to start experiment');
  const successExperimentId = successSubmit.experiment?.experimentId ?? '';
  assert.ok(successExperimentId.length > 0, 'Expected started sensitivity experiment id');

  await waitUntil(() => {
    const detail = getSensitivityExperiment(sensitivityFixtureRoot, successExperimentId).experiment;
    return detail.status === 'succeeded';
  });

  const successDetail = getSensitivityExperiment(sensitivityFixtureRoot, successExperimentId).experiment;
  assert.equal(successDetail.status, 'succeeded', 'Expected sensitivity experiment to finish as succeeded');
  assert.equal(successDetail.sampledPoints.length, 5, 'Expected five sampled points for non-integer sweep');
  assert.equal(
    hasActiveSensitivityExperiment(sensitivityFixtureRoot),
    false,
    'Expected no active sensitivity experiment after completion'
  );

  const successResults = getSensitivityExperimentResults(sensitivityFixtureRoot, successExperimentId);
  assert.equal(successResults.points.length, 5, 'Expected five point results in summary payload');
  assert.ok(
    successResults.points.every((point) => point.status === 'succeeded'),
    'Expected all points to succeed for deterministic sensitivity fixture'
  );
  assert.ok(
    successResults.points.every((point) => point.outputPath === null),
    'Expected summary-only sensitivity run to avoid retained point outputs'
  );
  assert.ok(
    !fs.existsSync(path.join(sensitivityFixtureRoot, 'Results', 'experiments', 'sensitivity', successExperimentId, 'points')),
    'Expected summary-only sensitivity run not to retain points folder'
  );
  const firstPointMetric = successResults.points[0]?.indicatorMetrics[0];
  assert.ok(firstPointMetric, 'Expected indicator KPI metrics to be present for sensitivity points');
  assert.equal(
    Object.prototype.hasOwnProperty.call(firstPointMetric, 'kpi'),
    true,
    'Expected sensitivity metrics to include KPI bundle'
  );
  assert.equal(
    Object.prototype.hasOwnProperty.call(firstPointMetric, 'deltaFromBaseline'),
    true,
    'Expected sensitivity metrics to include KPI-keyed deltas'
  );
  const baselinePoint = successResults.points.find((point) => point.isBaseline) ?? null;
  const comparisonPoint = successResults.points.find((point) => !point.isBaseline) ?? null;
  const baselineMetric = baselinePoint?.indicatorMetrics.find((metric) => metric.indicatorId === firstPointMetric.indicatorId) ?? null;
  const comparisonMetric = comparisonPoint?.indicatorMetrics.find((metric) => metric.indicatorId === firstPointMetric.indicatorId) ?? null;
  const baselineMean = baselineMetric?.kpi.mean ?? null;
  const comparisonMean = comparisonMetric?.kpi.mean ?? null;
  const observedPercentDiff = comparisonMetric?.deltaFromBaseline.mean ?? null;
  if (baselineMean === null || comparisonMean === null || observedPercentDiff === null) {
    throw new Error('Expected baseline and comparison KPI means with a computed % diff for at least one indicator');
  }
  const expectedPercentDiff = ((comparisonMean - baselineMean) / baselineMean) * 100;
  assertClose(
    observedPercentDiff,
    expectedPercentDiff,
    1e-9,
    'Expected KPI delta to be stored as percent difference from baseline'
  );

  const successCharts = getSensitivityExperimentCharts(sensitivityFixtureRoot, successExperimentId);
  assert.ok(successCharts.tornado.length > 0, 'Expected tornado chart payload to include indicators');
  assert.equal(successCharts.windowType, 'tail_120', 'Expected sensitivity charts payload to include tail_120 window');
  assert.equal(
    Object.prototype.hasOwnProperty.call(successCharts.tornado[0] ?? {}, 'maxAbsDeltaByKpi'),
    true,
    'Expected tornado payload to include KPI-keyed max deltas'
  );
  assert.ok(
    successCharts.deltaTrend.every((series) => series.points.length > 0),
    'Expected delta-trend payload to include points for each policy indicator'
  );
  assert.equal(
    Object.prototype.hasOwnProperty.call(successCharts.deltaTrend[0]?.points[0] ?? {}, 'deltaByKpi'),
    true,
    'Expected delta trend points to include KPI-keyed signed % differences'
  );
  assert.equal(
    typeof successCharts.tornado[0]?.maxAbsDeltaByKpi.mean,
    'number',
    'Expected tornado mean basis value to be computed'
  );
  assert.equal(
    typeof successCharts.tornado[0]?.maxAbsDeltaByKpi.range,
    'number',
    'Expected tornado range basis value to be computed'
  );

  const logsPayload = getSensitivityExperimentLogs(sensitivityFixtureRoot, successExperimentId, 0, 200);
  assert.ok(
    logsPayload.lines.some((line) => line.includes('[system]')),
    'Expected sensitivity logs to include lifecycle system markers'
  );
  assert.ok(
    logsPayload.lines.some((line) => line.includes('[stdout]')),
    'Expected sensitivity logs to include stdout output lines'
  );

  const fullOutputSubmit = submitSensitivityExperiment(sensitivityFixtureRoot, {
    baseline: 'v1.0',
    title: 'retain-outputs',
    parameterKey: 'CENTRAL_BANK_INITIAL_BASE_RATE',
    min: 0.004,
    max: 0.006,
    retainFullOutput: true,
    confirmWarnings: true
  });
  assert.equal(fullOutputSubmit.accepted, true, 'Expected full-output sensitivity submit to be accepted');
  const fullOutputExperimentId = fullOutputSubmit.experiment?.experimentId ?? '';
  await waitUntil(() => {
    const detail = getSensitivityExperiment(sensitivityFixtureRoot, fullOutputExperimentId).experiment;
    return detail.status === 'succeeded';
  });
  const fullOutputResults = getSensitivityExperimentResults(sensitivityFixtureRoot, fullOutputExperimentId);
  assert.ok(
    fullOutputResults.points.some((point) => Boolean(point.outputPath)),
    'Expected full-output sensitivity run to retain output paths'
  );
  const retainedOutput = fullOutputResults.points.find((point) => point.outputPath)?.outputPath ?? '';
  assert.ok(
    retainedOutput && fs.existsSync(path.join(sensitivityFixtureRoot, retainedOutput)),
    'Expected retained sensitivity point output path to exist on disk'
  );

  const duplicateSubmit = submitSensitivityExperiment(sensitivityFixtureRoot, {
    baseline: 'v1.0',
    parameterKey: 'CENTRAL_BANK_LTI_MONTHS_TO_CHECK',
    min: 11.6,
    max: 12.4,
    confirmWarnings: true
  });
  assert.equal(duplicateSubmit.accepted, true, 'Expected integer duplicate-range sweep to be accepted');
  const duplicateExperimentId = duplicateSubmit.experiment?.experimentId ?? '';
  await waitUntil(() => {
    const detail = getSensitivityExperiment(sensitivityFixtureRoot, duplicateExperimentId).experiment;
    return detail.status === 'succeeded';
  });
  const duplicateDetail = getSensitivityExperiment(sensitivityFixtureRoot, duplicateExperimentId).experiment;
  assert.equal(duplicateDetail.sampledPoints.length, 1, 'Expected rounded duplicate points to collapse into one sample');
  assert.equal(
    duplicateDetail.collapsedSlots.min,
    duplicateDetail.collapsedSlots.max,
    'Expected collapsed slot mapping to point at a single sampled point'
  );

  assert.throws(
    () =>
      submitSensitivityExperiment(sensitivityFixtureRoot, {
        baseline: 'v1.0',
        parameterKey: 'recordTransactions',
        min: 0,
        max: 1,
        confirmWarnings: true
      }),
    /must be numeric/,
    'Expected boolean sensitivity parameter to be rejected'
  );

  assert.throws(
    () =>
      submitSensitivityExperiment(sensitivityFixtureRoot, {
        baseline: 'v1.0',
        parameterKey: 'CENTRAL_BANK_INITIAL_BASE_RATE',
        min: 0.006,
        max: 0.007,
        confirmWarnings: true
      }),
    /must be within/,
    'Expected sensitivity range to require baseline inclusion'
  );

  __resetSensitivityRunsForTests();
  __setSensitivityRunSpawnForTests((_repoRoot, configPath, outputPath) => {
    const config = parseConfigFile(configPath);
    const baseRate = Number.parseFloat(config.get('CENTRAL_BANK_INITIAL_BASE_RATE') ?? '0');
    writeSensitivityCoreOutputs(outputPath, baseRate);
    const process = new FakeModelProcess();
    sensitivityProcesses.push(process);
    return process as never;
  });

  const cancelSubmit = submitSensitivityExperiment(sensitivityFixtureRoot, {
    baseline: 'v1.0',
    parameterKey: 'CENTRAL_BANK_INITIAL_BASE_RATE',
    min: 0.004,
    max: 0.006,
    confirmWarnings: true
  });
  assert.equal(cancelSubmit.accepted, true, 'Expected cancel target sensitivity submit to be accepted');
  const cancelExperimentId = cancelSubmit.experiment?.experimentId ?? '';
  await waitUntil(() => sensitivityProcesses.length > 0);
  cancelSensitivityExperiment(sensitivityFixtureRoot, cancelExperimentId);
  await waitUntil(() => {
    const detail = getSensitivityExperiment(sensitivityFixtureRoot, cancelExperimentId).experiment;
    return detail.status === 'canceled';
  });
  const canceledDetail = getSensitivityExperiment(sensitivityFixtureRoot, cancelExperimentId).experiment;
  assert.equal(canceledDetail.status, 'canceled', 'Expected canceled sensitivity experiment status');

  __resetModelRunManagerForTests();
  __setModelRunSpawnForTests(() => {
    const process = new FakeModelProcess();
    return process as never;
  });
  const lockedManualSubmit = submitModelRun(sensitivityFixtureRoot, {
    baseline: 'v1.0',
    title: 'manual-lock',
    overrides: { SEED: 42 },
    confirmWarnings: true
  });
  assert.equal(lockedManualSubmit.accepted, true, 'Expected manual queue submit to seed unified job lock test');
  const lockedManualJobId = lockedManualSubmit.job?.jobId ?? '';
  const unifiedJobs = listExperimentJobs(sensitivityFixtureRoot);
  assert.ok(
    unifiedJobs.jobs.some((job) => job.jobRef === `manual:${lockedManualJobId}`),
    'Expected unified job list to include manual job entry'
  );
  assert.ok(
    unifiedJobs.jobs.some((job) => job.jobRef === `sensitivity:${successExperimentId}`),
    'Expected unified job list to include sensitivity job entry'
  );
  assert.equal(
    unifiedJobs.locks.sensitivitySubmissionLocked,
    true,
    'Expected unified locks to block sensitivity submission when manual queue is active'
  );
  const unifiedSensitivityLogs = getExperimentJobLogs(
    sensitivityFixtureRoot,
    `sensitivity:${cancelExperimentId}`,
    0,
    200
  );
  assert.ok(unifiedSensitivityLogs.lines.length > 0, 'Expected unified logs endpoint to return sensitivity logs');
  assert.throws(
    () =>
      submitSensitivityExperiment(sensitivityFixtureRoot, {
        baseline: 'v1.0',
        parameterKey: 'CENTRAL_BANK_INITIAL_BASE_RATE',
        min: 0.004,
        max: 0.006,
        confirmWarnings: true
      }),
    /manual model runs are queued or running/,
    'Expected sensitivity submission to be blocked while manual run queue is active'
  );
  cancelExperimentJob(sensitivityFixtureRoot, `manual:${lockedManualJobId}`);
  await waitUntil(() => {
    const job = listExperimentJobs(sensitivityFixtureRoot).jobs.find((item) => item.jobRef === `manual:${lockedManualJobId}`);
    return job?.status === 'canceled';
  });

  __resetModelRunManagerForTests();
  __resetSensitivityRunsForTests();
  const experimentsAfterReload = listSensitivityExperiments(sensitivityFixtureRoot).experiments;
  assert.ok(
    experimentsAfterReload.some((experiment) => experiment.experimentId === successExperimentId),
    'Expected persisted completed sensitivity experiment to reload from disk'
  );

  const legacyExperimentId = 'sensitivity-legacy-schema-fixture';
  const legacyRoot = path.join(
    sensitivityFixtureRoot,
    'Results',
    'experiments',
    'sensitivity',
    legacyExperimentId
  );
  fs.mkdirSync(legacyRoot, { recursive: true });
  fs.writeFileSync(
    path.join(legacyRoot, 'metadata.json'),
    JSON.stringify(
      {
        experimentId: legacyExperimentId,
        baseline: 'v1.0',
        status: 'succeeded',
        createdAt: new Date().toISOString(),
        endedAt: new Date().toISOString(),
        retainFullOutput: false,
        parameter: {
          key: 'CENTRAL_BANK_INITIAL_BASE_RATE',
          title: 'Initial base rate',
          description: 'fixture',
          type: 'number',
          baselineValue: 0.005,
          min: 0.004,
          max: 0.006
        },
        warnings: [],
        warningSummary: { byPoint: {} },
        sampledPoints: [
          { pointId: 'point-0.005', value: 0.005, label: '0.005', slotLabels: ['baseline'], isBaseline: true }
        ],
        collapsedSlots: {
          min: 'point-0.005',
          mid_lower: 'point-0.005',
          baseline: 'point-0.005',
          mid_upper: 'point-0.005',
          max: 'point-0.005'
        },
        runCommand: {
          mavenBin: 'mvn',
          commandTemplate: 'fixture'
        }
      },
      null,
      2
    ),
    'utf-8'
  );
  fs.writeFileSync(
    path.join(legacyRoot, 'summary.json'),
    JSON.stringify(
      {
        results: {
          experimentId: legacyExperimentId,
          baselinePointId: 'point-0.005',
          points: [
            {
              pointId: 'point-0.005',
              value: 0.005,
              label: '0.005',
              slotLabels: ['baseline'],
              isBaseline: true,
              status: 'succeeded',
              runId: 'legacy-run',
              outputPath: null,
              indicatorMetrics: [
                {
                  indicatorId: 'core_ooLTV',
                  title: 'Owner-Occupier LTV (Mean Above Median)',
                  units: '%',
                  tail120Mean: 1.23,
                  deltaFromBaseline: 0
                }
              ]
            }
          ]
        },
        charts: {
          experimentId: legacyExperimentId,
          parameter: {
            key: 'CENTRAL_BANK_INITIAL_BASE_RATE',
            title: 'Initial base rate',
            description: 'fixture',
            type: 'number',
            baselineValue: 0.005,
            min: 0.004,
            max: 0.006
          },
          tornado: [
            {
              indicatorId: 'core_ooLTV',
              title: 'Owner-Occupier LTV (Mean Above Median)',
              units: '%',
              maxAbsDelta: 0
            }
          ],
          deltaTrend: [
            {
              indicatorId: 'core_ooLTV',
              title: 'Owner-Occupier LTV (Mean Above Median)',
              units: '%',
              points: [{ parameterValue: 0.005, delta: 0 }]
            }
          ]
        }
      },
      null,
      2
    ),
    'utf-8'
  );

  __resetSensitivityRunsForTests();
  const legacyResults = getSensitivityExperimentResults(sensitivityFixtureRoot, legacyExperimentId);
  const legacyMetric = legacyResults.points[0]?.indicatorMetrics[0];
  assert.equal(legacyMetric?.kpi.mean, 1.23, 'Expected legacy mean metric to migrate into KPI mean');
  assert.equal(legacyMetric?.kpi.cv, null, 'Expected legacy summary migration to default unsupported KPI keys to null');
  const legacyCharts = getSensitivityExperimentCharts(sensitivityFixtureRoot, legacyExperimentId);
  assert.equal(
    Object.prototype.hasOwnProperty.call(legacyCharts.tornado[0] ?? {}, 'maxAbsDeltaByKpi'),
    true,
    'Expected legacy tornado payload to migrate to KPI-keyed shape on read'
  );

  const interruptedExperimentId = 'sensitivity-interrupted-fixture';
  const interruptedRoot = path.join(
    sensitivityFixtureRoot,
    'Results',
    'experiments',
    'sensitivity',
    interruptedExperimentId
  );
  fs.mkdirSync(interruptedRoot, { recursive: true });
  fs.writeFileSync(
    path.join(interruptedRoot, 'metadata.json'),
    JSON.stringify(
      {
        experimentId: interruptedExperimentId,
        baseline: 'v1.0',
        status: 'running',
        createdAt: new Date().toISOString(),
        retainFullOutput: false,
        parameter: {
          key: 'CENTRAL_BANK_INITIAL_BASE_RATE',
          title: 'Initial base rate',
          description: 'fixture',
          type: 'number',
          baselineValue: 0.005,
          min: 0.004,
          max: 0.006
        },
        warnings: [],
        warningSummary: { byPoint: {} },
        sampledPoints: [],
        collapsedSlots: {
          min: 'point-0',
          mid_lower: 'point-0',
          baseline: 'point-0',
          mid_upper: 'point-0',
          max: 'point-0'
        },
        runCommand: {
          mavenBin: 'mvn',
          commandTemplate: 'fixture'
        }
      },
      null,
      2
    ),
    'utf-8'
  );

  __resetSensitivityRunsForTests();
  const restartedDetail = getSensitivityExperiment(sensitivityFixtureRoot, interruptedExperimentId).experiment;
  assert.equal(
    restartedDetail.status,
    'failed',
    'Expected non-terminal sensitivity experiment to be marked failed after restart reload'
  );
  assert.equal(
    restartedDetail.failureReason,
    'interrupted_on_restart',
    'Expected restart interruption failure reason to be persisted'
  );
} finally {
  __resetSensitivityRunsForTests();
  __resetModelRunManagerForTests();
  fs.rmSync(sensitivityFixtureRoot, { recursive: true, force: true });
}

const writeAuthDisabled = createWriteAuthController(undefined, undefined);
const disabledStatus = writeAuthDisabled.resolveAccess(undefined);
assert.equal(disabledStatus.authEnabled, false, 'Expected auth to be disabled when credentials are unset');
assert.equal(disabledStatus.canWrite, true, 'Expected local write access when auth is disabled');

const misconfiguredAuthStatus = resolveDashboardWriteAccess(writeAuthDisabled, undefined, true);
assert.equal(
  misconfiguredAuthStatus.authEnabled,
  true,
  'Expected model-runs-enabled auth misconfiguration to report auth-enabled read-only mode'
);
assert.equal(
  misconfiguredAuthStatus.canWrite,
  false,
  'Expected model-runs-enabled auth misconfiguration to block write access'
);
assert.equal(
  misconfiguredAuthStatus.authMisconfigured,
  true,
  'Expected auth misconfiguration status to be surfaced for UI and API handling'
);
const misconfiguredLoginError = getWriteAuthConfigurationError(writeAuthDisabled, true);
assert.ok(
  misconfiguredLoginError?.includes('DASHBOARD_WRITE_USERNAME'),
  'Expected auth misconfiguration to surface actionable login-blocking configuration error'
);
const devBypassAuthStatus = resolveDashboardWriteAccess(writeAuthDisabled, undefined, true, true);
assert.equal(devBypassAuthStatus.authEnabled, false, 'Expected dev bypass mode to disable auth lockout presentation');
assert.equal(devBypassAuthStatus.canWrite, true, 'Expected dev bypass mode to grant write access');
assert.equal(devBypassAuthStatus.authMisconfigured, false, 'Expected dev bypass mode to clear misconfiguration state');
assert.equal(
  getWriteAuthConfigurationError(writeAuthDisabled, true, true),
  null,
  'Expected dev bypass mode to suppress write-auth misconfiguration errors'
);

const writeAuthEnabled = createWriteAuthController('writer', 'secret');
const enabledStatusWithoutToken = writeAuthEnabled.resolveAccess(undefined);
assert.equal(enabledStatusWithoutToken.authEnabled, true, 'Expected auth to be enabled when credentials are configured');
assert.equal(enabledStatusWithoutToken.canWrite, false, 'Expected write access to require login in auth-enabled mode');

const badLogin = writeAuthEnabled.login('writer', 'incorrect');
assert.equal(badLogin.ok, false, 'Expected login to fail for invalid credentials');

const goodLogin = writeAuthEnabled.login('writer', 'secret');
assert.equal(goodLogin.ok, true, 'Expected login to succeed for valid credentials');
assert.ok(goodLogin.token, 'Expected successful login to issue a token');

const enabledStatusWithToken = writeAuthEnabled.resolveAccess(`Bearer ${goodLogin.token}`);
assert.equal(enabledStatusWithToken.canWrite, true, 'Expected bearer token to grant write access');
writeAuthEnabled.logout(goodLogin.token ?? null);
const afterLogoutStatus = writeAuthEnabled.resolveAccess(`Bearer ${goodLogin.token}`);
assert.equal(afterLogoutStatus.canWrite, false, 'Expected logout to revoke write access token');

const compareCardSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/src/components/CompareCard.tsx'), 'utf-8');
assert.ok(
  !compareCardSource.includes('Validation dataset'),
  'Compare card should not render Validation dataset field'
);

const manualResultsViewSource = fs.readFileSync(
  path.resolve(repoRoot, 'dashboard/src/pages/experiments/view/ManualResultsView.tsx'),
  'utf-8'
);
assert.ok(
  manualResultsViewSource.includes("dotted lines show each selected run&apos;s mean over the"),
  'Manual results overlay help copy should explain the dotted mean reference lines'
);

const appSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/src/App.tsx'), 'utf-8');
assert.ok(
  appSource.includes('const experimentsVisible = isDevEnv && !isProdPreviewEnabled;'),
  'App should gate experiments behind the dev-only visibility condition'
);
assert.ok(
  appSource.includes("from './pages/ValidationPage'"),
  'App should import the validation page when dev-only validation is available'
);
assert.ok(
  appSource.includes('const validationVisible = isDevEnv && !isProdPreviewEnabled;'),
  'App should gate validation behind the same true-dev visibility condition'
);
assert.ok(
  appSource.includes('<NavLink to="/compare">Calibration</NavLink>'),
  'App should label the compare route as Calibration in the header'
);
assert.ok(
  appSource.includes('{validationVisible && <NavLink to="/validation">Validation</NavLink>}'),
  'App should only render the validation nav item when validation is visible'
);
assert.ok(
  appSource.includes('{validationVisible && <Route path="/validation" element={<ValidationPage />} />}'),
  'App should only register the validation route when validation is visible'
);
assert.ok(
  appSource.includes("{experimentsVisible && <NavLink to=\"/experiments\">Experiments</NavLink>}"),
  'App should hide the experiments nav when experiments are not visible'
);
assert.ok(
  appSource.includes("{experimentsVisible && (\n              <Route\n                path=\"/experiments\""),
  'App should only register the experiments route when experiments are visible'
);

const validationPageSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/src/pages/ValidationPage.tsx'), 'utf-8');
const eChartSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/src/components/EChart.tsx'), 'utf-8');
const publicRoutesSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/server/routes/publicRoutes.ts'), 'utf-8');
const serviceSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/server/lib/service.ts'), 'utf-8');
const apiSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/src/lib/api.ts'), 'utf-8');
assert.ok(
  !validationPageSource.includes('three_lines'),
  'Validation page should no longer support the three-line mode'
);
assert.ok(
  validationPageSource.includes('validation-mode-row') &&
    validationPageSource.includes('Summary view') &&
    validationPageSource.includes('v0-2011 reference summary'),
  'Validation page should render a tracked/reference summary toggle'
);
assert.ok(
  validationPageSource.includes('Validation Loss Across Versions'),
  'Validation page should render the plain-English validation trend heading'
);
assert.ok(
  validationPageSource.includes('tracked 2024 timeline') &&
    validationPageSource.includes('full <code>v0-2011</code> reference summary'),
  'Validation page should explain that the trend chart stays tracked while the table can switch to the v0-2011 reference view'
);
assert.ok(
  validationPageSource.includes('core_hpiStd') &&
    validationPageSource.includes('core_hpiCyclePeriod') &&
    validationPageSource.includes('2011-anchored'),
  'Validation page should explain the 2011 HPI benchmark split between core_hpiStd and core_hpiCyclePeriod'
);
assert.ok(
  !validationPageSource.includes('Validation Categories'),
  'Validation page should remove the validation categories section'
);
assert.ok(
  validationPageSource.includes('Validation Results by Metric for'),
  'Validation page should render the renamed metric results section'
);
assert.ok(
  validationPageSource.includes('selectedValidationTargetYear'),
  'Validation page should render the selected validation target year in the metric results copy'
);
assert.ok(
  validationPageSource.includes('distance relative to target level'),
  'Validation page should explain how validation loss is calculated'
);
assert.ok(
  validationPageSource.includes('The line chart is a secondary overview'),
  'Validation page should explain that the chart is a secondary decision aid'
);
assert.ok(
  validationPageSource.includes('referenceLineLabel') &&
    validationPageSource.includes('Tracked summary:') &&
    !validationPageSource.includes('Dashed comparator:'),
  'Validation page tooltip should keep the tracked-summary copy and remove the dashed-comparator line'
);
assert.ok(
  !validationPageSource.includes('Click to filter the table'),
  'Validation page should remove the family-card table filters'
);
assert.ok(
  !validationPageSource.includes('Family weight'),
  'Validation page should remove validation family weight copy'
);
assert.ok(
  validationPageSource.includes('Search metrics'),
  'Validation page should render metric table search controls'
);
assert.ok(
  validationPageSource.includes('Sort by'),
  'Validation page should render metric table sort controls'
);
assert.ok(
  validationPageSource.includes('Loss delta vs v0-2011') &&
    validationPageSource.includes('lossDeltaVsReference2011'),
  'Validation page should render the signed loss-delta column versus v0-2011'
);
assert.ok(
  !validationPageSource.includes('Show all categories'),
  'Validation page should remove family filter reset controls'
);
assert.ok(
  validationPageSource.includes('Provenance & sources'),
  'Validation page should keep metric sources collapsed behind a disclosure'
);
assert.ok(
  validationPageSource.includes('validation-source-panel'),
  'Validation page should render a dedicated provenance panel when expanded'
);
assert.ok(
  validationPageSource.includes('validation-metric-cell'),
  'Validation page should stack the metric name and provenance controls vertically within the metric cell'
);
assert.ok(
  !validationPageSource.includes('validation-metric-meta'),
  'Validation page should not render metric-id descriptors under the main metric names'
);
assert.ok(
  validationPageSource.includes('metricLoss'),
  'Validation page should render each metric loss from the validation payload'
);
assert.ok(
  !validationPageSource.includes('selectedFamilyIds'),
  'Validation page should stop tracking validation family filters'
);
assert.ok(
  validationPageSource.includes('metricSearch'),
  'Validation page should track the metric search term'
);
assert.ok(
  validationPageSource.includes('sortMode'),
  'Validation page should track the selected metric sort mode'
);
assert.ok(
  validationPageSource.includes("const DEFAULT_SORT_MODE: ValidationSortMode = 'highest_loss';"),
  'Validation page should default the metric table to highest loss first'
);
assert.ok(
  validationPageSource.includes('openMetricIds'),
  'Validation page should track row-level provenance disclosure state'
);
assert.ok(
  validationPageSource.includes('Seeds inside band'),
  'Validation page should render inside-band uncertainty copy'
);
assert.ok(
  validationPageSource.includes('p25-p75'),
  'Validation page should render p25-p75 uncertainty labels'
);
assert.ok(
  validationPageSource.includes('Weight'),
  'Validation page should render the metric weight column'
);
assert.ok(
  validationPageSource.includes('validation-source-label'),
  'Validation page should render inline source labels for validation metrics'
);
assert.ok(
  validationPageSource.includes('sourceReferences'),
  'Validation page should render structured source references when available'
);
assert.ok(
  validationPageSource.includes('metricWeight'),
  'Validation page should render each metric weight from the validation payload'
);
assert.ok(
  validationPageSource.includes("viewMode === 'tracked' && (") && validationPageSource.includes('<span>Version</span>'),
  'Validation page should hide the version selector whenever the v0-2011 reference summary is selected'
);
assert.ok(
  !validationPageSource.includes('lossWeight'),
  'Validation page should stop rendering lossWeight fields'
);
assert.ok(
  !validationPageSource.includes('familySummaries'),
  'Validation page should stop depending on family summaries'
);
assert.ok(
  !validationPageSource.includes('familyId'),
  'Validation page should stop depending on metric family ids'
);
assert.ok(
  validationPageSource.includes('selectedVersion'),
  'Validation page should track the selected version'
);
assert.ok(
  !validationPageSource.includes("formatter: 'Selected'"),
  'Validation page should not render the selected chart label inside the marker icon'
);
assert.ok(
  validationPageSource.includes("position: 'top'"),
  'Validation page should position the selected chart label above the marker'
);
assert.ok(
  validationPageSource.includes('handleChartClick') &&
    validationPageSource.includes('Click a point to load that tracked version') &&
    validationPageSource.includes('onClick={handleChartClick}'),
  'Validation page should wire chart point clicks to tracked-version selection'
);
assert.ok(
  eChartSource.includes('onClick?: (params: unknown) => void;') &&
    eChartSource.includes("instance.on('click', clickHandler)") &&
    eChartSource.includes("instance.off('click', clickHandler)"),
  'EChart should expose an optional click handler and attach it to the ECharts instance'
);
assert.ok(
  apiSource.includes("/api/validation-overview") && apiSource.includes("view: ValidationOverviewViewMode"),
  'API client should fetch the validation overview payload with an explicit view mode'
);
assert.ok(
  publicRoutesSource.includes("/api/validation-overview") && publicRoutesSource.includes("req.query.view"),
  'Public routes should expose the validation overview endpoint and accept the view query parameter'
);
assert.ok(
  !serviceSource.includes('entry.validation.income_diff_pct'),
  'Validation overview should not derive page data from legacy version-notes diffs'
);

const comparePageSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/src/pages/ComparePage.tsx'), 'utf-8');
assert.ok(
  comparePageSource.includes("const DEFAULT_OPEN_COMPARE_CARD_IDS = new Set<string>([") &&
    comparePageSource.includes("'house_price_lognormal'") &&
    comparePageSource.includes("'wealth_given_income_joint'") &&
    comparePageSource.includes("'downpayment_ftb_lognormal'"),
  'Compare page should default-open the requested house price, wealth, and FTB down-payment cards'
);
assert.ok(
  comparePageSource.includes("const DEFAULT_OPEN_COMPARE_GROUPS = new Set<ParameterGroup>([") &&
    comparePageSource.includes("'Housing & Rental Market'") &&
    comparePageSource.includes("'Household Demographics & Wealth'") &&
    comparePageSource.includes("'Purchase & Mortgage'"),
  'Compare page should open the groups containing the requested default cards'
);
assert.ok(
  comparePageSource.includes('defaultExpanded={DEFAULT_OPEN_COMPARE_CARD_IDS.has(item.id)}'),
  'Compare page should drive default card expansion from the configured default-open ids'
);

assert.ok(
  compareCardSource.includes('const [isMoreInfoOpen, setIsMoreInfoOpen] = useState<boolean>(false);'),
  'Compare card should keep provenance and sources collapsed by default'
);
assert.ok(
  appSource.includes("{experimentsVisible && (\n              <Route\n                path=\"/login\""),
  'App should only register the experiments login route when experiments are visible'
);

const homePageSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/src/pages/HomePage.tsx'), 'utf-8');
assert.ok(
  !homePageSource.includes('fetchGitStats'),
  'Home page should no longer fetch git stats'
);
assert.ok(
  homePageSource.includes('fetchHomePreview(latest)'),
  'Home page should fetch the lightweight home preview payload'
);
assert.ok(
  !homePageSource.includes('Lines of Code Written'),
  'Home page should no longer render git stats cards'
);

const serverIndexSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/server/index.ts'), 'utf-8');
assert.ok(
  serverIndexSource.includes("const EXPERIMENTS_DISABLED_REASON =\n  'Experiments are not available in this environment.';"),
  'Server should define a stable experiments-disabled error message'
);
assert.ok(
  serverIndexSource.includes('function requireExperimentsFeature(req: express.Request, res: express.Response): boolean {'),
  'Server should centralize experiments feature gating'
);
assert.ok(
  serverIndexSource.includes("import { registerPublicRoutes } from './routes/publicRoutes';"),
  'Server should register public routes through a dedicated module'
);
assert.ok(
  serverIndexSource.includes("const { registerDevRoutes } = await import('./routes/devRoutes');"),
  'Server should load dev-only routes lazily so production does not import them'
);
assert.ok(
  serverIndexSource.includes("const memoryLoggingEnabled = (process.env.DASHBOARD_LOG_MEMORY?.trim().toLowerCase() ?? '') === 'true';"),
  'Server should support optional request-level memory logging'
);

assert.ok(
  publicRoutesSource.includes("app.get('/api/home-preview'"),
  'Public routes should expose the lightweight home preview endpoint'
);
assert.ok(
  !publicRoutesSource.includes("/api/git-stats"),
  'Public routes should not expose git stats'
);
assert.ok(
  publicRoutesSource.includes('getHomePreview(context.repoRoot, version, HOME_PREVIEW_PARAMETER_IDS)'),
  'Public routes should serve the home preview from the lightweight service function'
);

const devRoutesSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/server/routes/devRoutes.ts'), 'utf-8');
assert.ok(
  devRoutesSource.includes("app.get('/api/model-runs/options'"),
  'Dev routes should contain model-run endpoints'
);
assert.ok(
  devRoutesSource.includes("app.get('/api/results/runs'"),
  'Dev routes should contain results-management endpoints'
);
assert.ok(
  devRoutesSource.includes("if (!context.requireExperimentsFeature(req, res)) {"),
  'Dev routes should still guard experiments behind the experiments feature flag'
);

assert.ok(
  !apiSource.includes('fetchGitStats'),
  'Client API should no longer expose fetchGitStats'
);
assert.ok(
  apiSource.includes("buildApiUrl('/api/home-preview')"),
  'Client API should expose the lightweight home preview fetcher'
);

const resultsSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/server/lib/results.ts'), 'utf-8');
assert.ok(
  resultsSource.includes("const OUTPUT_CACHE_MAX_ENTRIES = (process.env.NODE_ENV?.trim().toLowerCase() ?? '') === 'production' ? 0 : 2;"),
  'Results parsing should disable the output cache in production'
);

const packageSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/package.json'), 'utf-8');
assert.ok(
  packageSource.includes("\"start:server\": \"node dist-server/server/index.js\""),
  'Production server should run compiled JavaScript instead of tsx'
);

const dockerfileSource = fs.readFileSync(path.resolve(repoRoot, 'dashboard/Dockerfile.api'), 'utf-8');
assert.ok(
  dockerfileSource.includes('RUN npm run build:server'),
  'Docker API image should build compiled server output'
);
assert.ok(
  !dockerfileSource.includes('openjdk-17-jdk'),
  'Docker API image should no longer install Java'
);

console.log('Smoke tests passed.');
