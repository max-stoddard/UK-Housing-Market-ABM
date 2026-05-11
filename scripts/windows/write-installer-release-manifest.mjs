#!/usr/bin/env node
// Author: Max Stoddard
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..', '..');
const dashboardRoot = path.join(repoRoot, 'dashboard');
const electronRoot = path.join(dashboardRoot, 'electron');
const defaultResourcesRoot = path.join(dashboardRoot, 'release', 'windows', 'resources');
const defaultInstallerRoot = path.join(dashboardRoot, 'release', 'windows', 'installer');
const appId = 'uk.housing.model.dashboard';
const productName = 'UK Housing Model';
const target = 'nsis';
const arch = 'x64';
const manifestFileName = 'release-manifest.json';
const checksumFileName = 'SHA256SUMS.txt';
const modelJarName = 'housing-model-1.0-SNAPSHOT-windows-release.jar';

function usage() {
  return `Usage: node scripts/windows/write-installer-release-manifest.mjs [options]

Options:
  --check              Validate existing installer release metadata without rewriting it.
  --resources-root     Release resources root. Defaults to dashboard/release/windows/resources.
  --installer-root     Installer output root. Defaults to dashboard/release/windows/installer.
  --help               Show this help.
`;
}

function parseArgs(argv) {
  const options = {
    check: false,
    resourcesRoot: defaultResourcesRoot,
    installerRoot: defaultInstallerRoot
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      console.log(usage());
      process.exit(0);
    }
    if (arg === '--check') {
      options.check = true;
      continue;
    }
    if (arg === '--resources-root') {
      const value = argv[i + 1];
      if (!value) {
        throw new Error('--resources-root requires a path.');
      }
      options.resourcesRoot = path.resolve(process.cwd(), value);
      i += 1;
      continue;
    }
    if (arg === '--installer-root') {
      const value = argv[i + 1];
      if (!value) {
        throw new Error('--installer-root requires a path.');
      }
      options.installerRoot = path.resolve(process.cwd(), value);
      i += 1;
      continue;
    }
    throw new Error(`Unknown option: ${arg}`);
  }

  return options;
}

function log(message) {
  console.log(`[installer-release] ${message}`);
}

function fail(message) {
  throw new Error(message);
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

function normalizeRel(filePath) {
  return filePath.split(path.sep).join('/');
}

function assertFile(filePath, label) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    fail(`Missing ${label}: ${filePath}`);
  }
}

function assertDirectory(dirPath, label) {
  if (!fs.existsSync(dirPath) || !fs.statSync(dirPath).isDirectory()) {
    fail(`Missing ${label}: ${dirPath}`);
  }
}

function sha256Buffer(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function sha256File(filePath) {
  return sha256Buffer(fs.readFileSync(filePath));
}

function listFiles(root) {
  const files = [];
  function walk(current) {
    const entries = fs.readdirSync(current, { withFileTypes: true })
      .sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const absolutePath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        walk(absolutePath);
      } else if (entry.isFile()) {
        files.push(absolutePath);
      } else if (!entry.isSymbolicLink()) {
        fail(`Unsupported package entry: ${absolutePath}`);
      }
    }
  }
  walk(root);
  return files;
}

function runCapture(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: 'utf-8',
    shell: process.platform === 'win32'
  });
  if (result.error) {
    fail(`${command} failed to start: ${result.error.message}`);
  }
  if (result.status !== 0) {
    fail(
      `${command} ${args.join(' ')} exited with status ${result.status ?? 'unknown'}.\n` +
        `STDOUT:\n${result.stdout ?? ''}\nSTDERR:\n${result.stderr ?? ''}`
    );
  }
  return `${result.stdout ?? ''}${result.stderr ?? ''}`.trim();
}

function installerFileName(appVersion) {
  return `UK-Housing-Model-${appVersion}-Setup.exe`;
}

function expectedInstallerPath(installerRoot, appVersion) {
  return path.join(installerRoot, installerFileName(appVersion));
}

