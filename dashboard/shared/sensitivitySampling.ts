// Author: Max Stoddard

export type SensitivityNumericParameterType = 'integer' | 'number';

const NUMERIC_SAMPLE_PRECISION = 15;

export function normalizeSensitivitySampleValue(
  value: number,
  parameterType: SensitivityNumericParameterType
): number {
  const normalized =
    parameterType === 'integer' ? Math.round(value) : Number(value.toPrecision(NUMERIC_SAMPLE_PRECISION));
  return Object.is(normalized, -0) ? 0 : normalized;
}

export function formatSensitivitySampleLabel(value: number): string {
  if (Number.isInteger(value)) {
    return String(value);
  }
  return String(normalizeSensitivitySampleValue(value, 'number'));
}
