import { randomBytes, timingSafeEqual } from 'node:crypto';

const SESSION_TTL_MS = 24 * 60 * 60 * 1000;

export interface WriteAccessStatus {
  authEnabled: boolean;
  canWrite: boolean;
  token: string | null;
}

export interface DashboardWriteAccessStatus extends WriteAccessStatus {
  authMisconfigured: boolean;
}

interface SessionRecord {
  expiresAt: number;
}

export interface WriteAuthController {
  resolveAccess(authorizationHeader: string | undefined): WriteAccessStatus;
  login(username: string, password: string): { ok: boolean; token?: string; canWrite: boolean };
  logout(token: string | null): void;
  authEnabled: boolean;
}

export function getWriteAuthConfigurationError(
  writeAuth: WriteAuthController,
  modelRunsEnabled: boolean,
  devBypassActive = false
): string | null {
  if (devBypassActive) {
    return null;
  }
  if (modelRunsEnabled && !writeAuth.authEnabled) {
    return 'Model runs are enabled but write credentials are not configured. Set DASHBOARD_WRITE_USERNAME and DASHBOARD_WRITE_PASSWORD.';
  }
  return null;
}

export function resolveDashboardWriteAccess(
  writeAuth: WriteAuthController,
  authorizationHeader: string | undefined,
  modelRunsEnabled: boolean,
  devBypassActive = false
): DashboardWriteAccessStatus {
  if (devBypassActive) {
    return {
      authEnabled: false,
      canWrite: true,
      token: null,
      authMisconfigured: false
    };
  }

  const configError = getWriteAuthConfigurationError(writeAuth, modelRunsEnabled, false);
  if (configError) {
    return {
      authEnabled: true,
      canWrite: false,
      token: null,
      authMisconfigured: true
    };
  }

  const access = writeAuth.resolveAccess(authorizationHeader);
  return {
    ...access,
    authMisconfigured: false
  };
}

function secureEquals(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left, 'utf-8');
  const rightBuffer = Buffer.from(right, 'utf-8');
  if (leftBuffer.length !== rightBuffer.length) {
    return false;
  }
  return timingSafeEqual(leftBuffer, rightBuffer);
}

function parseBearerToken(authorizationHeader: string | undefined): string | null {
  if (!authorizationHeader) {
    return null;
  }
  const trimmed = authorizationHeader.trim();
  const match = /^Bearer\s+(.+)$/i.exec(trimmed);
  if (!match) {
    return null;
  }
  const token = match[1].trim();
  return token ? token : null;
}

export function createWriteAuthController(
  writeUsernameRaw: string | undefined,
  writePasswordRaw: string | undefined
): WriteAuthController {
  const writeUsername = writeUsernameRaw?.trim() ?? '';
  const writePassword = writePasswordRaw?.trim() ?? '';
  const authEnabled = Boolean(writeUsername && writePassword);
  const sessions = new Map<string, SessionRecord>();

  const purgeExpiredSessions = () => {
    const now = Date.now();
    for (const [token, session] of sessions.entries()) {
      if (session.expiresAt <= now) {
        sessions.delete(token);
      }
    }
  };

  const resolveAccess = (authorizationHeader: string | undefined): WriteAccessStatus => {
    if (!authEnabled) {
      return {
        authEnabled: false,
        canWrite: true,
        token: null
      };
    }

    purgeExpiredSessions();
    const token = parseBearerToken(authorizationHeader);
    if (!token) {
      return {
        authEnabled: true,
        canWrite: false,
        token: null
      };
    }

    const session = sessions.get(token);
    if (!session) {
      return {
        authEnabled: true,
        canWrite: false,
        token: null
      };
    }

    return {
      authEnabled: true,
      canWrite: true,
      token
    };
  };

  const login = (username: string, password: string) => {
    if (!authEnabled) {
      return { ok: true, canWrite: true };
    }

    if (!secureEquals(writeUsername, username.trim()) || !secureEquals(writePassword, password.trim())) {
      return { ok: false, canWrite: false };
    }

    purgeExpiredSessions();
    const token = randomBytes(32).toString('hex');
    sessions.set(token, {
      expiresAt: Date.now() + SESSION_TTL_MS
    });
    return {
      ok: true,
      token,
      canWrite: true
    };
  };

  const logout = (token: string | null) => {
    if (!token) {
      return;
    }
    sessions.delete(token);
  };

  return {
    resolveAccess,
    login,
    logout,
    authEnabled
  };
}

export function createDesktopWriteAuthController(desktopTokenRaw: string | undefined): WriteAuthController {
  const desktopToken = desktopTokenRaw?.trim() ?? '';
  if (!desktopToken) {
    throw new Error('Desktop write auth token is required and must be non-empty.');
  }

  const resolveAccess = (authorizationHeader: string | undefined): WriteAccessStatus => {
    const token = parseBearerToken(authorizationHeader);
    if (!token || !secureEquals(desktopToken, token)) {
      return {
        authEnabled: true,
        canWrite: false,
        token: null
      };
    }

    return {
      authEnabled: true,
      canWrite: true,
      token
    };
  };

  return {
    resolveAccess,
    login: () => ({ ok: false, canWrite: false }),
    logout: () => {
      // Desktop auth uses an Electron-owned per-session bearer token, not server-side sessions.
    },
    authEnabled: true
  };
}

export function createWriteAuthControllerFromEnv(): WriteAuthController {
  return createWriteAuthController(process.env.DASHBOARD_WRITE_USERNAME, process.env.DASHBOARD_WRITE_PASSWORD);
}
