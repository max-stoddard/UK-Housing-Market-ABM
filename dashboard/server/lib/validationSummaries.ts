import fs from 'node:fs';
import path from 'node:path';
import type {
  ValidationCompositeTrendPayload,
  ValidationFamilySummary,
  ValidationMetricSummary,
  ValidationOverviewPayload,
  ValidationVersionSummary
} from '../../shared/types';
import { compareVersions } from './versioning';

function assertObject(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(message);
  }
  return value as Record<string, unknown>;
}

function assertString(value: unknown, message: string): string {
  if (typeof value !== 'string') {
    throw new Error(message);
  }
  return value;
}

function assertStringOrNull(value: unknown, message: string): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  return assertString(value, message);
}

function assertNumber(value: unknown, message: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(message);
  }
  return value;
}

function assertNumberOrNull(value: unknown, message: string): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  return assertNumber(value, message);
}

function assertNumberArray(value: unknown, message: string): number[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'number' || !Number.isFinite(item))) {
    throw new Error(message);
  }
  return value;
}

function parseSourceReference(value: unknown, index: number) {
  const objectValue = assertObject(value, `sourceReferences[${index}] must be an object`);
  return {
    label: assertString(objectValue.label, `sourceReferences[${index}].label must be a string`),
    sourceDocumentPath: assertString(
      objectValue.sourceDocumentPath,
      `sourceReferences[${index}].sourceDocumentPath must be a string`
    ),
    sourceTextPath: assertStringOrNull(
      objectValue.sourceTextPath,
      `sourceReferences[${index}].sourceTextPath must be a string or null`
    ),
    sourceTable: assertStringOrNull(
      objectValue.sourceTable,
      `sourceReferences[${index}].sourceTable must be a string or null`
    ),
    sourcePage: assertNumberOrNull(
      objectValue.sourcePage,
      `sourceReferences[${index}].sourcePage must be a number or null`
    ),
    sourceIndicatorLabel: assertStringOrNull(
      objectValue.sourceIndicatorLabel,
      `sourceReferences[${index}].sourceIndicatorLabel must be a string or null`
    ),
    rawSourceValue: assertNumberOrNull(
      objectValue.rawSourceValue,
      `sourceReferences[${index}].rawSourceValue must be a number or null`
    ),
    sourceAsOf: assertStringOrNull(
      objectValue.sourceAsOf,
      `sourceReferences[${index}].sourceAsOf must be a string or null`
    ),
    sourceUnits: assertStringOrNull(
      objectValue.sourceUnits,
      `sourceReferences[${index}].sourceUnits must be a string or null`
    ),
    notes: assertStringOrNull(objectValue.notes, `sourceReferences[${index}].notes must be a string or null`)
  };
}

function parseStatusCounts(value: unknown, message: string) {
  const objectValue = assertObject(value, message);
  return {
    pass: assertNumber(objectValue.pass, `${message}.pass`),
    warn: assertNumber(objectValue.warn, `${message}.warn`),
    fail: assertNumber(objectValue.fail, `${message}.fail`),
    unsupported: assertNumber(objectValue.unsupported, `${message}.unsupported`)
  };
}

function parseFamilySummary(value: unknown, index: number): ValidationFamilySummary {
  const objectValue = assertObject(value, `familySummaries[${index}] must be an object`);
  return {
    familyId: assertString(objectValue.familyId, `familySummaries[${index}].familyId must be a string`),
    label: assertString(objectValue.label, `familySummaries[${index}].label must be a string`),
    loss: assertNumber(objectValue.loss, `familySummaries[${index}].loss must be a number`),
    statusCounts: parseStatusCounts(
      objectValue.statusCounts,
      `familySummaries[${index}].statusCounts must be an object`
    )
  };
}

