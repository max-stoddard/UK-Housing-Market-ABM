export interface LogBufferState {
  logLines: string[];
  logStart: number;
  partialLine: string;
  sink?: LogLineSink;
}

export interface LogSlicePayload {
  cursor: number;
  nextCursor: number;
  lines: string[];
  hasMore: boolean;
  truncated: boolean;
}

export const DEFAULT_LOG_LIMIT = 200;
export const MAX_LOG_LIMIT = 1_000;

export type LogLineSink = (line: string) => void;

export function appendLogLine(state: LogBufferState, line: string, maxLines: number): void {
  state.logLines.push(line);
  if (state.logLines.length > maxLines) {
    const overflow = state.logLines.length - maxLines;
    state.logLines.splice(0, overflow);
    state.logStart += overflow;
  }
  if (state.sink) {
    try {
      state.sink(line);
    } catch {
      // Persistent logging must not break the live in-memory log stream.
    }
  }
}

export function appendOutputChunk(
  state: LogBufferState,
  streamName: 'stdout' | 'stderr',
  chunk: Buffer,
  maxLines: number
): void {
  state.partialLine += chunk.toString('utf-8').replace(/\r\n/g, '\n');

  while (true) {
    const lineBreak = state.partialLine.indexOf('\n');
    if (lineBreak < 0) {
      break;
    }
    const line = state.partialLine.slice(0, lineBreak);
    state.partialLine = state.partialLine.slice(lineBreak + 1);
    appendLogLine(state, `[${streamName}] ${line}`, maxLines);
  }
}

export function flushPartialLine(state: LogBufferState, maxLines: number): void {
  if (!state.partialLine) {
    return;
  }
  appendLogLine(state, `[stdout] ${state.partialLine}`, maxLines);
  state.partialLine = '';
}

export function coerceLogCursor(value: number | undefined): number {
  if (!Number.isFinite(value as number)) {
    return 0;
  }
  return Math.max(0, Math.trunc(value as number));
}

export function coerceLogLimit(value: number | undefined): number {
  if (!Number.isFinite(value as number)) {
    return DEFAULT_LOG_LIMIT;
  }
  const limit = Math.trunc(value as number);
  if (limit <= 0) {
    return DEFAULT_LOG_LIMIT;
  }
  return Math.min(limit, MAX_LOG_LIMIT);
}

export function readLogSlice(
  state: LogBufferState,
  cursor: number | undefined,
  limit: number | undefined
): LogSlicePayload {
  const safeCursor = coerceLogCursor(cursor);
  const safeLimit = coerceLogLimit(limit);
  const startCursor = Math.max(safeCursor, state.logStart);
  const offset = Math.max(0, startCursor - state.logStart);
  const lines = state.logLines.slice(offset, offset + safeLimit);
  const nextCursor = startCursor + lines.length;
  const absoluteEnd = state.logStart + state.logLines.length;

  return {
    cursor: startCursor,
    nextCursor,
    lines,
    hasMore: nextCursor < absoluteEnd,
    truncated: safeCursor < state.logStart
  };
}
