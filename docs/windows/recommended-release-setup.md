---
title: Windows Release Agent Phase Plan
author: Max Stoddard
status: recommended-target
target_platform: windows
last_reviewed: 2026-05-08
architecture_version: 2
first_release: v0.1.0
---

# Windows Release Agent Phase Plan

Author: Max Stoddard

This artifact defines the recommended execution plan for a future Windows release of the UK housing model dashboard. It is not a statement of current repo capability. The current repository is still a developer-oriented runtime: it does not yet contain an Electron shell, Windows installer workflow, runnable model jar packaging, desktop-owned server lifecycle, or packaged-runtime path abstraction.

The goal is to let a Windows user install once, launch the dashboard, and run dashboard-managed Java model experiments locally without installing Node.js, Maven, Java, Git, or using a terminal workflow. This should improve accessibility and reproducibility without changing Java model behavior.

For v1, "experiments" means:

- Dashboard-managed manual Java model runs.
- Dashboard-managed one-at-a-time sensitivity runs.
- Viewing results, run logs, sensitivity summaries, and dashboard-facing validation/provenance summaries.

For v1, "experiments" does not mean:

- Bash or Python calibration workflows.
- Full validation regeneration.
- Workflows requiring `private-datasets/`.
- Long sharded research sweeps using `gnu parallel`, Linux shell tools, WSL-only paths, or Python private-data helpers.
- Remote Render, AWS API, or other public cloud model execution.

WSL2, Docker, AWS EC2, AWS Batch, or a remote Linux runner remain better fits for heavy research workflows, calibration, validation regeneration, and long experiment sweeps. The Windows desktop release should focus on small-to-medium local dashboard workflows.

## How To Use This Plan

Future agents should execute one phase at a time unless the user explicitly asks for multiple phases in one prompt.

Use this prompt pattern:

```text
execute phase <n> of docs/windows/recommended-release-setup.md
```

Each phase is scoped so one agent prompt can complete it, including implementation, local validation, and a concise summary of changed files and checks. If a phase discovers that this document is wrong, outdated, or missing a required instruction, update this document in the same change and alert the user.

Do not skip model-validity checks. Any change to `src/main/java/` must be minimal, packaging/runtime-entrypoint focused, and covered by `mvn test` plus the regression checks defined below.

## Execution Isolation And Context Rules

Before executing Phase 1, create a dedicated git worktree and branch for the full Windows release effort, for example `git worktree add ../uk-housing-model-windows-release -b feat/windows-release-v0.1.0`. All phase work, commands, builds, generated artifacts, and validation must run from that dedicated worktree. Treat the original checkout as a shared repo where other contributors or agents may be working; do not make Windows release phase changes there.

The phase agent should assume it is not alone in the source repository but is alone inside the dedicated worktree. Do not merge the Windows release work back into the original checkout or main branch until the selected release phases are complete, validated, and reviewed. Merge only after the final acceptance checks for the completed scope pass.

At every phase, use as many GPT-5.5 xhigh subagents as practical to keep the lead agent context clean. Prefer subagents for independent codebase audits, implementation slices with disjoint write scopes, test/log analysis, documentation review, and release-package inspection. Each subagent must work only inside the dedicated worktree, avoid prohibited paths such as `agents/`, respect the `private-datasets/` CSV limits, and return concise findings plus changed-file lists rather than large copied context.

## Target Architecture Constraints

These decisions are locked for the first Windows release unless the user explicitly changes this plan.

- First Windows release version: `v0.1.0`.
- Distribution: GitHub Releases.
- Release trigger: the first release is built from tag `v0.1.0`; later releases use the same `v*` tag flow.
- Release assets: installer EXE, release manifest, and SHA256 checksums are attached to a draft GitHub Release.
- Signing: v1 is unsigned. The release documentation must explain SmartScreen expectations and checksum verification.
- Installer target: a complete offline Windows package for dashboard manual and sensitivity runs.
- Installer technology: `electron-builder` `nsis` single-file installer EXE. Do not use `nsis-web` for v1 because the installer must work offline.
- Desktop shell: Electron.
- Frontend: built React dashboard from `dashboard/dist`, served by the local Express server in desktop mode.
- API: constructible Express server owned by Electron, bound only to `127.0.0.1` on a random available local port.
- Desktop auth: constructible server accepts a non-empty per-session bearer token in desktop mode; Electron generates the token and exposes it to the renderer only through a narrow preload/contextBridge API; no static write credentials; no packaged dev write bypass.
- Model runtime: bundled Java 25 runtime image; users do not need system Java or Maven.
- Model artifact: runnable fat jar with `Main-Class: housing.Model`.
- Model launcher: packaged mode directly spawns the bundled Java executable with separate args and `shell: false`.
- Release data: allowlisted `release-data` directory, not a blind copy of the repository.
- Results, temp files, logs, manifests, summaries, and support bundles: written under Electron `userData`, not the install directory.
- Public cloud compatibility: the Windows desktop path remains separate from AWS public deployment. Public cloud/API mode keeps model execution disabled by default per `docs/cloud/recommended-aws-setup.md`.

