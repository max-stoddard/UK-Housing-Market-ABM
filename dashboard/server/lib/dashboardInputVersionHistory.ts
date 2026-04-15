import fs from 'node:fs';
import path from 'node:path';
import { compareVersions } from './versioning';
import type { ValidationStatus } from '../../shared/types';

export interface DashboardInputVersionHistoryValidation {
  status: ValidationStatus;
  income_diff_pct: number | null;
  housing_wealth_diff_pct: number | null;
  financial_wealth_diff_pct: number | null;
  note?: string;
}

export interface DashboardInputVersionHistoryParameterChange {
  config_parameter: string;
  dataset_source: string | null;
}

export interface DashboardInputVersionHistoryEntry {
  version_id: string;
  snapshot_folder: string;
  validation_dataset: string;
  description: string;
  updated_data_sources: string[];
  calibration_files: string[];
  config_parameters: string[];
  parameter_changes: DashboardInputVersionHistoryParameterChange[];
  method_variations: DashboardInputVersionHistoryMethodVariation[];
  validation: DashboardInputVersionHistoryValidation;
}

export interface DashboardInputVersionHistoryMethodVariation {
  config_parameters: string[];
  improvement_summary: string;
  why_changed: string;
  method_chosen?: string;
  decision_logic?: string;
}

interface DashboardInputVersionHistoryDocument {
  author: string;
  schema_version: number;
  description: string;
  entries: DashboardInputVersionHistoryEntry[];
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function assertString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`Invalid dashboard input version history schema: ${field} must be a non-empty string`);
  }
  return value;
}

function assertStringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new Error(`Invalid dashboard input version history schema: ${field} must be a string array`);
  }
  return value;
}

function assertNullableNumber(value: unknown, field: string): number | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new Error(`Invalid dashboard input version history schema: ${field} must be a number or null`);
  }
  return value;
}

function parseValidation(value: unknown, field: string): DashboardInputVersionHistoryValidation {
  if (!isObject(value)) {
    throw new Error(`Invalid dashboard input version history schema: ${field} must be an object`);
  }

  const status = value.status;
  if (status !== 'complete' && status !== 'in_progress') {
    throw new Error(`Invalid dashboard input version history schema: ${field}.status must be 'complete' or 'in_progress'`);
  }

  const note = value.note;
  if (note !== undefined && typeof note !== 'string') {
    throw new Error(`Invalid dashboard input version history schema: ${field}.note must be a string when provided`);
  }

  return {
    status,
    income_diff_pct: assertNullableNumber(value.income_diff_pct, `${field}.income_diff_pct`),
    housing_wealth_diff_pct: assertNullableNumber(value.housing_wealth_diff_pct, `${field}.housing_wealth_diff_pct`),
    financial_wealth_diff_pct: assertNullableNumber(value.financial_wealth_diff_pct, `${field}.financial_wealth_diff_pct`),
    note
  };
}

function parseEntry(value: unknown, index: number): DashboardInputVersionHistoryEntry {
  if (!isObject(value)) {
    throw new Error(`Invalid dashboard input version history schema: entries[${index}] must be an object`);
  }

  const methodVariations = value.method_variations;
  if (!Array.isArray(methodVariations)) {
    throw new Error(`Invalid dashboard input version history schema: entries[${index}].method_variations must be an array`);
  }

  const configParameters = assertStringArray(value.config_parameters, `entries[${index}].config_parameters`);
  const parameterChanges = parseParameterChanges(value.parameter_changes, index);
  assertParameterConsistency(configParameters, parameterChanges, index);

  return {
    version_id: assertString(value.version_id, `entries[${index}].version_id`),
    snapshot_folder: assertString(value.snapshot_folder, `entries[${index}].snapshot_folder`),
    validation_dataset: assertString(value.validation_dataset, `entries[${index}].validation_dataset`),
    description: assertString(value.description, `entries[${index}].description`),
    updated_data_sources: assertStringArray(value.updated_data_sources, `entries[${index}].updated_data_sources`),
    calibration_files: assertStringArray(value.calibration_files, `entries[${index}].calibration_files`),
    config_parameters: configParameters,
    parameter_changes: parameterChanges,
    method_variations: methodVariations.map((variation, variationIndex) =>
      parseMethodVariation(variation, index, variationIndex)
    ),
    validation: parseValidation(value.validation, `entries[${index}].validation`)
  };
}

function parseParameterChanges(
  value: unknown,
  entryIndex: number
): DashboardInputVersionHistoryParameterChange[] {
  if (!Array.isArray(value)) {
    throw new Error(`Invalid dashboard input version history schema: entries[${entryIndex}].parameter_changes must be an array`);
  }

  return value.map((parameterChange, parameterIndex) => {
    if (!isObject(parameterChange)) {
      throw new Error(
        `Invalid dashboard input version history schema: entries[${entryIndex}].parameter_changes[${parameterIndex}] must be an object`
      );
    }

    const datasetSource = parameterChange.dataset_source;
    if (datasetSource !== null && typeof datasetSource !== 'string') {
      throw new Error(
        `Invalid dashboard input version history schema: entries[${entryIndex}].parameter_changes[${parameterIndex}].dataset_source must be a string or null`
      );
    }

    return {
      config_parameter: assertString(
        parameterChange.config_parameter,
        `entries[${entryIndex}].parameter_changes[${parameterIndex}].config_parameter`
      ),
      dataset_source: datasetSource
    };
  });
}