function parseMetricSummary(value: unknown, index: number): ValidationMetricSummary {
  const objectValue = assertObject(value, `metrics[${index}] must be an object`);
  const rawTargetBand = objectValue.targetBand;
  const rawSourceReferences = objectValue.sourceReferences;
  const targetBand =
    rawTargetBand === null
      ? null
      : {
          lower: assertNumber(assertObject(rawTargetBand, `metrics[${index}].targetBand must be an object`).lower, `metrics[${index}].targetBand.lower must be a number`),
          upper: assertNumber(assertObject(rawTargetBand, `metrics[${index}].targetBand must be an object`).upper, `metrics[${index}].targetBand.upper must be a number`)
        };

  return {
    metricId: assertString(objectValue.metricId, `metrics[${index}].metricId must be a string`),
    familyId: assertString(objectValue.familyId, `metrics[${index}].familyId must be a string`),
    label: assertString(objectValue.label, `metrics[${index}].label must be a string`),
    status: assertString(objectValue.status, `metrics[${index}].status must be a string`) as ValidationMetricSummary['status'],
    requirement: assertString(
      objectValue.requirement,
      `metrics[${index}].requirement must be a string`
    ) as ValidationMetricSummary['requirement'],
    units: assertString(objectValue.units, `metrics[${index}].units must be a string`),
    sourceLabel: assertString(objectValue.sourceLabel, `metrics[${index}].sourceLabel must be a string`),
    sourceIndicatorLabel: assertStringOrNull(
      objectValue.sourceIndicatorLabel,
      `metrics[${index}].sourceIndicatorLabel must be a string or null`
    ),
    sourceDocumentPath: assertStringOrNull(
      objectValue.sourceDocumentPath,
      `metrics[${index}].sourceDocumentPath must be a string or null`
    ),
    sourceTextPath: assertStringOrNull(
      objectValue.sourceTextPath,
      `metrics[${index}].sourceTextPath must be a string or null`
    ),
    sourceTable: assertStringOrNull(objectValue.sourceTable, `metrics[${index}].sourceTable must be a string or null`),
    sourcePage: assertNumberOrNull(objectValue.sourcePage, `metrics[${index}].sourcePage must be a number or null`),
    rawSourceValue: assertNumberOrNull(
      objectValue.rawSourceValue,
      `metrics[${index}].rawSourceValue must be a number or null`
    ),
    sourceValue: assertNumberOrNull(objectValue.sourceValue, `metrics[${index}].sourceValue must be a number or null`),
    sourceAsOf: assertStringOrNull(objectValue.sourceAsOf, `metrics[${index}].sourceAsOf must be a string or null`),
    sourceUnits: assertStringOrNull(objectValue.sourceUnits, `metrics[${index}].sourceUnits must be a string or null`),
    comparisonUnits: assertStringOrNull(
      objectValue.comparisonUnits,
      `metrics[${index}].comparisonUnits must be a string or null`
    ),
    mappingStatus: assertStringOrNull(
      objectValue.mappingStatus,
      `metrics[${index}].mappingStatus must be a string or null`
    ) as ValidationMetricSummary['mappingStatus'],
    bandMethod: assertStringOrNull(objectValue.bandMethod, `metrics[${index}].bandMethod must be a string or null`),
    bandNotes: assertStringOrNull(objectValue.bandNotes, `metrics[${index}].bandNotes must be a string or null`),
    sourceReferences: Array.isArray(rawSourceReferences)
      ? rawSourceReferences.map((item, sourceIndex) => parseSourceReference(item, sourceIndex))
      : [],
    targetBand,
    seedMean: assertNumber(objectValue.seedMean, `metrics[${index}].seedMean must be a number`),
    p25: assertNumber(objectValue.p25, `metrics[${index}].p25 must be a number`),
    p75: assertNumber(objectValue.p75, `metrics[${index}].p75 must be a number`),
    insideRate: assertNumberOrNull(objectValue.insideRate, `metrics[${index}].insideRate must be a number or null`),
    normalizedDistance: assertNumberOrNull(
      objectValue.normalizedDistance,
      `metrics[${index}].normalizedDistance must be a number or null`
    ),
    normalizedIqr: assertNumberOrNull(objectValue.normalizedIqr, `metrics[${index}].normalizedIqr must be a number or null`),
    metricLoss: assertNumberOrNull(objectValue.metricLoss, `metrics[${index}].metricLoss must be a number or null`)
  };
}

function parseValidationSummary(filePath: string): ValidationVersionSummary {
  const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as unknown;
  const value = assertObject(raw, `${filePath} must contain a JSON object`);
  const windowValue = assertObject(value.window, `${filePath}.window must be an object`);
  if (!Array.isArray(value.familySummaries)) {
    throw new Error(`${filePath}.familySummaries must be an array`);
  }
  if (!Array.isArray(value.metrics)) {
    throw new Error(`${filePath}.metrics must be an array`);
  }
  return {
    schemaVersion: assertNumber(value.schemaVersion, `${filePath}.schemaVersion must be a number`),
    version: assertString(value.version, `${filePath}.version must be a string`),
    generatedAt: assertString(value.generatedAt, `${filePath}.generatedAt must be a string`),
    seeds: assertNumberArray(value.seeds, `${filePath}.seeds must be a number array`),
    window: {
      startIndex: assertNumber(windowValue.startIndex, `${filePath}.window.startIndex must be a number`),
      endIndex: assertNumber(windowValue.endIndex, `${filePath}.window.endIndex must be a number`)
    },
    overallCompositeLoss: assertNumber(
      value.overallCompositeLoss,
      `${filePath}.overallCompositeLoss must be a number`
    ),
    familySummaries: value.familySummaries.map((item, index) => parseFamilySummary(item, index)),
    metrics: value.metrics.map((item, index) => parseMetricSummary(item, index))
  };
}

export function listValidationSummaryVersions(repoRoot: string): string[] {
  const validationDir = path.join(repoRoot, 'input-data-versions', 'validation');
  if (!fs.existsSync(validationDir)) {
    return [];
  }

  return fs
    .readdirSync(validationDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => entry.name.replace(/\.json$/u, ''))
    .sort(compareVersions);
}

export function readValidationSummary(repoRoot: string, version: string): ValidationVersionSummary {
  const filePath = path.join(repoRoot, 'input-data-versions', 'validation', `${version}.json`);
  if (!fs.existsSync(filePath)) {
    throw new Error(`Missing validation summary for ${version}`);
  }
  return parseValidationSummary(filePath);
}

export function getValidationOverview(repoRoot: string, requestedVersion?: string): ValidationOverviewPayload {
  const availableVersions = listValidationSummaryVersions(repoRoot);
  if (availableVersions.length === 0) {
    throw new Error('No tracked validation summaries are available');
  }

  const selectedVersion = requestedVersion?.trim() ? requestedVersion : availableVersions[availableVersions.length - 1];
  if (!selectedVersion || !availableVersions.includes(selectedVersion)) {
    throw new Error(`Unknown validation summary version: ${requestedVersion ?? ''}`);
  }

  const selectedSummary = readValidationSummary(repoRoot, selectedVersion);
  const trend: ValidationCompositeTrendPayload = {
    points: availableVersions.map((version) => {
      const summary = readValidationSummary(repoRoot, version);
      return {
        version,
        overallCompositeLoss: summary.overallCompositeLoss
      };
    })
  };

  return {
    availableVersions,
    selectedVersion,
    trend,
    selectedSummary
  };
}