The packaged launcher must preserve the current `housing.Model` command-line behavior for `-configFile`, `-outputFolder`, and `-dev`. Desktop runs must always pass an explicit generated config file and output folder. Packaged runs must not rely on the model default `src/main/resources/config.properties`.

## Phase 1 - Baseline Audit

**Goal**

Create a concise implementation audit that maps current code to this release plan before making runtime changes.

**Prerequisites**

- Read `AGENTS.md`.
- Read this document.
- Create and enter the dedicated Windows release worktree before any audit or implementation work.
- Do not read `agents/`.
- Do not read full CSV files under `private-datasets/`.

**Implementation Scope**

- Inventory the current dashboard server entrypoint, route registration, auth behavior, diagnostics, model-run launcher, sensitivity-run launcher, result readers, cleanup/storage-cap logic, and CI workflows.
- Identify every current hard-coded repo path used by dashboard runtime code.
- Identify current Java launch behavior and Maven packaging behavior.
- Identify public API/container behavior that must remain compatible with AWS deployment.
- Record the dedicated worktree path and branch in the audit.
- Record specific files and current gaps in a short markdown audit, preferably under an existing docs location. Do not create ad hoc `AGENTS.md`, `AGENT*.md`, or `tmp/` notes.

**Likely Areas**

- `dashboard/server/`
- `dashboard/src/`
- `dashboard/package.json`
- `dashboard/Dockerfile.api`
- `.github/workflows/`
- `pom.xml`
- `src/main/java/`

**Acceptance Checks**

- The audit names the concrete files that later phases will edit.
- The audit distinguishes desktop-only changes from shared dashboard/server changes.
- The audit confirms current public API model execution remains disabled unless explicitly configured.
- The audit confirms all future Windows release phase work will happen from the dedicated worktree until validated and ready to merge.
- No model behavior changes are made in this phase.

**Model-Validity Guardrails**

- Do not change Java code.
- Do not change calibration, validation, or experiment logic.
- Flag any later phase that appears likely to alter economic model behavior.

**Cloud-Compatibility Guardrails**

- Preserve the lightweight public API posture documented in `docs/cloud/recommended-aws-setup.md`.
- Do not add AWS deployment automation in this phase.

## Phase 2 - Java Fat Jar Artifact

**Goal**

Add a release-time Maven packaging path that creates a runnable fat jar for the existing model entrypoint.

**Prerequisites**

- Phase 1 complete.
- Confirm the current Java main class remains `housing.Model`.

**Implementation Scope**

- Configure Maven to produce a runnable fat jar with `Main-Class: housing.Model`.
- Keep Maven `exec:java` available for local development.
- Do not move input files into Java classpath resources.
- Do not change model logic or default model behavior.
- Add or update documentation for the release jar build command.

**Likely Areas**

- `pom.xml`
- Existing Java build/test docs if relevant.

**Acceptance Checks**

- `mvn test` passes.
- The fat jar is produced by the documented Maven command.
- The fat jar accepts `-configFile`, `-outputFolder`, and `-dev`.
- A short manual or scripted smoke launch proves the jar starts with an explicit config and output folder.

**Model-Validity Guardrails**

- Java changes must be packaging-only.
- If any `src/main/java/` change is required, explain why and add targeted tests.

**Cloud-Compatibility Guardrails**

- Do not add Java, Maven, or the fat jar to the public API Docker image.
- Keep `dashboard/Dockerfile.api` lightweight unless a later phase explicitly changes image hygiene checks.

## Phase 3 - Packaged Launcher

**Goal**

Introduce a shared dashboard-side model launcher abstraction with development Maven mode and packaged fat-jar mode.

**Prerequisites**

