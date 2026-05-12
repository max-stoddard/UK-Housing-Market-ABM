import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { CompareResponse, ParameterCardMeta, ParameterGroup } from '../../shared/types';
import { API_RETRY_DELAY_MS, fetchCatalog, fetchCompare, fetchVersions, isRetryableApiError } from '../lib/api';
import { CollapsibleSection } from '../components/CollapsibleSection';
import { CompareCard } from '../components/CompareCard';
import { GroupedCheckboxSections } from '../components/GroupedCheckboxSections';
import { LoadingSkeleton, LoadingSkeletonGroup } from '../components/LoadingSkeleton';
import {
  buildVersionLabelState,
  formatCalibrationVersionTitleLabel,
  formatVersionOptionLabel,
  getLatestStableVersion,
  type VersionLabelKind
} from '../lib/versionLabels';

const GROUP_ORDER: ParameterGroup[] = [
  'Housing & Rental Market',
  'Household Demographics & Wealth',
  'Government & Tax',
  'Purchase & Mortgage',
  'Bank & Credit Policy',
  'BTL & Investor Behavior'
];
const DEFAULT_OPEN_COMPARE_CARD_IDS = new Set<string>([
  'house_price_lognormal',
  'wealth_given_income_joint',
  'downpayment_ftb_lognormal'
]);
const DEFAULT_OPEN_COMPARE_GROUPS = new Set<ParameterGroup>([
  'Housing & Rental Market',
  'Household Demographics & Wealth',
  'Purchase & Mortgage'
]);

type ChangeFilter = 'all' | 'updated' | 'unchanged';
type ViewMode = 'single' | 'compare';

function getDefaultDisplayVersion(versions: string[], inProgressVersions: string[]): string {
  return getLatestStableVersion(versions, inProgressVersions) || (versions[versions.length - 1] ?? '');
}

function getOriginalDisplayVersion(versions: string[]): string {
  return versions.includes('v0') ? 'v0' : (versions[0] ?? '');
}

function getVersionTagClassName(kind: VersionLabelKind): string {
  switch (kind) {
    case 'in_progress':
      return 'status-pill-in-progress';
    case 'latest':
      return 'status-pill status-pill-latest';
    case 'original':
      return 'status-pill status-pill-original';
  }
}

function getVersionTagText(prefix: string, version: string, kind: VersionLabelKind): string {
  switch (kind) {
    case 'in_progress':
      return `${prefix} ${version} in progress`;
    case 'latest':
      return `${prefix} ${version} latest`;
    case 'original':
      return `${prefix} ${version} original`;
  }
}

function groupCatalog(catalog: ParameterCardMeta[]) {
  const grouped = new Map<string, ParameterCardMeta[]>();
  for (const item of catalog) {
    const current = grouped.get(item.group) ?? [];
    current.push(item);
    grouped.set(item.group, current);
  }
  return grouped;
}

function isUpdated(item: CompareResponse['items'][number], mode: ViewMode): boolean {
  if (mode === 'single') {
    return item.changeOriginsInRange.length > 0;
  }
  return !item.unchanged;
}

function groupCompareItems(compareData: CompareResponse | null, filter: ChangeFilter, mode: ViewMode) {
  const grouped = new Map<ParameterGroup, CompareResponse['items']>();
  if (!compareData) {
    return grouped;
  }

  for (const item of compareData.items) {
    const updated = isUpdated(item, mode);
    const include = filter === 'all' || (filter === 'updated' ? updated : !updated);
    if (!include) {
      continue;
    }

    const current = grouped.get(item.group) ?? [];
    current.push(item);
    grouped.set(item.group, current);
  }

  return grouped;
}

