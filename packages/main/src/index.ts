import { existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { bootstrap, loadConfig, createLogger } from '@agent/core';
import { createDashboardServer } from '@agent/dashboard-server';
import { createAgentFactories } from './agent-factories.js';
import { createDashboardDeps } from './dashboard-adapter.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

const log = createLogger('Main');

async function main() {
  log.info('Starting agent orchestration system...');

  // 설정을 한번만 로드하고 모든 하위 모듈에 DI로 전달
  const appConfig = loadConfig();

  const context = await bootstrap({
    agents: createAgentFactories(appConfig),
    appConfig,
  });

  log.info(
    { agentCount: context.agents.length, agents: context.agents.map((a) => a.id) },
    'System started successfully',
  );

  // Dashboard server 시작
  const dashboardDeps = createDashboardDeps(
    context.stateStore,
    context.messageBus,
    context.agents,
  );
  // Auto-detect built dashboard-client for single-port static serving
  const clientDistPath = resolve(__dirname, '../../dashboard-client/dist');
  const staticDir = existsSync(clientDistPath) ? clientDistPath : undefined;

  const dashboard = createDashboardServer(dashboardDeps, {
    corsOrigins: appConfig.dashboard.corsOrigins,
    staticDir,
    authToken: appConfig.dashboard.authToken,
  });
  await dashboard.listen(appConfig.dashboard.port);

  log.info({ port: appConfig.dashboard.port }, 'Dashboard server started');
  log.info(`  REST API:   http://localhost:${appConfig.dashboard.port}/api`);
  log.info(`  WebSocket:  ws://localhost:${appConfig.dashboard.port}`);
  log.info(`  Health:     http://localhost:${appConfig.dashboard.port}/health`);

  // SIGINT/SIGTERM 핸들러는 bootstrap() 내부에서 등록됨 (process.on('SIGINT'/'SIGTERM', signalHandler))
  // context.shutdown을 호출하면 해당 핸들러가 자동으로 제거됨
  // Graceful shutdown에 dashboard 포함
  const originalShutdown = context.shutdown;
  let shuttingDown = false;
  context.shutdown = async () => {
    if (shuttingDown) return;
    shuttingDown = true;
    try {
      await dashboard.close();
    } finally {
      await originalShutdown();
    }
  };
}

main().catch((err) => {
  log.fatal({ err }, 'Fatal startup error');
  process.exit(1);
});