- Phase 2 complete.
- Phase 1 has identified all current model-run and sensitivity-run launch points.

**Implementation Scope**

- Add a launcher API used by manual runs and sensitivity runs.
- Development mode continues to use Maven.
- Packaged mode uses the bundled Java executable and fat jar.
- Packaged mode must call `spawn(javaExe, args, { shell: false })` or equivalent safe separate-argument spawning.
- Packaged mode must pass explicit generated config and output folder args.
- Packaged mode must use unique output directories or pre-delete dashboard-owned output directories before launch.
- Packaged mode must never fall back to `src/main/resources/config.properties`.

**Likely Areas**

- `dashboard/server/lib/modelRuns.ts`
- `dashboard/server/lib/sensitivityRuns.ts`
- New launcher helper under `dashboard/server/lib/`
- Dashboard server tests or smoke tests where available.

**Acceptance Checks**

- Manual runs and sensitivity runs both use the shared launcher.
- Existing local development Maven behavior still works.
- Packaged launcher args are separate array entries, not one quoted shell command string.
- Run cancellation still terminates the child process.

**Model-Validity Guardrails**

- The launcher may change how the process starts, but not model parameters, generated config semantics, or output interpretation.
- Any output-folder cleanup must be limited to dashboard-owned run directories.

**Cloud-Compatibility Guardrails**

- Production public API must still keep model execution disabled unless explicitly configured.
- Public API builds must not require the packaged Java runtime or fat jar.

## Phase 4 - Regression Harness And Windows Paths

**Goal**

Prove that Maven launch and packaged fat-jar launch produce equivalent deterministic outputs and that generated config paths are Windows-safe.

**Prerequisites**

- Phase 3 complete.
- Identify or create a short deterministic smoke configuration that does not require private data.

**Implementation Scope**

- Add a regression harness that runs the same generated config and seed through Maven mode and packaged fat-jar mode.
- Compare stable output hashes or an approved KPI summary hash.
- Add tests for generated `.properties` files containing paths with spaces.
- Add tests for generated `.properties` files containing non-ASCII user path segments.
- Add launch tests where both the Java CLI `-configFile` path and `-outputFolder` path contain spaces and non-ASCII user path segments.
- Verify the model writes the expected output files under the requested `-outputFolder` and copies the generated `config.properties` there.
- Prefer forward slashes for Windows paths written to Java properties; otherwise escape backslashes correctly for `Properties.load`.

**Likely Areas**

- Dashboard server test/smoke infrastructure.
- Model-run config generation helpers.
- CI scripts or package scripts for release regression checks.

**Acceptance Checks**

- The harness fails clearly when outputs diverge.
- The harness verifies both launch modes use the same generated config and seed.
- Windows path tests cover spaces and non-ASCII usernames for generated config paths and Java CLI output-folder paths.
- Generated configs contain explicit data paths under the configured data root.
- Maven and fat-jar launches both succeed from output folders containing spaces and non-ASCII path segments, with expected outputs and copied config present.

**Model-Validity Guardrails**

- Treat any Maven-vs-jar output difference as a release blocker until explained.
- Do not relax comparisons without documenting why the compared outputs are stable and meaningful.

**Cloud-Compatibility Guardrails**

- Keep the regression harness separate from public API container startup.
- If CI runs this harness, scope it to Java/package changes or release workflows to avoid slowing unrelated dashboard-only checks unnecessarily.

## Phase 5 - RuntimePaths Foundation

**Goal**

Introduce explicit runtime roots for data, results, temp files, and logs across dashboard server behavior.

**Prerequisites**

- Phase 1 complete.
- Phase 3 complete if launcher paths are being wired at the same time.

**Implementation Scope**

- Add a shared `RuntimePaths` object or equivalent typed configuration.
- Development defaults:
  - data root: `<repo>/input-data-versions`
  - results root: `<repo>/Results`
  - temp root: `<repo>/tmp`
  - logs root: `<repo>/tmp/dashboard-logs`
- Desktop defaults:
  - data root: `<app resources>/release-data/input-data-versions`
  - results root: `<Electron userData>/Results`
  - temp root: `<Electron userData>/tmp`
  - logs root: `<Electron userData>/logs`
- Use runtime paths in input-data services, manual runs, sensitivity runs, result readers, deletion, cleanup/storage-cap logic, diagnostics, and support-bundle preparation.
- Ensure the installed app never writes to app resources or Program Files.

**Likely Areas**

