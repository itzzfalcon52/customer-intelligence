import { readConfig } from './config.js';
import { createPrisma } from './lib/prisma.js';
import { createAuth } from './lib/auth.js';
import { createApp } from './app.js';

async function start() {
  const config = readConfig();
  const database = createPrisma(config.DATABASE_URL);
  try {
    await database.$connect();
    await database.user.count();
  } catch {
    await database.$disconnect();
    throw new Error(
      'Cannot connect to the account database. Check DATABASE_URL in apps/backend/.env and run pnpm setup:backend.',
    );
  }
  const app = createApp(createAuth(database, config), database, config);
  const server = app.listen(config.PORT, config.HOST, () =>
    console.log(
      `Account backend ready at http://${config.HOST}:${config.PORT}`,
    ),
  );
  server.on('error', () => {
    console.error(
      'Backend could not start. Check whether its port is already in use.',
    );
    void database.$disconnect().finally(() => process.exit(1));
  });
  for (const signal of ['SIGINT', 'SIGTERM'] as const)
    process.once(signal, () => {
      server.close(() => {
        void database.$disconnect().finally(() => process.exit(0));
      });
    });
}
start().catch((error) => {
  console.error(
    error instanceof Error ? error.message : 'Backend startup failed.',
  );
  process.exit(1);
});
