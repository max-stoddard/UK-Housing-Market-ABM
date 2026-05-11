import { useCallback, useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import type { AuthStatusPayload } from '../shared/types';
import {
  fetchAuthStatus,
  logoutWriteAccess,
  setApiAuthToken,
  setApiViewMode
} from './lib/api';
import { ComparePage } from './pages/ComparePage';
import { ExperimentsPage } from './pages/ExperimentsPage';
import { HomePage } from './pages/HomePage';
import { LoginPage } from './pages/LoginPage';
import { ValidationPage } from './pages/ValidationPage';

const AUTH_TOKEN_STORAGE_KEY = 'dashboard.writeAuthToken';
const PREVIEW_MODE_STORAGE_KEY = 'dashboard.prodPreviewEnabled';
const EXPERIMENTS_VIEW_PATH = '/experiments?mode=view&type=manual';

const DEFAULT_AUTH_STATUS: AuthStatusPayload = {
  authEnabled: false,
  canWrite: true,
  authMisconfigured: false,
  modelRunsEnabled: false,
  modelRunsConfigured: false,
  modelRunsDisabledReason: null
};

function loadStoredAuthToken(): string | null {
  try {
    return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistAuthToken(token: string | null): void {
  try {
    if (token) {
      window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    }
  } catch {
    // ignore persistence failures
  }
}

function loadStoredProdPreviewEnabled(): boolean {
  try {
    return window.localStorage.getItem(PREVIEW_MODE_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

function persistProdPreviewEnabled(enabled: boolean): void {
  try {
    if (enabled) {
      window.localStorage.setItem(PREVIEW_MODE_STORAGE_KEY, 'true');
    } else {
      window.localStorage.removeItem(PREVIEW_MODE_STORAGE_KEY);
    }
  } catch {
    // ignore persistence failures
  }
}

function getDesktopApi(): UkHousingDesktopApi | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.ukHousingDesktop ?? null;
}

export function App() {
  const isDevEnv = import.meta.env.DEV;
  const [desktopApi] = useState<UkHousingDesktopApi | null>(() => getDesktopApi());
  const isDesktopRuntime = Boolean(desktopApi);
  const [isProdPreviewEnabled, setIsProdPreviewEnabled] = useState<boolean>(() =>
    isDevEnv ? loadStoredProdPreviewEnabled() : false
  );
  const [authStatus, setAuthStatus] = useState<AuthStatusPayload>(DEFAULT_AUTH_STATUS);
  const [authInitialised, setAuthInitialised] = useState(false);
  const [authLoaded, setAuthLoaded] = useState(false);
  const [authError, setAuthError] = useState('');
  const [desktopActionError, setDesktopActionError] = useState('');
  const [desktopActionMessage, setDesktopActionMessage] = useState('');
  const experimentsVisible = true;
  const validationVisible = isDevEnv && !isProdPreviewEnabled;

  const loginPath = `/login?next=${encodeURIComponent(EXPERIMENTS_VIEW_PATH)}`;

  const refreshAuthStatus = useCallback(async () => {
    try {
      const status = await fetchAuthStatus();
      setAuthStatus(status);
      if (!isDesktopRuntime && status.authEnabled && !status.canWrite) {
        setApiAuthToken(null);
        persistAuthToken(null);
      }
      setAuthError('');
    } catch (error) {
      setAuthError((error as Error).message);
    } finally {
      setAuthLoaded(true);
    }
  }, [isDesktopRuntime]);

  useEffect(() => {
    let cancelled = false;

    async function initialiseAuthToken(): Promise<void> {
      try {
        if (desktopApi) {
          const token = await desktopApi.getApiAuthToken();
          if (cancelled) {
            return;
          }
          setApiAuthToken(token);
          persistAuthToken(null);
        } else {
          setApiAuthToken(loadStoredAuthToken());
        }
      } catch (error) {
        if (!cancelled) {
          setApiAuthToken(null);
          setAuthError((error as Error).message);
        }
      } finally {
        if (!cancelled) {
          setAuthInitialised(true);
        }
      }
    }

    void initialiseAuthToken();

    return () => {
      cancelled = true;
    };
  }, [desktopApi]);

  useEffect(() => {
    if (!authInitialised) {
      return;
    }
    if (!isDevEnv && isProdPreviewEnabled) {
      setIsProdPreviewEnabled(false);
      return;
    }
    persistProdPreviewEnabled(isDevEnv && isProdPreviewEnabled);
    setApiViewMode(isDevEnv && !isProdPreviewEnabled ? 'dev' : 'non_dev_preview');
    void refreshAuthStatus();
  }, [authInitialised, experimentsVisible, isDevEnv, isProdPreviewEnabled, refreshAuthStatus]);

  const handleLoginSuccess = useCallback(
    async (token: string | null) => {
      setApiAuthToken(token);
      persistAuthToken(token);
      await refreshAuthStatus();
    },
    [refreshAuthStatus]
  );

  const handleLogout = useCallback(async () => {
    if (isDesktopRuntime) {
      return;
    }
    try {
      await logoutWriteAccess();
    } catch {
      // ignore logout API errors and clear token locally
    }
    setApiAuthToken(null);
    persistAuthToken(null);
    await refreshAuthStatus();
  }, [isDesktopRuntime, refreshAuthStatus]);

  const handleOpenDesktopFolder = useCallback(async (openFolder: () => Promise<UkHousingDesktopFolderOpenResult>) => {
    const result = await openFolder();
    if (result.ok) {
      setDesktopActionError('');
      setDesktopActionMessage('');
      return;
    }
    setDesktopActionError(result.error ?? 'Unable to open desktop folder.');
    setDesktopActionMessage('');
  }, []);

  const handleExportSupportBundle = useCallback(async (desktopApiInput: UkHousingDesktopApi) => {
    const result = await desktopApiInput.exportSupportBundle();
    if (result.ok) {
      setDesktopActionError('');
      setDesktopActionMessage(`Support bundle exported: ${result.path ?? 'desktop support-bundles folder'}`);
      return;
    }
    setDesktopActionError(result.error ?? 'Unable to export support bundle.');
    setDesktopActionMessage('');
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-wrap">
          <p className="eyebrow">Max Stoddard BEng Individual Project</p>
          <h1 className="brand-title">
            <span>UK Housing Market ABM</span>
            {isDevEnv && <span className="env-pill-dev">Dev</span>}
            {isDevEnv && (
              <button
                type="button"
                className="env-toggle"
                onClick={() => setIsProdPreviewEnabled((current) => !current)}
                aria-pressed={isProdPreviewEnabled}
              >
                {isProdPreviewEnabled ? 'Show dev view' : 'Preview non-dev'}
              </button>
            )}
          </h1>
        </div>
        <div className="header-nav-wrap">
          <nav className="main-nav" aria-label="Main">
            <NavLink to="/" end>
              Home
            </NavLink>
            <NavLink to="/compare">Calibration</NavLink>
            {validationVisible && <NavLink to="/validation">Validation</NavLink>}
            {experimentsVisible && <NavLink to="/experiments">Experiments</NavLink>}
            {experimentsVisible && !isDesktopRuntime && authStatus.authEnabled && !authStatus.canWrite && (
              <NavLink className="main-nav-auth-control main-nav-auth-link" to={loginPath}>
                <span className="main-nav-auth-icon" aria-hidden="true">
                  <svg viewBox="0 0 20 20" role="img" aria-hidden="true">
                    <path
                      d="M10 2.5a3.75 3.75 0 1 0 0 7.5a3.75 3.75 0 0 0 0-7.5zm0 9c-3.44 0-6.25 1.98-6.25 4.42V17.5h12.5v-1.58c0-2.44-2.81-4.42-6.25-4.42z"
                      fill="currentColor"
                    />
                  </svg>
                </span>
                <span>Login</span>
              </NavLink>
            )}
            {experimentsVisible && !isDesktopRuntime && authStatus.authEnabled && authStatus.canWrite && (
              <button type="button" className="main-nav-auth-control main-nav-auth-button" onClick={() => void handleLogout()}>
                <span className="main-nav-auth-icon" aria-hidden="true">
                  <svg viewBox="0 0 20 20" role="img" aria-hidden="true">
                    <path
                      d="M10 2.5a3.75 3.75 0 1 0 0 7.5a3.75 3.75 0 0 0 0-7.5zm0 9c-3.44 0-6.25 1.98-6.25 4.42V17.5h12.5v-1.58c0-2.44-2.81-4.42-6.25-4.42z"
                      fill="currentColor"
                    />
                  </svg>
                </span>
                <span>Logout</span>
              </button>
            )}
          </nav>
          {desktopApi && (
            <div className="desktop-folder-actions" aria-label="Desktop folders">
              <button
                type="button"
                onClick={() => void handleOpenDesktopFolder(desktopApi.openResultsFolder)}
                title="Open Results Folder"
              >
                Results Folder
              </button>
              <button
                type="button"
                onClick={() => void handleOpenDesktopFolder(desktopApi.openLogsFolder)}
                title="Open Logs Folder"
              >
                Logs Folder
              </button>
              <button
                type="button"
                onClick={() => void handleExportSupportBundle(desktopApi)}
                title="Export Support Bundle"
              >
                Support Bundle
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="app-main">
        {authError && <p className="error-banner">{authError}</p>}
        {desktopActionError && <p className="error-banner">{desktopActionError}</p>}
        {desktopActionMessage && <p className="info-banner">{desktopActionMessage}</p>}
        {experimentsVisible && authLoaded && authStatus.authMisconfigured && (
          <p className="error-banner">
            Write access is disabled: model runs are enabled but dashboard write credentials are not configured.
          </p>
        )}
        {!authLoaded ? (
          <p className="loading-banner">Checking access...</p>
        ) : (
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/compare" element={<ComparePage />} />
            {validationVisible && <Route path="/validation" element={<ValidationPage />} />}
            {experimentsVisible && (
              <Route
                path="/experiments"
                element={<ExperimentsPage canWrite={authStatus.canWrite} authEnabled={authStatus.authEnabled} />}
              />
            )}
            {experimentsVisible && (
              <Route
                path="/login"
                element={<LoginPage authStatus={authStatus} onLoginSuccess={handleLoginSuccess} />}
              />
            )}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>

      <footer className="app-footer">© 2026 Max Stoddard. All rights reserved.</footer>
    </div>
  );
}