export function ComparePage() {
  const [searchParams] = useSearchParams();
  const searchParamsKey = searchParams.toString();
  const [versions, setVersions] = useState<string[]>([]);
  const [inProgressVersions, setInProgressVersions] = useState<string[]>([]);
  const [catalog, setCatalog] = useState<ParameterCardMeta[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<string>('');
  const [left, setLeft] = useState<string>('');
  const [right, setRight] = useState<string>('');
  const [mode, setMode] = useState<ViewMode>('single');
  const [search, setSearch] = useState<string>('');
  const [compareData, setCompareData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string>('');
  const [isBootstrapping, setIsBootstrapping] = useState<boolean>(true);
  const [isBootstrapReady, setIsBootstrapReady] = useState<boolean>(false);
  const [isWaitingForApi, setIsWaitingForApi] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSetupOpen, setIsSetupOpen] = useState<boolean>(false);
  const [changeFilter, setChangeFilter] = useState<ChangeFilter>('all');
  const [sectionOpen, setSectionOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    const load = async () => {
      setError('');
      setIsBootstrapping(true);
      setIsWaitingForApi(false);

      try {
        const [versionsPayload, catalogList] = await Promise.all([fetchVersions(), fetchCatalog()]);
        if (cancelled) {
          return;
        }

        const versionList = versionsPayload.versions;
        const defaultDisplayVersion = getDefaultDisplayVersion(versionList, versionsPayload.inProgressVersions);
        const currentParams = new URLSearchParams(searchParamsKey);
        const requestedModeRaw = currentParams.get('mode')?.trim() ?? '';
        const hasRequestedMode = requestedModeRaw.length > 0;
        const requestedMode: ViewMode = hasRequestedMode
          ? requestedModeRaw === 'compare'
            ? 'compare'
            : 'single'
          : 'compare';
        const requestedVersionRaw = currentParams.get('version')?.trim() ?? '';
        const requestedVersion = versionList.includes(requestedVersionRaw) ? requestedVersionRaw : '';
        const singleVersion = requestedVersion || defaultDisplayVersion;
        const defaultCompareLeftVersion = getOriginalDisplayVersion(versionList);
        const compareLeftVersion = hasRequestedMode ? (versionList[0] ?? '') : defaultCompareLeftVersion;
        const compareRightVersion = requestedVersion || defaultDisplayVersion;

        setVersions(versionList);
        setInProgressVersions(versionsPayload.inProgressVersions);
        setCatalog(catalogList);
        setSelectedIds(catalogList.map((item) => item.id));
        setMode(requestedMode);
        setSelectedVersion(singleVersion);
        setLeft(compareLeftVersion);
        setRight(compareRightVersion);
        setIsBootstrapReady(true);
        setIsBootstrapping(false);
      } catch (loadError) {
        if (cancelled) {
          return;
        }

        if (isRetryableApiError(loadError)) {
          setIsWaitingForApi(true);
          setIsBootstrapReady(false);
          setIsBootstrapping(false);
          retryTimer = window.setTimeout(() => {
            void load();
          }, API_RETRY_DELAY_MS);
          return;
        }

        setError((loadError as Error).message);
        setIsBootstrapReady(false);
        setIsBootstrapping(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
    };
  }, [searchParamsKey]);

  useEffect(() => {
    if (mode === 'compare') {
      if (!left && versions.length > 0) {
        setLeft(versions[0]);
      }
      if (!right && versions.length > 0) {
        setRight(getDefaultDisplayVersion(versions, inProgressVersions));
      }
    }
  }, [mode, left, right, versions, inProgressVersions]);

  useEffect(() => {
    if (!isBootstrapReady) {
      setCompareData(null);
      return;
    }

    let cancelled = false;
    let retryTimer: number | undefined;

    const run = async () => {
      if (selectedIds.length === 0) {
        setCompareData(null);
        setIsWaitingForApi(false);
        return;
      }

      if (mode === 'single') {
        if (!selectedVersion) {
          setCompareData(null);
          setIsWaitingForApi(false);
          return;
        }

        setIsLoading(true);
        setIsWaitingForApi(false);
        setError('');
        try {
          const payload = await fetchCompare(selectedVersion, selectedVersion, selectedIds, 'through_right');
          if (cancelled) {
            return;
          }
          setCompareData(payload);
        } catch (loadError) {
          if (cancelled) {
            return;
          }
          if (isRetryableApiError(loadError)) {
            setIsWaitingForApi(true);
            retryTimer = window.setTimeout(() => {
              void run();
            }, API_RETRY_DELAY_MS);
            return;
          }
          setIsWaitingForApi(false);
          setError((loadError as Error).message);
        } finally {
          if (!cancelled) {
            setIsLoading(false);
          }
        }
        return;
      }

      if (!left || !right) {
        setCompareData(null);
        setIsWaitingForApi(false);
        return;
      }

      setIsLoading(true);
      setIsWaitingForApi(false);
      setError('');
      try {
        const payload = await fetchCompare(left, right, selectedIds, 'range');
        if (cancelled) {
          return;
        }
        setCompareData(payload);
      } catch (loadError) {
        if (cancelled) {
          return;
        }
        if (isRetryableApiError(loadError)) {
          setIsWaitingForApi(true);
          retryTimer = window.setTimeout(() => {
            void run();
          }, API_RETRY_DELAY_MS);
          return;
        }
        setIsWaitingForApi(false);
        setError((loadError as Error).message);
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
    };
  }, [isBootstrapReady, mode, left, right, selectedVersion, selectedIds]);

  const filteredCatalog = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) {
      return catalog;
    }
    return catalog.filter(
      (item) =>
        item.title.toLowerCase().includes(term) ||
        item.id.toLowerCase().includes(term) ||
        item.configKeys.some((key) => key.toLowerCase().includes(term))
    );
  }, [catalog, search]);

  const setupGrouped = useMemo(() => groupCatalog(filteredCatalog), [filteredCatalog]);
  const setupSections = useMemo(
    () =>
      [...setupGrouped.entries()].map(([groupName, entries]) => ({
        id: groupName,
        title: groupName,
        items: entries.map((entry) => ({
          id: entry.id,
          label: entry.title,
          checked: selectedIds.includes(entry.id)
        }))
      })),
    [selectedIds, setupGrouped]
  );

  const groupedResults = useMemo(() => groupCompareItems(compareData, changeFilter, mode), [compareData, changeFilter, mode]);

  const sectionCounts = useMemo(() => {
    const counts = new Map<ParameterGroup, { updated: number; unchanged: number }>();
    if (!compareData) {
      return counts;
    }
    for (const item of compareData.items) {
      const current = counts.get(item.group) ?? { updated: 0, unchanged: 0 };
      if (isUpdated(item, mode)) {
        current.updated += 1;
      } else {
        current.unchanged += 1;
      }
      counts.set(item.group, current);
    }
    return counts;
  }, [compareData, mode]);

  useEffect(() => {
    if (!compareData) {
      return;
    }

    setSectionOpen((current) => {
      if (Object.keys(current).length === 0) {
        const seeded: Record<string, boolean> = {};
        for (const groupName of GROUP_ORDER) {
          seeded[groupName] = DEFAULT_OPEN_COMPARE_GROUPS.has(groupName);
        }
        return seeded;
      }

      let changed = false;
      const nextState = { ...current };
      for (const groupName of GROUP_ORDER) {
        if (!(groupName in nextState)) {
          nextState[groupName] = false;
          changed = true;
        }
      }
      return changed ? nextState : current;
    });
  }, [compareData]);

  const toggleId = (id: string) => {
    setSelectedIds((current) => {
      if (current.includes(id)) {
        return current.filter((value) => value !== id);
      }
      return [...current, id];
    });
  };

  const toggleAll = () => {
    if (selectedIds.length === catalog.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(catalog.map((item) => item.id));
    }
  };

  const shownCount = compareData
    ? compareData.items.filter((item) =>
        changeFilter === 'all' ? true : changeFilter === 'updated' ? isUpdated(item, mode) : !isUpdated(item, mode)
      ).length
    : 0;

  const hasComparedItems = (compareData?.items.length ?? 0) > 0;
  const isLoadingWithoutData = isBootstrapping || (isLoading && !hasComparedItems);
  const isRefreshingComparedItems = isLoading && hasComparedItems;
  const inProgressSet = useMemo(() => new Set(inProgressVersions), [inProgressVersions]);
  const latestStableVersion = useMemo(() => getLatestStableVersion(versions, inProgressVersions), [versions, inProgressVersions]);
  const getVersionLabelState = (version: string) => buildVersionLabelState(version, latestStableVersion, inProgressSet);
  const formatTitleLabel = (version: string) => formatCalibrationVersionTitleLabel(version, getVersionLabelState(version));
  const titleText =
    mode === 'single'
      ? selectedVersion
        ? `Model parameters at ${formatTitleLabel(selectedVersion)}`
        : ''
      : left && right
        ? `${formatTitleLabel(left)} vs ${formatTitleLabel(right)}`
        : '';
  const isTitleLoading = isBootstrapping || titleText.length === 0;
  const formatSelectLabel = (version: string) => formatVersionOptionLabel(version, getVersionLabelState(version));
  const renderVersionTags = (prefix: string, version: string) =>
    getVersionLabelState(version).kinds.map((kind) => (
      <span key={`${prefix}-${version}-${kind}`} className={getVersionTagClassName(kind)}>
        {getVersionTagText(prefix, version, kind)}
      </span>
    ));
  const selectedVersionTags =
    mode === 'single'
      ? renderVersionTags('Version', selectedVersion)
      : [...renderVersionTags('Left', left), ...renderVersionTags('Right', right)];

  return (
    <section className={`compare-layout ${isSetupOpen ? '' : 'setup-collapsed'}`}>
      {isSetupOpen ? (
        <aside className="sidebar">
          <div className="sidebar-head">
            <h2>Workspace Setup</h2>
            <div className="sidebar-head-actions">
              <p>{selectedIds.length} tracked</p>
              <button
                type="button"
                className="sidebar-icon-toggle"
                onClick={() => setIsSetupOpen(false)}
                aria-label="Collapse setup panel"
                title="Collapse setup"
              >
                ◂
              </button>
            </div>
          </div>

          <label>Mode</label>
          <div className="mode-switch-row">
            <button
              type="button"
              className={`filter-pill ${mode === 'single' ? 'active' : ''}`}
              onClick={() => setMode('single')}
            >
              Single version
            </button>
            <button
              type="button"
              className={`filter-pill ${mode === 'compare' ? 'active' : ''}`}
              onClick={() => setMode('compare')}
            >
              Compare versions
            </button>
          </div>

          {mode === 'single' ? (
            <>
              <label htmlFor="single-version">Version</label>
              <select id="single-version" value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)}>
                {versions.map((version) => (
                  <option key={version} value={version}>
                    {formatSelectLabel(version)}
                  </option>
                ))}
              </select>
            </>
          ) : (
            <>
              <label htmlFor="left-version">Left version</label>
              <select id="left-version" value={left} onChange={(event) => setLeft(event.target.value)}>
                {versions.map((version) => (
                  <option key={version} value={version}>
                    {formatSelectLabel(version)}
                  </option>
                ))}
              </select>

              <label htmlFor="right-version">Right version</label>
              <select id="right-version" value={right} onChange={(event) => setRight(event.target.value)}>
                {versions.map((version) => (
                  <option key={version} value={version}>
                    {formatSelectLabel(version)}
                  </option>
                ))}
              </select>
            </>
          )}

          <label htmlFor="search-params">Find parameters</label>
          <input
            id="search-params"
            placeholder="Search title or key"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />

          <CollapsibleSection
            title="Parameter filters"
            defaultOpen={false}
            summary={`${selectedIds.length} selected`}
            className="compare-filter-disclosure"
            bodyClassName="compare-filter-disclosure-body"
          >
            <button type="button" className="secondary-button" onClick={toggleAll}>
              {selectedIds.length === catalog.length ? 'Clear all' : 'Select all'}
            </button>

            <GroupedCheckboxSections sections={setupSections} onToggle={toggleId} />
          </CollapsibleSection>
        </aside>
      ) : (
        <button
          type="button"
          className="setup-rail-toggle"
          onClick={() => setIsSetupOpen(true)}
          aria-label="Open workspace setup"
          title="Open workspace setup"
        >
          <svg viewBox="0 0 24 24" role="img" aria-hidden="true" focusable="false">
            <path
              d="M10.255 4.18806C9.84269 5.17755 8.68655 5.62456 7.71327 5.17535C6.10289 4.4321 4.4321 6.10289 5.17535 7.71327C5.62456 8.68655 5.17755 9.84269 4.18806 10.255C2.63693 10.9013 2.63693 13.0987 4.18806 13.745C5.17755 14.1573 5.62456 15.3135 5.17535 16.2867C4.4321 17.8971 6.10289 19.5679 7.71327 18.8246C8.68655 18.3754 9.84269 18.8224 10.255 19.8119C10.9013 21.3631 13.0987 21.3631 13.745 19.8119C14.1573 18.8224 15.3135 18.3754 16.2867 18.8246C17.8971 19.5679 19.5679 17.8971 18.8246 16.2867C18.3754 15.3135 18.8224 14.1573 19.8119 13.745C21.3631 13.0987 21.3631 10.9013 19.8119 10.255C18.8224 9.84269 18.3754 8.68655 18.8246 7.71327C19.5679 6.10289 17.8971 4.4321 16.2867 5.17535C15.3135 5.62456 14.1573 5.17755 13.745 4.18806C13.0987 2.63693 10.9013 2.63693 10.255 4.18806Z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M15 12C15 13.6569 13.6569 15 12 15C10.3431 15 9 13.6569 9 12C9 10.3431 10.3431 9 12 9C13.6569 9 15 10.3431 15 12Z"
              stroke="currentColor"
              strokeWidth="2"
            />
          </svg>
        </button>
      )}

      <div className="compare-results">
        <section className="summary-panel">
          <h2>Parameter Calibration Workspace</h2>
          <p>
            This page exists to visualize calibrated model parameters and to track iterative project progress as inputs are
            refined over versions. Single-version mode is the default for reviewing the current state; compare mode is
            available when you need version-to-version deltas.
          </p>
        </section>

        <header className="results-head">
          <h2>
            {isTitleLoading ? (
              <LoadingSkeleton as="span" className="loading-skeleton-line compare-title-skeleton" ariaLabel="Loading selected versions" />
            ) : (
              titleText
            )}
          </h2>
          {selectedVersionTags.length > 0 && (
            <div className="results-version-tags">
              {selectedVersionTags}
            </div>
          )}
          <p>Explore how the model's assumptions have changed over time and where each update came from.</p>

          <div className="change-filter-row">
            <span>Filter:</span>
            <button
              type="button"
              className={`filter-pill ${changeFilter === 'all' ? 'active' : ''}`}
              onClick={() => setChangeFilter('all')}
            >
              All
            </button>
            <button
              type="button"
              className={`filter-pill ${changeFilter === 'updated' ? 'active' : ''}`}
              onClick={() => setChangeFilter('updated')}
            >
              Updated
            </button>
            <button
              type="button"
              className={`filter-pill ${changeFilter === 'unchanged' ? 'active' : ''}`}
              onClick={() => setChangeFilter('unchanged')}
            >
              No change
            </button>
            <strong>
              {isLoadingWithoutData ? (
                <LoadingSkeleton as="span" className="loading-skeleton-line compare-count-skeleton" ariaLabel="Loading filtered count" />
              ) : (
                shownCount
              )}
            </strong>
          </div>
          {isRefreshingComparedItems && (
            <LoadingSkeleton as="span" className="loading-skeleton-pill compare-refresh-pill" ariaLabel="Refreshing parameter comparison" />
          )}
        </header>

        {error && <p className="error-banner">{error}</p>}
        {isWaitingForApi && (
          <p className="waiting-banner">Waiting for API to become available. Retrying every 2 seconds...</p>
        )}

        {!isBootstrapping && !isLoading && (selectedIds.length === 0 || compareData?.items.length === 0) && (
          <p className="info-banner">No parameters selected.</p>
        )}

        {isLoadingWithoutData ? (
          <LoadingSkeletonGroup
            className="cards-stack-skeleton"
            count={4}
            itemClassName="loading-skeleton-card result-group-skeleton"
            ariaLabel="Loading parameter groups"
          />
        ) : (
          <div className="cards-stack">
            {GROUP_ORDER.filter((group) => (groupedResults.get(group)?.length ?? 0) > 0).map((groupName) => {
              const items = groupedResults.get(groupName) ?? [];
              const counts = sectionCounts.get(groupName) ?? { updated: 0, unchanged: 0 };
              const open = sectionOpen[groupName] ?? false;

              return (
                <section className="result-group" key={groupName}>
                  <button
                    type="button"
                    className="result-group-header"
                    onClick={() =>
                      setSectionOpen((current) => ({
                        ...current,
                        [groupName]: !open
                      }))
                    }
                  >
                    <span className="result-group-title">
                      {open ? '▾' : '▸'} {groupName}
                    </span>
                    <span className="result-group-counts">
                      <span className="unchanged">No change: {counts.unchanged}</span>
                      <span className="updated">Updated: {counts.updated}</span>
                    </span>
                  </button>

                  {open && (
                    <div className="result-group-body">
                      {items.map((item) => (
                        <CompareCard
                          key={item.id}
                          item={item}
                          mode={mode}
                          inProgressVersions={inProgressVersions}
                          defaultExpanded={DEFAULT_OPEN_COMPARE_CARD_IDS.has(item.id)}
                        />
                      ))}
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