- `dashboard/server/lib/io.ts`
- `dashboard/server/lib/results.ts`
- `dashboard/server/lib/modelRuns.ts`
- `dashboard/server/lib/sensitivityRuns.ts`
- `dashboard/server/lib/runtimeDeps.ts`
- Route context types.

**Acceptance Checks**

- Development behavior still reads and writes the same repo paths by default.
- Desktop configuration can redirect all writable paths to Electron `userData`.
- No write path points under app resources in desktop mode.
- Result deletion and cleanup only affect dashboard-owned paths.

**Model-Validity Guardrails**

- Data-root changes must not silently switch input-data versions.
- Generated configs must record the exact data root used for each run.

**Cloud-Compatibility Guardrails**

- Container/public API defaults must still work in the repo-shaped `/app` layout.
- Do not require Electron paths in public API mode.

## Phase 6 - Run Manifests And Diagnostics

**Goal**

Persist enough metadata for reproducibility and expose desktop diagnostics that explain missing runtime pieces clearly.

**Prerequisites**

- Phase 5 complete.
- Phase 3 complete.

**Implementation Scope**

- Write a dashboard-owned manifest next to each manual run and sensitivity summary.
- Include, where practical:
  - app version and release channel
  - Git commit SHA used to build the release
  - Java model artifact hash
  - Java runtime vendor and version
  - launcher mode: Maven or fat jar
  - input data package checksum or manifest hash
  - baseline snapshot
  - generated config hash
  - run seed and key overridden parameters
  - output hash or approved KPI summary hash
- Expand runtime diagnostics for desktop mode:
  - configured Java binary
  - model artifact
  - data root
  - results root writability
  - temp root writability
  - logs root writability
  - Java major version
- Keep `/api/runtime-deps` useful in cloud mode even when Java/Maven are intentionally absent.

**Likely Areas**

- `dashboard/server/lib/runtimeDeps.ts`
- `dashboard/server/lib/modelRuns.ts`
- `dashboard/server/lib/sensitivityRuns.ts`
- Result metadata types.

**Acceptance Checks**

- Missing fat jar is reported clearly.
- Missing bundled Java runtime is reported clearly.
- Missing data root is reported clearly.
- Unwritable results, temp, or logs root is reported clearly.
- Manifests are preserved across app restart.

**Model-Validity Guardrails**

- Manifests must make it possible to tie persisted outputs to the exact release, model artifact, input data, config, and seed.

**Cloud-Compatibility Guardrails**

- Public API runtime may report Java/Maven missing; that remains acceptable when `DASHBOARD_ENABLE_MODEL_RUNS=false`.

## Phase 7 - Server Lifecycle And Static Serving

**Goal**

Make the dashboard server constructible so Electron can own startup and shutdown, and serve the built dashboard UI in desktop mode.

**Prerequisites**

- Phase 5 complete.

**Implementation Scope**

- Expose a server startup API similar to `startDashboardServer({ host, port, paths, auth, launcher })`.
- Return the actual selected port and a shutdown handle.
- Avoid starting the server at module load.
- Desktop mode binds to `127.0.0.1`.
- Desktop mode uses port `0` or another random available local port.
- Keep production/container startup compatible with the existing server command.
- Serve `dashboard/dist` in desktop mode.
- Add SPA fallback to `index.html` in desktop mode.

**Likely Areas**

- `dashboard/server/index.ts`
- New server bootstrap helper under `dashboard/server/`
- Route context types.

**Acceptance Checks**

- Existing `npm run start:server` still starts the public API server.
- Constructible server can start on `127.0.0.1` with a random port and report the actual port.
- Shutdown handle closes the HTTP server.
- Desktop static serving loads the built dashboard by same-origin URL.

**Model-Validity Guardrails**

- This phase must not change model config generation, launcher semantics, or result interpretation.

**Cloud-Compatibility Guardrails**

- Container mode must still bind according to production settings and remain compatible with AWS ECS/Fargate.
- Public API read routes must continue to work without Electron.

## Phase 8 - Desktop Auth And Logs

**Goal**

Add the desktop server-side write-auth contract and persistent logs suitable for a packaged local app.

**Prerequisites**

- Phase 7 complete.

**Implementation Scope**

