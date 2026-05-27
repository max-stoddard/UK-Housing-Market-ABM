#!/usr/bin/env node
/* global console */
// Author: Max Stoddard
import assert from 'node:assert/strict';
import { classifyCloudSmokePreflight } from './cloud-experiment-smoke.mjs';

function runtimeDeps({
  modelRunsEnabled = true,
  modelRunsDisabledReason = null,
  remoteExecution = {
    configured: true,
    available: true,
    runnerState: 'running',
    ssmPingStatus: 'Online',
    reason: null
  }
} = {}) {
  return {
    modelRunsEnabled,
    modelRunsDisabledReason,
    ...(remoteExecution ? { remoteExecution } : {})
  };
}

function assertFails(runtimeDepsPayload, options, pattern) {
  assert.throws(
    () => classifyCloudSmokePreflight(runtimeDepsPayload, options),
    pattern
  );
}

{
  const result = classifyCloudSmokePreflight(
    runtimeDeps({
      remoteExecution: {
        configured: true,
        available: false,
        runnerState: 'stopped',
        ssmPingStatus: 'unknown',
        reason: 'EC2 runner is stopped.'
      }
    }),
    { warnOnStoppedRunner: true }
  );

  assert.equal(result.action, 'warn_and_skip');
  assert.match(result.message, /runnerState=stopped/);
  assert.match(result.message, /EC2 runner is stopped/);
}

assertFails(
  runtimeDeps({
    remoteExecution: {
      configured: true,
      available: false,
      runnerState: 'stopped',
      ssmPingStatus: 'unknown',
      reason: 'EC2 runner is stopped.'
    }
  }),
  { warnOnStoppedRunner: false },
  /Cloud smoke requires the EC2 runner to be running and SSM Online/
);

assertFails(
  runtimeDeps({
    remoteExecution: {
      configured: true,
      available: false,
      runnerState: 'running',
      ssmPingStatus: 'Offline',
      reason: 'SSM runner status is Offline.'
    }
  }),
  { warnOnStoppedRunner: true },
  /ssmPingStatus=Offline/
);

assertFails(
  runtimeDeps({ remoteExecution: null }),
  { warnOnStoppedRunner: true },
  /remote execution is not configured/
);

assertFails(
  runtimeDeps({
    modelRunsEnabled: false,
    modelRunsDisabledReason: 'Model execution is disabled.',
    remoteExecution: {
      configured: true,
      available: false,
      runnerState: 'stopped',
      ssmPingStatus: 'unknown',
      reason: 'EC2 runner is stopped.'
    }
  }),
  { warnOnStoppedRunner: true },
  /Cloud smoke requires model runs enabled/
);

{
  const result = classifyCloudSmokePreflight(
    runtimeDeps({
      remoteExecution: {
        configured: true,
        available: true,
        runnerState: 'running',
        ssmPingStatus: 'Online',
        reason: null
      }
    }),
    { warnOnStoppedRunner: true }
  );

  assert.deepEqual(result, { action: 'proceed' });
}

console.log('Cloud experiment smoke preflight tests passed.');
