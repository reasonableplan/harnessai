import { bootstrap, createLogger } from '@agent/core';
import { createAgentFactories } from './agent-factories.js';

const log = createLogger('Main');

async function main() {
  log.info('Starting agent orchestration system...');

  const context = await bootstrap({
    agents: createAgentFactories(),
  });

  log.info(
    { agentCount: context.agents.length, agents: context.agents.map((a) => a.id) },
    'System started successfully',
  );
}

main().catch((err) => {
  log.fatal({ err }, 'Fatal startup error');
  process.exit(1);
});