- Add a desktop auth mode that accepts a per-session bearer token supplied through constructible server startup options.
- Require a non-empty token when starting in desktop mode; packaged desktop mode must fail closed if token setup is missing or empty.
- Require that token for all write routes in packaged desktop mode.
- Ensure packaged desktop mode never uses dev write bypass.
- Do not ship static write username/password credentials.
- Preserve existing local development auth behavior unless explicitly changed.
- Add persistent app/server/model logs under runtime `logsRoot`.
- Add log rotation so logs cannot grow without bound.

**Likely Areas**

- `dashboard/server/lib/writeAuth.ts`
- Route context/auth wiring.
- Existing log buffer or logging helpers.

**Acceptance Checks**

- Desktop server startup fails if token setup is missing or empty.
- Write routes reject missing or wrong desktop token.
- Write routes accept the configured per-session desktop token.
- Packaged desktop mode has no dev write bypass.
- Logs are written under `logsRoot` and rotate.
- Existing local dev workflow remains usable.

**Model-Validity Guardrails**

- Auth and logging must not alter run parameters or output files.

**Cloud-Compatibility Guardrails**

- Public API must not require Electron token for read-only routes.
- Public API model execution must remain disabled by default.

## Phase 9 - Electron Shell

**Goal**

Add the Electron application shell that owns the local server lifecycle and loads the dashboard.

**Prerequisites**

- Phase 7 complete.
- Phase 8 complete.

**Implementation Scope**

- Add Electron main and preload code.
- Electron main process creates the desktop auth token.
- Electron main process starts the constructible dashboard server with desktop paths, auth, and packaged launcher configuration.
- Preload exposes a narrow desktop API through `contextBridge`, including `window.ukHousingDesktop.getApiAuthToken()`.
- Renderer startup calls the existing `setApiAuthToken(token)` before `fetchAuthStatus()` and before any submit, cancel, or delete write call.
- Renderer loads `http://127.0.0.1:<actual-port>/`.
- Expose safe actions for:
  - Open Results Folder
  - Open Logs Folder
  - Support bundle export hook if diagnostics/support-bundle implementation already exists
- Ensure app shutdown stops the server.
- Ensure cancellation and app exit do not leave orphan Java processes.

**Likely Areas**

- `dashboard/package.json`
- New Electron source under `dashboard/`
- Dashboard UI actions for results/logs folders.

**Acceptance Checks**

- Electron app launches the dashboard without a separate terminal server.
- Electron app exits cleanly.
- Results/logs folder actions open the configured desktop paths.
- Manual run submit, cancel, delete, log polling, and result viewing work with the Electron-provided token.
- Sensitivity experiment submit, cancel, summary writing, and result viewing work with the Electron-provided token.
- Missing or wrong desktop tokens are still rejected in packaged desktop mode.
- Manual run cancellation leaves no orphan Java process.
- System Node is not required for the packaged runtime path.

**Model-Validity Guardrails**

- Electron must delegate model execution through the launcher abstraction, not introduce a second launch path.

**Cloud-Compatibility Guardrails**

- Electron dependencies and desktop-only code must not be required by the public API Docker image.

## Phase 10 - Release Data And Runtime Resources

**Goal**

Assemble the allowlisted `release-data` directory and packaged app runtime resources for the Windows package.

**Prerequisites**

- Phase 2 complete.
- Phase 5 complete.
- Phase 6 complete if `release-data` hashes are emitted.
- Phase 9 complete.

**Implementation Scope**

- Build or collect the runnable fat jar.
- Include a pinned Java 25 runtime image, preferably with vendor/version recorded in the release manifest.
- Assemble allowlisted `release-data`, meaning input data and dashboard metadata only.
- Include in `release-data`:
  - canonical `input-data-versions/v*` folders that contain `config.properties` and runtime data files referenced by those configs
  - `input-data-versions/dashboard-input-version-history.json`
  - `input-data-versions/validation/*.json`
  - `input-data-versions/validation-overlays/*.json`
- Exclude from `release-data` by default:
  - `input-data-versions/tmp/`
  - `private-datasets/`
  - `Results/`
  - root `tmp/`
  - generated app or release artifacts such as installers, jars, `dashboard/dist`, and `dashboard/dist-server`
  - calibration evidence, validation source artifacts, and large supporting source files unless each path has explicit license, privacy, size, and user-value review
- Assemble packaged app resources from the Electron app, built dashboard assets, compiled server, production runtime dependencies, fat jar, Java runtime, and `release-data`.
- Generate a release-data manifest and checksum.

**Likely Areas**