function validateBuilderConfig() {
  const configPath = path.join(electronRoot, 'electron-builder.yml');
  assertFile(configPath, 'Electron Builder config');
  const config = fs.readFileSync(configPath, 'utf-8');
  const requiredSnippets = [
    `appId: ${appId}`,
    `productName: ${productName}`,
    'artifactName: UK-Housing-Model-${version}-Setup.${ext}',
    'asar: false',
    'publish: null',
    'app: ../release/windows/resources/app',
    'output: ../release/windows/installer',
    'main: electron/dist/electron/main.js',
    'from: ../release/windows/resources/java',
    'from: ../release/windows/resources/model',
    'from: ../release/windows/resources/release-data',
    'from: ../release/windows/resources/release-manifest.json',
    'target: nsis',
    'perMachine: false',
    'deleteAppDataOnUninstall: false'
  ];
  for (const snippet of requiredSnippets) {
    if (!config.includes(snippet)) {
      fail(`Electron Builder config is missing required setting: ${snippet}`);
    }
  }
  if (/nsis-web/i.test(config)) {
    fail('Electron Builder config must not use nsis-web for the offline v1 installer.');
  }
}

function releaseDataManifestFilePaths(releaseDataRoot) {
  const manifestPaths = new Set(['release-data-manifest.json', 'release-data.sha256']);
  return listFiles(releaseDataRoot)
    .map((filePath) => normalizeRel(path.relative(releaseDataRoot, filePath)))
    .filter((relativePath) => !manifestPaths.has(relativePath))
    .sort((left, right) => left.localeCompare(right));
}

function releaseDataAggregateSha256(releaseDataRoot) {
  const entries = releaseDataManifestFilePaths(releaseDataRoot).map((relativePath) => {
    const filePath = path.join(releaseDataRoot, relativePath);
    return `${sha256File(filePath)}  ${relativePath}`;
  });
  return sha256Buffer(Buffer.from(`${entries.join('\n')}\n`, 'utf-8'));
}

function readAndValidateResourceManifest(resourcesRoot) {
  const manifestPath = path.join(resourcesRoot, 'release-manifest.json');
  assertFile(manifestPath, 'Phase 10 release manifest');
  assertFile(path.join(resourcesRoot, 'model', modelJarName), 'staged model jar');
  assertDirectory(path.join(resourcesRoot, 'release-data'), 'staged release-data');
  const manifest = readJson(manifestPath);
  const modelPath = path.join(resourcesRoot, manifest.modelArtifact?.path ?? '');
  assertFile(modelPath, 'resource manifest model artifact');
  if (manifest.modelArtifact?.sha256 !== sha256File(modelPath)) {
    fail('Resource manifest model artifact hash does not match the staged model jar.');
  }
  const releaseDataRoot = path.join(resourcesRoot, manifest.releaseData?.path ?? '');
  assertDirectory(releaseDataRoot, 'resource manifest release-data root');
  const actualReleaseDataHash = releaseDataAggregateSha256(releaseDataRoot);
  if (manifest.releaseData?.sha256 !== actualReleaseDataHash) {
    fail('Resource manifest release-data hash does not match staged release-data.');
  }
  return {
    path: manifestPath,
    sha256: sha256File(manifestPath),
    manifest
  };
}

function validatePackagedResourceTree(packagedResourcesRoot, sourceResourceManifest) {
  assertDirectory(packagedResourcesRoot, 'packaged Electron resources');
  const packagedManifestPath = path.join(packagedResourcesRoot, 'release-manifest.json');
  assertFile(packagedManifestPath, 'packaged Phase 10 release manifest');
  if (sha256File(packagedManifestPath) !== sourceResourceManifest.sha256) {
    fail('Packaged release-manifest.json does not match the validated Phase 10 resource manifest.');
  }

  const packagedManifest = readJson(packagedManifestPath);
  const packagedModelPath = path.join(packagedResourcesRoot, packagedManifest.modelArtifact?.path ?? '');
  assertFile(packagedModelPath, 'packaged model jar');
  if (packagedManifest.modelArtifact?.sha256 !== sha256File(packagedModelPath)) {
    fail('Packaged model jar hash does not match the packaged release manifest.');
  }

  const packagedReleaseDataRoot = path.join(packagedResourcesRoot, packagedManifest.releaseData?.path ?? '');
  assertDirectory(packagedReleaseDataRoot, 'packaged release-data root');
  if (packagedManifest.releaseData?.sha256 !== releaseDataAggregateSha256(packagedReleaseDataRoot)) {
    fail('Packaged release-data hash does not match the packaged release manifest.');
  }

  const packagedJavaExe = path.join(packagedResourcesRoot, 'java', 'bin', 'java.exe');
  assertFile(packagedJavaExe, 'packaged Windows Java executable');

  assertNoDisallowedPackageEntries(packagedResourcesRoot);
}

