import { runDashboardServerFromEnv } from './dashboardServer';

void runDashboardServerFromEnv().catch((error) => {
  console.error('[dashboard-api] failed to start:', error);
  process.exitCode = 1;
});
