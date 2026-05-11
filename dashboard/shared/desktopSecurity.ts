// Author: Max Stoddard

export interface DesktopFrameLike {
  readonly detached?: boolean;
  readonly origin: string;
  readonly parent: DesktopFrameLike | null;
  readonly top: DesktopFrameLike | null;
  readonly url: string;
  isDestroyed?: () => boolean;
}

export interface DesktopIpcSenderDetails {
  readonly mainWindowWebContentsId: number | null;
  readonly senderFrame: DesktopFrameLike | null;
  readonly senderWebContentsId: number;
  readonly trustedOrigin: string | null;
}

export interface DesktopSecurityDecision {
  readonly ok: boolean;
  readonly reason?: string;
}

export interface DesktopNavigationDetails {
  readonly isMainFrame?: boolean;
  readonly url: string;
}

export interface DesktopWindowOpenDecision {
  readonly action: 'deny';
  readonly openExternalUrl?: string;
}

export function parseUrl(value: string): URL | null {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}

export function deriveTrustedDashboardOrigin(serverUrl: string): string {
  const parsed = parseUrl(serverUrl);
  if (!parsed) {
    throw new Error(`Cannot derive trusted dashboard origin from invalid server URL: ${serverUrl}`);
  }
  return parsed.origin;
}

export function isTrustedDashboardUrl(url: string, trustedOrigin: string | null): boolean {
  if (!trustedOrigin) {
    return false;
  }
  const parsed = parseUrl(url);
  return parsed?.origin === trustedOrigin;
}

export function validateTrustedDesktopIpcSender(details: DesktopIpcSenderDetails): DesktopSecurityDecision {
  if (!details.trustedOrigin) {
    return { ok: false, reason: 'trusted dashboard origin is not initialised' };
  }
  if (!details.mainWindowWebContentsId || details.senderWebContentsId !== details.mainWindowWebContentsId) {
    return { ok: false, reason: 'sender does not belong to the main dashboard window' };
  }

  const frame = details.senderFrame;
  if (!frame) {
    return { ok: false, reason: 'sender frame is unavailable' };
  }
  if (frame.detached || frame.isDestroyed?.()) {
    return { ok: false, reason: 'sender frame is no longer active' };
  }
  if (frame.parent !== null) {
    return { ok: false, reason: 'sender frame is not the main frame' };
  }
  if (frame.top !== null && frame.top !== frame) {
    return { ok: false, reason: 'sender frame is not the top frame' };
  }
  if (frame.origin !== details.trustedOrigin) {
    return { ok: false, reason: 'sender frame origin is not trusted' };
  }
  if (!isTrustedDashboardUrl(frame.url, details.trustedOrigin)) {
    return { ok: false, reason: 'sender frame URL is not trusted' };
  }

  return { ok: true };
}

export function assertTrustedDesktopIpcSender(details: DesktopIpcSenderDetails): void {
  const decision = validateTrustedDesktopIpcSender(details);
  if (!decision.ok) {
    throw new Error(`Rejected desktop IPC from untrusted renderer: ${decision.reason ?? 'unknown reason'}`);
  }
}

export function shouldBlockDashboardNavigation(
  navigation: DesktopNavigationDetails,
  trustedOrigin: string | null
): boolean {
  if (navigation.isMainFrame === false) {
    return false;
  }
  return !isTrustedDashboardUrl(navigation.url, trustedOrigin);
}

export function classifyDesktopWindowOpenTarget(url: string): DesktopWindowOpenDecision {
  const parsed = parseUrl(url);
  if (parsed?.protocol === 'https:' && parsed.username.length === 0 && parsed.password.length === 0) {
    return { action: 'deny', openExternalUrl: parsed.toString() };
  }
  return { action: 'deny' };
}