function assertParameterConsistency(
  configParameters: string[],
  parameterChanges: DashboardInputVersionHistoryParameterChange[],
  entryIndex: number
): void {
  const configSet = new Set(configParameters);
  const parameterSet = new Set(parameterChanges.map((change) => change.config_parameter));
  if (configSet.size !== configParameters.length) {
    throw new Error(
      `Invalid dashboard input version history schema: entries[${entryIndex}].config_parameters must not contain duplicates`
    );
  }
  if (parameterSet.size !== parameterChanges.length) {
    throw new Error(
      `Invalid dashboard input version history schema: entries[${entryIndex}].parameter_changes must not contain duplicates`
    );
  }
  if (configSet.size !== parameterSet.size) {
    throw new Error(
      `Invalid dashboard input version history schema: entries[${entryIndex}].config_parameters and entries[${entryIndex}].parameter_changes must match as sets`
    );
  }
  for (const parameter of configSet) {
    if (!parameterSet.has(parameter)) {
      throw new Error(
        `Invalid dashboard input version history schema: entries[${entryIndex}].config_parameters and entries[${entryIndex}].parameter_changes must match as sets`
      );
    }
  }
}

function parseMethodVariation(
  value: unknown,
  entryIndex: number,
  variationIndex: number
): DashboardInputVersionHistoryMethodVariation {
  if (!isObject(value)) {
    throw new Error(
      `Invalid dashboard input version history schema: entries[${entryIndex}].method_variations[${variationIndex}] must be an object`
    );
  }

  const methodChosen = value.method_chosen;
  if (methodChosen !== undefined && typeof methodChosen !== 'string') {
    throw new Error(
      `Invalid dashboard input version history schema: entries[${entryIndex}].method_variations[${variationIndex}].method_chosen must be a string when provided`
    );
  }

  const decisionLogic = value.decision_logic;
  if (decisionLogic !== undefined && typeof decisionLogic !== 'string') {
    throw new Error(
      `Invalid dashboard input version history schema: entries[${entryIndex}].method_variations[${variationIndex}].decision_logic must be a string when provided`
    );
  }

  return {
    config_parameters: assertStringArray(
      value.config_parameters,
      `entries[${entryIndex}].method_variations[${variationIndex}].config_parameters`
    ),
    improvement_summary: assertString(
      value.improvement_summary,
      `entries[${entryIndex}].method_variations[${variationIndex}].improvement_summary`
    ),
    why_changed: assertString(value.why_changed, `entries[${entryIndex}].method_variations[${variationIndex}].why_changed`),
    method_chosen: methodChosen,
    decision_logic: decisionLogic
  };
}

function parseDocument(value: unknown): DashboardInputVersionHistoryDocument {
  if (!isObject(value)) {
    throw new Error('Invalid dashboard input version history schema: root must be an object');
  }

  const entriesValue = value.entries;
  if (!Array.isArray(entriesValue)) {
    throw new Error('Invalid dashboard input version history schema: entries must be an array');
  }

  const document: DashboardInputVersionHistoryDocument = {
    author: assertString(value.author, 'author'),
    schema_version: Number(value.schema_version),
    description: assertString(value.description, 'description'),
    entries: entriesValue.map((entry, index) => parseEntry(entry, index))
  };

  if (!Number.isFinite(document.schema_version)) {
    throw new Error('Invalid dashboard input version history schema: schema_version must be a number');
  }

  return document;
}

export function getDashboardInputVersionHistoryPath(repoRoot: string): string {
  return path.join(repoRoot, 'input-data-versions', 'dashboard-input-version-history.json');
}

export function loadDashboardInputVersionHistory(repoRoot: string): DashboardInputVersionHistoryEntry[] {
  const historyPath = getDashboardInputVersionHistoryPath(repoRoot);
  if (!fs.existsSync(historyPath)) {
    throw new Error(`Missing dashboard input version history file: ${path.relative(repoRoot, historyPath)}`);
  }

  let raw: unknown;
  try {
    raw = JSON.parse(fs.readFileSync(historyPath, 'utf-8'));
  } catch (error) {
    throw new Error(`Invalid dashboard input version history JSON: ${(error as Error).message}`);
  }

  const document = parseDocument(raw);

  return [...document.entries].sort((a, b) => {
    const folderCompare = compareVersions(a.snapshot_folder, b.snapshot_folder);
    if (folderCompare !== 0) {
      return folderCompare;
    }
    return a.version_id.localeCompare(b.version_id);
  });
}