function assertNoDisallowedPackageEntries(root) {
  const disallowedParts = new Set([
    'private-datasets',
    'Results',
    'tmp',
    'agents',
    '.github',
    '.aws',
    'docs/cloud'
  ]);
  const disallowedBasenames = [/^AGENTS?\.md$/i, /^AGENT.*\.md$/i, /^CLAUDE\.md$/i, /^PROMPT\.md$/i, /^\.env/i, /^render\.yaml$/i];

  function walk(current) {
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      const absolutePath = path.join(current, entry.name);
      const relativePath = normalizeRel(path.relative(root, absolutePath));
      const parts = relativePath.split('/');
      for (let i = 0; i < parts.length; i += 1) {
        const partial = parts.slice(i, i + 2).join('/');
        if (disallowedParts.has(parts[i]) || disallowedParts.has(partial)) {
          fail(`Disallowed release package path found: ${relativePath}`);
        }
      }
      const baseName = path.basename(relativePath);
      if (disallowedBasenames.some((pattern) => pattern.test(baseName))) {
        fail(`Disallowed release package file found: ${relativePath}`);
      }
      if (entry.isDirectory()) {
        walk(absolutePath);
      } else if (!entry.isFile() && !entry.isSymbolicLink()) {
        fail(`Unsupported release package entry found: ${relativePath}`);
      }
    }
  }

  walk(root);
}

function resolveReleaseCommit() {
  const configuredCommit = process.env.RELEASE_GIT_COMMIT?.trim();
  if (configuredCommit) {
    return configuredCommit;
  }
  return runCapture('git', ['rev-parse', 'HEAD'], repoRoot);
}

function buildInstallerManifest(options, appPackage, installerPath, resourceManifest) {
  const installerHash = sha256File(installerPath);
  const relativeInstallerPath = normalizeRel(path.relative(options.installerRoot, installerPath));
  return {
    manifestVersion: 1,
    generatedAt: new Date().toISOString(),
    distribution: {
      channel: 'windows-desktop',
      method: 'GitHub Releases',
      unsigned: true
    },
    app: {
      name: appPackage.name,
      version: appPackage.version,
      releaseVersion: `v${appPackage.version}`,
      productName,
      appId
    },
    git: {
      commit: resolveReleaseCommit()
    },
    installer: {
      path: relativeInstallerPath,
      fileName: path.basename(installerPath),
      target,
      arch,
      unsigned: true,
      sizeBytes: fs.statSync(installerPath).size,
      sha256: installerHash
    },
    packagedResources: {
      pathInInstaller: 'resources',
      phase10ManifestPath: 'resources/release-manifest.json',
      phase10ManifestSha256: resourceManifest.sha256,
      modelArtifact: resourceManifest.manifest.modelArtifact,
      javaRuntime: resourceManifest.manifest.javaRuntime,
      releaseData: resourceManifest.manifest.releaseData
    },
    checksums: {
      aggregatePath: checksumFileName,
      installerPath: `${path.basename(installerPath)}.sha256`
    }
  };
}

function checksumLine(filePath, relativePath) {
  return `${sha256File(filePath)}  ${relativePath}\n`;
}

function writeChecksums(installerRoot, installerPath, releaseManifestPath) {
  const installerName = path.basename(installerPath);
  const installerChecksumPath = path.join(installerRoot, `${installerName}.sha256`);
  fs.writeFileSync(installerChecksumPath, checksumLine(installerPath, installerName), 'utf-8');

  const entries = [
    checksumLine(installerPath, installerName),
    checksumLine(releaseManifestPath, path.basename(releaseManifestPath))
  ].sort((left, right) => left.localeCompare(right));
  fs.writeFileSync(path.join(installerRoot, checksumFileName), entries.join(''), 'utf-8');
}

