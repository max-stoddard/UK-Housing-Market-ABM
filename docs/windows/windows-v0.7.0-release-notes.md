---
title: Windows v0.7.0 Release Notes
author: Max Stoddard
status: release-candidate
target_platform: windows
release: v0.7.0
---

# Windows v0.7.0 Release Notes

Author: Max Stoddard

## Summary

`v0.7.0` updates the UK Housing Model dashboard results view so the manual experiment Window setting controls both aggregate KPI calculations and indicator overlays. The default manual results window is now `post500`, focusing comparisons on model ticks from 500 onward.

This release changes dashboard result interpretation only. It does not change Java model behavior, calibration logic, generated config semantics, or input data.

## Release Assets

- `UK-Housing-Model-0.7.0-Setup.exe`
- `release-manifest.json`
- `SHA256SUMS.txt`
- `UK-Housing-Model-0.7.0-Setup.exe.sha256`

Verify the installer with PowerShell before installing:

```powershell
Get-FileHash .\UK-Housing-Model-0.7.0-Setup.exe -Algorithm SHA256
```

Compare the result with `SHA256SUMS.txt` and `UK-Housing-Model-0.7.0-Setup.exe.sha256`.

## Results Window Change

- `post500` is the default manual results window.
- Aggregate Results now use the selected Window setting.
- Indicator overlays continue to use the selected Window setting.
- Smoothing remains chart-only and does not change aggregate KPI values.

## Unsigned Installer

The Windows installer may be unsigned unless the release workflow proves signing secrets were available. Windows SmartScreen may warn that the app is from an unknown publisher. Install only after the checksum matches the published release checksums.

## Included

- local dashboard-managed manual Java model runs
- one-at-a-time sensitivity runs
- result, log, run-manifest, sensitivity-summary, and support-bundle storage under Electron user data
- offline launch and bundled dashboard runs without system Node.js, Maven, Java, Git, or terminal use
- local API bound only to `127.0.0.1` with an Electron-owned per-session write token

## Not Included

- Python calibration workflows
- full validation regeneration
- `private-datasets/`
- heavy sharded research sweeps
- WSL/Linux-only shell workflows
- AWS, Render, public API, or other cloud model execution

WSL2, Docker, EC2/Batch, or another remote Linux runner remain better fits for heavy research workflows, calibration, validation regeneration, and long experiment sweeps.