- Release scripts under an appropriate existing scripts or dashboard build location.
- `dashboard/package.json` release scripts.
- Release documentation.

**Acceptance Checks**

- Packaged app resources include the Electron app, built dashboard assets, compiled server, production runtime dependencies, fat jar, Java runtime, and the allowlisted `release-data` directory.
- `release-data` excludes private datasets, generated results, tmp files, local dependency folders, local env files, and operational agent material.
- Release-data manifest lists included paths and checksums.
- App can resolve data root from app resources.

**Model-Validity Guardrails**

- Release data must be explicit and reproducible.
- Do not silently omit runtime files referenced by included configs.

**Cloud-Compatibility Guardrails**

- Keep public API Docker image hygiene aligned with the same exclusion principles.
- Do not package cloud credentials or AWS resources into the desktop package.

## Phase 11 - Installer Packaging

**Goal**

Build the complete unsigned Windows installer for the desktop app.

**Prerequisites**

- Phase 9 complete.
- Phase 10 complete.

**Implementation Scope**

- Add Windows packaging configuration for Electron.
- Use `electron-builder` `nsis` as the Windows installer target.
- Do not use `nsis-web` for v1 because the installer must work offline.
- Produce an unsigned single-file installer EXE for v1.
- Include release manifest and SHA256 checksum generation.
- Ensure installer updates preserve Electron `userData`.
- Ensure install directory is treated as read-only.

**Likely Areas**

- `dashboard/package.json`
- Electron packaging config.
- Release scripts.
- GitHub Actions workflow in the next phase.

**Acceptance Checks**

- Installer builds on Windows.
- Installed app launches from a path containing spaces.
- Installed app works without system Node, Maven, or Java in `PATH`.
- Installed app works for a standard non-admin user.
- Installed app works offline for bundled manual and sensitivity runs.
- App restart preserves results, logs, manifests, and experiment metadata.

**Model-Validity Guardrails**

- Installer packaging must use the same fat jar and release data validated by earlier phases.
- Any installer-specific path transformation must be covered by regression checks.

**Cloud-Compatibility Guardrails**

- No AWS deployment workflow is introduced by this phase.
- Release artifacts must not contain private or cloud-only material.

## Phase 12 - GitHub Release CI/CD

**Goal**

Add the clean GitHub Actions release pipeline that builds and publishes draft GitHub Release assets.

**Prerequisites**

- Phase 11 complete.
- All required release scripts can run locally or on `windows-latest`.

**Implementation Scope**

- Add a separate Windows release workflow, for example `.github/workflows/windows-release.yml`.
- Trigger on:
  - tag `v0.1.0` for the first release
  - later `v*` tags using the same flow
  - optional `workflow_dispatch` for release-candidate validation without publishing
- Run on `windows-latest`.
- Use Node 22 and Java 25 at build time.
- Ordered workflow steps:
  - checkout repository
  - install dashboard dependencies with `npm ci`
  - run dashboard lint
  - run dashboard build
  - run dashboard smoke tests
  - run `mvn test`
  - build fat jar
  - run Maven-vs-packaged-launcher regression check
  - collect pinned Java 25 runtime image
  - assemble allowlisted `release-data` directory
  - assemble Electron resources
  - build unsigned Windows installer
  - run packaged smoke checks from a path containing spaces
  - generate release manifest and SHA256 checksums
  - create or update a draft GitHub Release for the tag
  - upload installer EXE, release manifest, and checksums
- Use `permissions: contents: write` only in this release workflow. Baseline CI should remain `contents: read`.

**Likely Areas**

- `.github/workflows/windows-release.yml`
- `dashboard/package.json`
- Release scripts.

**Acceptance Checks**

- `v0.1.0` tag creates a draft GitHub Release.
- Draft GitHub Release contains the installer EXE, release manifest, and SHA256 checksums.
- Workflow fails if checks or packaged smoke tests fail.
- Workflow does not publish AWS resources or require AWS credentials.
- Workflow documents unsigned release behavior.

**Model-Validity Guardrails**

- Release workflow must block publication when Maven-vs-packaged-launcher regression fails.
- Release manifest must tie app version, commit SHA, model artifact hash, Java runtime version, and `release-data` hash together.

**Cloud-Compatibility Guardrails**

- Do not add AWS deployment steps in this workflow.
- Keep Render/AWS/public API CI separate from Windows release CI.

## Phase 13 - Release Hardening

**Goal**