function parseChecksumFile(filePath) {
  const entries = new Map();
  const lines = fs.readFileSync(filePath, 'utf-8').split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    const match = /^([a-f0-9]{64})  (.+)$/i.exec(line);
    if (!match) {
      fail(`Invalid checksum line in ${filePath}: ${line}`);
    }
    entries.set(match[2], match[1].toLowerCase());
  }
  return entries;
}

function validateChecksums(installerRoot, installerPath, releaseManifestPath) {
  const installerName = path.basename(installerPath);
  const installerChecksumPath = path.join(installerRoot, `${installerName}.sha256`);
  const aggregateChecksumPath = path.join(installerRoot, checksumFileName);
  assertFile(installerChecksumPath, 'installer SHA256 checksum file');
  assertFile(aggregateChecksumPath, 'aggregate SHA256 checksum file');

  const installerChecksum = fs.readFileSync(installerChecksumPath, 'utf-8');
  const expectedInstallerChecksum = checksumLine(installerPath, installerName);
  if (installerChecksum !== expectedInstallerChecksum) {
    fail(`${installerChecksumPath} does not match the installer artifact.`);
  }

  const aggregate = parseChecksumFile(aggregateChecksumPath);
  const expected = new Map([
    [installerName, sha256File(installerPath)],
    [path.basename(releaseManifestPath), sha256File(releaseManifestPath)]
  ]);
  for (const [relativePath, hash] of expected) {
    if (aggregate.get(relativePath) !== hash) {
      fail(`${aggregateChecksumPath} is missing or has a stale hash for ${relativePath}.`);
    }
  }
}

function validateReleaseManifest(installerRoot, installerPath, releaseManifestPath, resourceManifest) {
  assertFile(releaseManifestPath, 'installer release manifest');
  const manifest = readJson(releaseManifestPath);
  if (manifest.app?.appId !== appId || manifest.app?.productName !== productName) {
    fail('Installer release manifest has unexpected app identity.');
  }
  if (manifest.installer?.target !== target || manifest.installer?.arch !== arch) {
    fail('Installer release manifest has unexpected target or architecture.');
  }
  if (manifest.installer?.unsigned !== true || manifest.distribution?.unsigned !== true) {
    fail('Installer release manifest must record the v1 package as unsigned.');
  }
  if (manifest.installer?.sha256 !== sha256File(installerPath)) {
    fail('Installer release manifest installer hash is stale.');
  }
  if (manifest.packagedResources?.phase10ManifestSha256 !== resourceManifest.sha256) {
    fail('Installer release manifest Phase 10 resource manifest hash is stale.');
  }
  validateChecksums(installerRoot, installerPath, releaseManifestPath);
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  options.resourcesRoot = path.resolve(options.resourcesRoot);
  options.installerRoot = path.resolve(options.installerRoot);

  validateBuilderConfig();
  const dashboardPackage = readJson(path.join(dashboardRoot, 'package.json'));
  const resourceManifest = readAndValidateResourceManifest(options.resourcesRoot);
  const installerPath = expectedInstallerPath(options.installerRoot, dashboardPackage.version);
  const releaseManifestPath = path.join(options.installerRoot, manifestFileName);

  if (!fs.existsSync(installerPath)) {
    if (options.check && process.platform !== 'win32') {
      log(
        `validated installer config and resources; Windows installer artifact is not required on ${os.platform()} checks.`
      );
      return;
    }
    fail(`Missing Windows installer artifact: ${installerPath}`);
  }

  const winUnpackedResources = path.join(options.installerRoot, 'win-unpacked', 'resources');
  validatePackagedResourceTree(winUnpackedResources, resourceManifest);

  if (!options.check) {
    fs.mkdirSync(options.installerRoot, { recursive: true });
    const manifest = buildInstallerManifest(options, dashboardPackage, installerPath, resourceManifest);
    writeJson(releaseManifestPath, manifest);
    writeChecksums(options.installerRoot, installerPath, releaseManifestPath);
    log(`wrote installer release manifest and checksums under ${options.installerRoot}`);
  }

  validateReleaseManifest(options.installerRoot, installerPath, releaseManifestPath, resourceManifest);
  log(`validated installer release artifacts under ${options.installerRoot}`);
}

try {
  main();
} catch (error) {
  console.error(`[installer-release] ${(error instanceof Error ? error.message : String(error))}`);
  process.exitCode = 1;
}
