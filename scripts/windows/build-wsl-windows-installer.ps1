# Author: Max Stoddard
[CmdletBinding()]
param(
  [Parameter()]
  [ValidateNotNullOrEmpty()]
  [string]$WslRepoPath = '/home/max/dev/uni/project/models/uk-housing-model-individual-project',

  [Parameter()]
  [string]$WslDistro = '',

  [Parameter()]
  [string]$BuildRoot = '',

  [Parameter()]
  [string]$JavaHome = '',

  [Parameter()]
  [switch]$RunInstalledSmoke
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step {
  param([Parameter(Mandatory = $true)][string]$Message)
  Write-Host ''
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Format-CommandLine {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter()][string[]]$ArgumentList = @()
  )

  $parts = @($FilePath) + $ArgumentList
  return ($parts | ForEach-Object {
    if ($_ -match '[\s"]') {
      '"' + ($_ -replace '"', '\"') + '"'
    } else {
      $_
    }
  }) -join ' '
}

function Invoke-ProcessChecked {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter()][string[]]$ArgumentList = @(),
    [Parameter()][string]$WorkingDirectory = (Get-Location).Path
  )

  Write-Host (Format-CommandLine -FilePath $FilePath -ArgumentList $ArgumentList)
  Push-Location -LiteralPath $WorkingDirectory
  try {
    $global:LASTEXITCODE = 0
    & $FilePath @ArgumentList
    $exitCode = $global:LASTEXITCODE
  } finally {
    Pop-Location
  }

  if ($exitCode -ne 0) {
    throw "Command failed with exit code ${exitCode}: $(Format-CommandLine -FilePath $FilePath -ArgumentList $ArgumentList)"
  }
}

function Invoke-ProcessCapture {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter()][string[]]$ArgumentList = @(),
    [Parameter()][string]$WorkingDirectory = (Get-Location).Path
  )

  Push-Location -LiteralPath $WorkingDirectory
  try {
    $global:LASTEXITCODE = 0
    $output = & $FilePath @ArgumentList 2>&1
    $exitCode = $global:LASTEXITCODE
  } finally {
    Pop-Location
  }

  $text = ($output | ForEach-Object { $_.ToString() }) -join "`n"
  if ($exitCode -ne 0) {
    throw "Command failed with exit code ${exitCode}: $(Format-CommandLine -FilePath $FilePath -ArgumentList $ArgumentList)`n${text}"
  }
  return $text.Trim()
}

function Resolve-RequiredCommand {
  param([Parameter(Mandatory = $true)][string]$Name)

  $command = Get-Command -Name $Name -ErrorAction SilentlyContinue
  if ($null -eq $command) {
    throw "Required command was not found on Windows PATH: ${Name}"
  }
  return $command.Source
}

function Resolve-PreferredNpmCommand {
  $npmCmd = Get-Command -Name 'npm.cmd' -ErrorAction SilentlyContinue
  if ($null -ne $npmCmd) {
    return $npmCmd.Source
  }
  return Resolve-RequiredCommand 'npm'
}

function Assert-WindowsHost {
  $isWindowsVariable = Get-Variable -Name IsWindows -ErrorAction SilentlyContinue
  $isWindows = ($null -ne $isWindowsVariable -and [bool]$isWindowsVariable.Value) -or
    ($PSVersionTable.PSEdition -eq 'Desktop')

  if (-not $isWindows) {
    throw 'This script must run from Windows PowerShell or PowerShell on the Windows host, not inside WSL.'
  }
}

function Get-DefaultBuildRoot {
  $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
  if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = $env:LOCALAPPDATA
  }
  if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = Join-Path -Path ([IO.Path]::GetTempPath()) -ChildPath 'LocalAppData'
  }
  return Join-Path -Path $localAppData -ChildPath 'UKHousingModel\wsl-windows-build'
}