Complete release-readiness checks and user-facing release documentation for `v0.1.0`.

**Prerequisites**

- Phase 12 complete.

**Implementation Scope**

- Document supported Windows versions and CPU architecture.
- Document GitHub download flow for `v0.1.0`.
- Document checksum verification, including PowerShell `Get-FileHash`.
- Document unsigned installer and expected SmartScreen behavior.
- Document install, launch, update, and uninstall steps.
- Document how to run manual and sensitivity experiments.
- Document where results and logs are stored.
- Document support bundle export.
- Document what is included offline.
- Document what is not included: Python calibration, full validation regeneration, private datasets, heavy research sweeps, and cloud model execution.
- Add or run hardening checks:
  - standard non-admin install
  - offline launch and offline manual/sensitivity runs
  - install and user-data paths with spaces
  - user-data paths with non-ASCII characters
  - update preserves results/logs/manifests
  - missing runtime pieces report clear diagnostics
  - local API listens only on `127.0.0.1`
  - write routes reject missing token
  - no static write credentials embedded

**Likely Areas**

- Release docs under `docs/`.
- GitHub Release notes template if added.
- Smoke/hardening scripts where appropriate.

**Acceptance Checks**

- A user can download `v0.1.0` from GitHub Releases, verify checksums, install, launch, run a manual experiment, run a sensitivity experiment, find results/logs, and understand unsigned installer warnings.
- The app works without system Node, Maven, or Java.
- The app works offline for bundled dashboard runs.
- The app preserves user results and logs across updates.
- Troubleshooting docs explain how to export support information.

**Model-Validity Guardrails**

- Release notes must state that the Windows package improves accessibility and reproducibility without changing Java model behavior.
- Any known model-output caveat must be stated plainly before publication.

**Cloud-Compatibility Guardrails**

- Release docs must not imply public AWS/API model execution is available.
- Point heavy remote workflows to the cloud/EC2 approach in `docs/cloud/recommended-aws-setup.md` only as a separate target.

## CI And Release Summary

The repo should eventually have separate CI/CD responsibilities:

- Existing dashboard CI remains the PR/push gate for dashboard lint, build, smoke tests, and public API container build checks.
- Java/model release checks gate packaging-sensitive changes with `mvn test` and Maven-vs-fat-jar regression.
- Windows release CI is a separate `windows-latest` workflow that builds the complete unsigned installer and publishes draft GitHub Release assets for `v0.1.0` and later `v*` tags.
- AWS deployment CI/CD is not part of this Windows release plan. If added later, it should follow `docs/cloud/recommended-aws-setup.md`, use GitHub OIDC instead of long-lived AWS keys, and keep public model execution disabled by default.

## Final Release Acceptance Checklist

The `v0.1.0` Windows release is acceptable only when these checks pass:

- `mvn test` passes before model artifact packaging.
- Dashboard `npm run lint`, `npm run build`, and `npm run test:smoke` pass.
- The fat jar launches with explicit `-configFile`, `-outputFolder`, and `-dev`.
- Maven-run and packaged-run deterministic outputs match by stable output hash or approved KPI summary comparison.
- Generated configs contain explicit data paths under the packaged data root.
- Packaged runs never fall back to `src/main/resources/config.properties`.
- Packaged app launches without system Node, Maven, or Java.
- App works from install and user-data paths containing spaces.
- App works for a standard non-admin Windows user.
- App works offline for bundled manual and sensitivity runs.
- App handles user-data paths with non-ASCII characters.
- Manual run submission, log polling, cancellation, deletion, and result viewing work.
- Sensitivity run execution, summary writing, result viewing, and cancellation work.
- App restart preserves results, logs, manifests, and experiment metadata.
- Open Results Folder and Open Logs Folder actions work.
- Release data contains only allowlisted runtime data and dashboard metadata.
- No `private-datasets/`, `Results/`, root `tmp/`, local env files, or operational agent material are present in release artifacts.
- Missing model artifact, bundled Java runtime, data root, or writable roots are reported clearly.
- Support bundle includes release manifest, diagnostics, and recent logs.
- Local API listens only on `127.0.0.1`.
- Write routes reject requests without the per-session token.
- Packaged app does not use dev write bypass.
- No static write credentials are embedded.
- GitHub Release assets include installer EXE, release manifest, and SHA256 checksums.
- Draft GitHub Release for `v0.1.0` documents unsigned installer behavior and checksum verification.
