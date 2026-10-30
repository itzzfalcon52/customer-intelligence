import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const envPath = fileURLToPath(new URL('../apps/backend/.env', import.meta.url));
const require = createRequire(
  new URL('../apps/backend/package.json', import.meta.url),
);
const { parse } = require('dotenv');
if (!existsSync(envPath)) {
  const template = readFileSync(
    new URL('../apps/backend/.env.example', import.meta.url),
    'utf8',
  );
  writeFileSync(
    envPath,
    template.replace(
      'BETTER_AUTH_SECRET=\n',
      `BETTER_AUTH_SECRET=${randomBytes(32).toString('hex')}\n`,
    ),
    { flag: 'wx', mode: 0o600 },
  );
}
const saved = parse(readFileSync(envPath));
if (!saved.INTERNAL_API_SECRET) {
  const secret = randomBytes(32).toString('hex');
  let contents = readFileSync(envPath, 'utf8');
  contents = /^INTERNAL_API_SECRET=/m.test(contents)
    ? contents.replace(
        /^INTERNAL_API_SECRET=.*$/m,
        'INTERNAL_API_SECRET=' + secret,
      )
    : contents + '\nINTERNAL_API_SECRET=' + secret + '\n';
  writeFileSync(envPath, contents, { mode: 0o600 });
  saved.INTERNAL_API_SECRET = secret;
}
const values = { ...saved, ...process.env };
if (!values.DATABASE_URL) {
  console.error(
    'Add your Neon DATABASE_URL to apps/backend/.env, then run pnpm setup:backend again.',
  );
  process.exit(1);
}
for (const task of ['db:generate', 'db:migrate']) {
  const result = spawnSync('pnpm', ['--filter', '@ci/backend', task], {
    cwd: root,
    stdio: 'inherit',
    env: values,
  });
  if (result.status !== 0) process.exit(result.status || 1);
}
console.log('Account database is ready. Start all services with pnpm dev.');