function Resolve-FullPath {
  param([Parameter(Mandatory = $true)][string]$PathValue)

  $expanded = [Environment]::ExpandEnvironmentVariables($PathValue)
  if (-not [IO.Path]::IsPathRooted($expanded)) {
    $expanded = Join-Path -Path (Get-Location).Path -ChildPath $expanded
  }
  return [IO.Path]::GetFullPath($expanded)
}

function Trim-TrailingSeparators {
  param([Parameter(Mandatory = $true)][string]$PathValue)
  return $PathValue.TrimEnd([char[]]@('\', '/'))
}

function Assert-SafeBuildRoot {
  param([Parameter(Mandatory = $true)][string]$ResolvedBuildRoot)

  $pathRoot = [IO.Path]::GetPathRoot($ResolvedBuildRoot)
  if ([string]::IsNullOrWhiteSpace($pathRoot)) {
    throw "BuildRoot must be an absolute Windows path: ${ResolvedBuildRoot}"
  }

  if ((Trim-TrailingSeparators $ResolvedBuildRoot) -eq (Trim-TrailingSeparators $pathRoot)) {
    throw "BuildRoot must not be a filesystem root: ${ResolvedBuildRoot}"
  }
}

function Assert-StageOutsideSource {
  param(
    [Parameter(Mandatory = $true)][string]$SourceWindowsPath,
    [Parameter(Mandatory = $true)][string]$StageRoot
  )

  $normalizedSource = Trim-TrailingSeparators ([IO.Path]::GetFullPath($SourceWindowsPath))
  $normalizedStage = Trim-TrailingSeparators ([IO.Path]::GetFullPath($StageRoot))
  $sourcePrefix = $normalizedSource + [IO.Path]::DirectorySeparatorChar

  if (
    $normalizedStage.Equals($normalizedSource, [StringComparison]::OrdinalIgnoreCase) -or
    $normalizedStage.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)
  ) {
    throw "Build staging directory must be outside the WSL source checkout. Source=${normalizedSource}; Stage=${normalizedStage}"
  }
}

function Invoke-WslCapture {
  param([Parameter(Mandatory = $true)][string[]]$ArgumentList)

  $wslArgs = @()
  if (-not [string]::IsNullOrWhiteSpace($WslDistro)) {
    $wslArgs += @('-d', $WslDistro)
  }
  $wslArgs += '--'
  $wslArgs += $ArgumentList
  return Invoke-ProcessCapture -FilePath 'wsl.exe' -ArgumentList $wslArgs
}

function Convert-WslPathToWindowsPath {
  param([Parameter(Mandatory = $true)][string]$LinuxPath)
  return Invoke-WslCapture -ArgumentList @('wslpath', '-w', $LinuxPath)
}

function Get-WslGitText {
  param([Parameter(Mandatory = $true)][string[]]$GitArgs)
  return Invoke-WslCapture -ArgumentList (@('git', '-C', $WslRepoPath) + $GitArgs)
}

function Get-JavaMajorVersion {
  param([Parameter(Mandatory = $true)][string]$VersionOutput)

  $match = [regex]::Match($VersionOutput, '(?im)^(?:openjdk|java)\s+(?:version\s+)?["'']?([0-9]+)(?:[.\s"'']|$)')
  if (-not $match.Success) {
    throw "Could not parse Java major version from:`n${VersionOutput}"
  }
  return [int]$match.Groups[1].Value
}

function Resolve-JavaHome {
  param([Parameter()][string]$ConfiguredJavaHome)

  if (-not [string]::IsNullOrWhiteSpace($ConfiguredJavaHome)) {
    $resolved = Resolve-FullPath $ConfiguredJavaHome
    if (-not (Test-Path -LiteralPath $resolved -PathType Container)) {
      throw "JavaHome does not exist or is not a directory: ${resolved}"
    }
    return $resolved
  }

  $javaCommand = Resolve-RequiredCommand 'java'
  $settings = Invoke-ProcessCapture -FilePath $javaCommand -ArgumentList @('-XshowSettings:properties', '-version')
  $match = [regex]::Match($settings, '(?m)^\s*java\.home\s*=\s*(.+?)\s*$')
  if (-not $match.Success) {
    throw "Could not determine java.home from Windows java command. Pass -JavaHome explicitly.`n${settings}"
  }
  return Resolve-FullPath $match.Groups[1].Value.Trim()
}

function Assert-Java25Runtime {
  param([Parameter(Mandatory = $true)][string]$ResolvedJavaHome)

  $javaExe = Join-Path -Path $ResolvedJavaHome -ChildPath 'bin\java.exe'
  $jlinkExe = Join-Path -Path $ResolvedJavaHome -ChildPath 'bin\jlink.exe'
  if (-not (Test-Path -LiteralPath $javaExe -PathType Leaf)) {
    throw "Java executable was not found: ${javaExe}"
  }
  if (-not (Test-Path -LiteralPath $jlinkExe -PathType Leaf)) {
    throw "jlink executable was not found. Use a Java 25 JDK, not a JRE: ${jlinkExe}"
  }

  $javaVersion = Invoke-ProcessCapture -FilePath $javaExe -ArgumentList @('--version')
  $major = Get-JavaMajorVersion $javaVersion
  if ($major -ne 25) {
    throw "Windows release packaging requires Java 25; found major version ${major}.`n${javaVersion}"
  }

  $jlinkVersion = Invoke-ProcessCapture -FilePath $jlinkExe -ArgumentList @('--version')
  return [ordered]@{
    Home = $ResolvedJavaHome
    JavaExe = $javaExe
    JlinkExe = $jlinkExe
    VersionOutput = $javaVersion
    JlinkVersionOutput = $jlinkVersion
  }
}

function Assert-Node22 {
  param([Parameter(Mandatory = $true)][string]$NodeCommand)

  $nodeVersion = Invoke-ProcessCapture -FilePath $NodeCommand -ArgumentList @('--version')
  if ($nodeVersion -notmatch '^v22\.') {
    throw "Windows release packaging requires Node 22; found ${nodeVersion}."
  }
  return $nodeVersion
}

function Invoke-RobocopyChecked {
  param([Parameter(Mandatory = $true)][string[]]$ArgumentList)

  Write-Host (Format-CommandLine -FilePath 'robocopy.exe' -ArgumentList $ArgumentList)
  $global:LASTEXITCODE = 0
  & robocopy.exe @ArgumentList
  $exitCode = $global:LASTEXITCODE
  if ($exitCode -ge 8) {
    throw "robocopy failed with exit code ${exitCode}."
  }
  Write-Host "robocopy completed with exit code ${exitCode}."
}

function Copy-WslWorkingTreeToStage {
  param(
    [Parameter(Mandatory = $true)][string]$SourceWindowsPath,
    [Parameter(Mandatory = $true)][string]$StageRoot
  )

  if (Test-Path -LiteralPath $StageRoot) {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
  }
  New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null

  $excludeDirs = @(
    (Join-Path $SourceWindowsPath '.agents'),
    (Join-Path $SourceWindowsPath '.claude'),
    (Join-Path $SourceWindowsPath '.idea'),
    (Join-Path $SourceWindowsPath '.vscode'),
    (Join-Path $SourceWindowsPath '.worktrees'),
    (Join-Path $SourceWindowsPath 'agents'),
    (Join-Path $SourceWindowsPath 'bin'),
    (Join-Path $SourceWindowsPath 'dashboard\.smoke-dist'),
    (Join-Path $SourceWindowsPath 'dashboard\dist'),
    (Join-Path $SourceWindowsPath 'dashboard\dist-server'),
    (Join-Path $SourceWindowsPath 'dashboard\electron\dist'),
    (Join-Path $SourceWindowsPath 'dashboard\electron\node_modules'),
    (Join-Path $SourceWindowsPath 'dashboard\node_modules'),
    (Join-Path $SourceWindowsPath 'dashboard\release'),
    (Join-Path $SourceWindowsPath 'experiments'),
    (Join-Path $SourceWindowsPath 'private-datasets'),
    (Join-Path $SourceWindowsPath 'Results'),
    (Join-Path $SourceWindowsPath 'target'),
    (Join-Path $SourceWindowsPath 'tmp')
  )

  $excludeFiles = @(
    '.codex',
    '.env',
    '.env.*',
    '*.dta',
    '*.privdata',
    'AGENTS.md',
    'AGENT*.md',
    'CLAUDE.md',
    'PROMPT.md',
    'TODO.md'
  )

  $robocopyArgs = @(
    $SourceWindowsPath,
    $StageRoot,
    '/E',
    '/COPY:DAT',
    '/DCOPY:DAT',
    '/R:2',
    '/W:2',
    '/XJ',
    '/NP'
  )
  $robocopyArgs += '/XD'
  $robocopyArgs += $excludeDirs
  $robocopyArgs += '/XF'
  $robocopyArgs += $excludeFiles

  Invoke-RobocopyChecked -ArgumentList $robocopyArgs
}

function Assert-StagedRepoShape {
  param([Parameter(Mandatory = $true)][string]$StageRoot)

  $requiredPaths = @(
    '.git',
    '.mvn',
    'dashboard\package.json',
    'dashboard\electron\package.json',
    'input-data-versions',
    'mvnw.cmd',
    'pom.xml',
    'scripts\windows\assemble-release-resources.mjs',
    'src\main\java'
  )

  foreach ($relativePath in $requiredPaths) {
    $absolutePath = Join-Path -Path $StageRoot -ChildPath $relativePath
    if (-not (Test-Path -LiteralPath $absolutePath)) {
      throw "Staged repository is missing required path: ${relativePath}"
    }
  }
}

function Invoke-ReleaseBuild {
  param(
    [Parameter(Mandatory = $true)][string]$StageRoot,
    [Parameter(Mandatory = $true)][string]$NpmCommand
  )

  $dashboardRoot = Join-Path -Path $StageRoot -ChildPath 'dashboard'

  Write-Step 'Installing dashboard dependencies'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('ci', '--include=dev') -WorkingDirectory $dashboardRoot

  Write-Step 'Installing Electron dependencies'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('--prefix', 'electron', 'ci') -WorkingDirectory $dashboardRoot

  Write-Step 'Running dashboard lint'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('run', 'lint') -WorkingDirectory $dashboardRoot

  Write-Step 'Building dashboard'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('run', 'build') -WorkingDirectory $dashboardRoot

  Write-Step 'Running dashboard smoke tests'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('run', 'test:smoke') -WorkingDirectory $dashboardRoot

  Write-Step 'Running Maven tests'
  Invoke-ProcessChecked -FilePath (Join-Path $StageRoot 'mvnw.cmd') -ArgumentList @('test') -WorkingDirectory $StageRoot

  Write-Step 'Building Windows release fat jar'
  Invoke-ProcessChecked -FilePath (Join-Path $StageRoot 'mvnw.cmd') -ArgumentList @('-q', '-DskipTests', '-Pwindows-release-fat-jar', 'package') -WorkingDirectory $StageRoot

  Write-Step 'Running Maven-vs-packaged launcher regression'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('run', 'test:release-launch') -WorkingDirectory $dashboardRoot

  Write-Step 'Building unsigned Windows installer'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('run', 'release:installer:unsigned') -WorkingDirectory $dashboardRoot

  Write-Step 'Validating installer release metadata'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('run', 'release:installer:check:unsigned') -WorkingDirectory $dashboardRoot

  Write-Step 'Running desktop release-resource smoke test'
  Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('run', 'test:desktop-release-resources') -WorkingDirectory $dashboardRoot

  if ($RunInstalledSmoke) {
    Write-Step 'Running installed app smoke test'
    Invoke-ProcessChecked -FilePath $NpmCommand -ArgumentList @('run', 'test:windows-installed-installer') -WorkingDirectory $dashboardRoot
  }
}

function Copy-InstallerArtifactsBack {
  param(
    [Parameter(Mandatory = $true)][string]$StageRoot,
    [Parameter(Mandatory = $true)][string]$DestinationWindowsRoot,
    [Parameter(Mandatory = $true)][hashtable]$WrapperMetadata
  )

  $dashboardPackagePath = Join-Path -Path $StageRoot -ChildPath 'dashboard\package.json'
  $dashboardPackage = Get-Content -Raw -LiteralPath $dashboardPackagePath | ConvertFrom-Json
  $version = [string]$dashboardPackage.version
  if ([string]::IsNullOrWhiteSpace($version)) {
    throw "Could not read dashboard package version from ${dashboardPackagePath}"
  }

  $installerName = "UK-Housing-Model-${version}-Setup.exe"
  $installerRoot = Join-Path -Path $StageRoot -ChildPath 'dashboard\release\windows\installer'
  $artifactNames = @(
    $installerName,
    'release-manifest.json',
    'SHA256SUMS.txt',
    "${installerName}.sha256"
  )

  foreach ($artifactName in $artifactNames) {
    $artifactPath = Join-Path -Path $installerRoot -ChildPath $artifactName
    if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
      throw "Missing expected installer artifact: ${artifactPath}"
    }
  }

  if (-not (Test-Path -LiteralPath $DestinationWindowsRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $DestinationWindowsRoot -Force | Out-Null
  }

  foreach ($artifactName in $artifactNames) {
    Copy-Item `
      -LiteralPath (Join-Path -Path $installerRoot -ChildPath $artifactName) `
      -Destination (Join-Path -Path $DestinationWindowsRoot -ChildPath $artifactName) `
      -Force
  }

  $manifest = [ordered]@{
    manifestVersion = 1
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    source = $WrapperMetadata.Source
    build = $WrapperMetadata.Build
    installer = [ordered]@{
      fileName = $installerName
      copiedTo = (Join-Path -Path $DestinationWindowsRoot -ChildPath $installerName)
      releaseManifest = (Join-Path -Path $DestinationWindowsRoot -ChildPath 'release-manifest.json')
      checksumFile = (Join-Path -Path $DestinationWindowsRoot -ChildPath "${installerName}.sha256")
      aggregateChecksumFile = (Join-Path -Path $DestinationWindowsRoot -ChildPath 'SHA256SUMS.txt')
    }
  }

  $wrapperManifestPath = Join-Path -Path $DestinationWindowsRoot -ChildPath 'wsl-windows-installer-manifest.json'
  $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $wrapperManifestPath -Encoding UTF8

  return [ordered]@{
    InstallerName = $installerName
    InstallerPath = (Join-Path -Path $DestinationWindowsRoot -ChildPath $installerName)
    ManifestPath = $wrapperManifestPath
  }
}

Assert-WindowsHost

if ([string]::IsNullOrWhiteSpace($BuildRoot)) {
  $BuildRoot = Get-DefaultBuildRoot
}
$resolvedBuildRoot = Resolve-FullPath $BuildRoot
Assert-SafeBuildRoot $resolvedBuildRoot

Write-Step 'Checking Windows host prerequisites'
Resolve-RequiredCommand 'wsl.exe' | Out-Null
Resolve-RequiredCommand 'git' | Out-Null
$nodeCommand = Resolve-RequiredCommand 'node'
$npmCommand = Resolve-PreferredNpmCommand
Resolve-RequiredCommand 'robocopy.exe' | Out-Null

$nodeVersion = Assert-Node22 $nodeCommand
$npmVersion = Invoke-ProcessCapture -FilePath $npmCommand -ArgumentList @('--version')
$resolvedJavaHome = Resolve-JavaHome -ConfiguredJavaHome $JavaHome
$javaMetadata = Assert-Java25Runtime -ResolvedJavaHome $resolvedJavaHome

Write-Step 'Resolving WSL source repository'
$sourceWindowsPath = Convert-WslPathToWindowsPath $WslRepoPath
if (-not (Test-Path -LiteralPath $sourceWindowsPath -PathType Container)) {
  throw "WSL repository path does not resolve to a Windows-readable directory: ${WslRepoPath} -> ${sourceWindowsPath}"
}

$sourceCommit = Get-WslGitText -GitArgs @('rev-parse', 'HEAD')
$sourceBranch = Get-WslGitText -GitArgs @('branch', '--show-current')
$sourceStatusText = Get-WslGitText -GitArgs @('status', '--short', '--untracked-files=all')
$sourceStatusLines = @()
if (-not [string]::IsNullOrWhiteSpace($sourceStatusText)) {
  $sourceStatusLines = $sourceStatusText -split '\r?\n'
}

$stageRoot = Join-Path -Path $resolvedBuildRoot -ChildPath 'source'
$destinationRootLinux = "${WslRepoPath}/dashboard/release/windows/installer"
Invoke-WslCapture -ArgumentList @('mkdir', '-p', $destinationRootLinux) | Out-Null
$destinationWindowsRoot = Convert-WslPathToWindowsPath $destinationRootLinux

Write-Step 'Copying WSL working tree to native Windows staging directory'
Assert-StageOutsideSource -SourceWindowsPath $sourceWindowsPath -StageRoot $stageRoot
Copy-WslWorkingTreeToStage -SourceWindowsPath $sourceWindowsPath -StageRoot $stageRoot
Assert-StagedRepoShape $stageRoot

$originalJavaHome = $env:JAVA_HOME
$originalPath = $env:Path
try {
  $env:JAVA_HOME = $javaMetadata.Home
  $env:Path = (Join-Path $javaMetadata.Home 'bin') + [IO.Path]::PathSeparator + $env:Path

  Write-Step 'Building Windows installer from staged source'
  Invoke-ReleaseBuild -StageRoot $stageRoot -NpmCommand $npmCommand
} finally {
  $env:JAVA_HOME = $originalJavaHome
  $env:Path = $originalPath
}

Write-Step 'Copying installer artifacts back to WSL repository'
$wrapperMetadata = @{
  Source = [ordered]@{
    wslRepoPath = $WslRepoPath
    wslDistro = $WslDistro
    windowsPath = $sourceWindowsPath
    gitCommit = $sourceCommit
    gitBranch = $sourceBranch
    dirty = ($sourceStatusLines.Count -gt 0)
    statusShort = $sourceStatusLines
  }
  Build = [ordered]@{
    buildRoot = $resolvedBuildRoot
    stagedRepoPath = $stageRoot
    windowsHost = $env:COMPUTERNAME
    windowsUser = $env:USERNAME
    nodeVersion = $nodeVersion
    npmVersion = $npmVersion
    javaHome = $javaMetadata.Home
    javaVersionOutput = $javaMetadata.VersionOutput
    jlinkVersionOutput = $javaMetadata.JlinkVersionOutput
    runInstalledSmoke = [bool]$RunInstalledSmoke
  }
}
$copied = Copy-InstallerArtifactsBack `
  -StageRoot $stageRoot `
  -DestinationWindowsRoot $destinationWindowsRoot `
  -WrapperMetadata $wrapperMetadata

Write-Step 'Done'
Write-Host "Installer: $($copied.InstallerPath)"
Write-Host "Wrapper manifest: $($copied.ManifestPath)"
if ($RunInstalledSmoke) {
  Write-Host 'The installed-app smoke test was run because -RunInstalledSmoke was set.'
} else {
  Write-Host 'The installed-app smoke test was not run. Pass -RunInstalledSmoke to opt into silent install validation.' -ForegroundColor Yellow
}
