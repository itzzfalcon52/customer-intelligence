// Turns on Stripe/HubSpot connectors: writes a Fernet key (CI_CREDENTIALS_KEY) to apps/api/.env
// once. The key encrypts stored connector credentials; it is never printed. Losing or changing it
// makes saved connections unreadable, so an existing key is always kept.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { fileURLToPath } from 'node:url';
const envPath = fileURLToPath(new URL('../apps/api/.env', import.meta.url));
const contents = existsSync(envPath) ? readFileSync(envPath, 'utf8') : '';
if (/^CI_CREDENTIALS_KEY=\S+/m.test(contents)) {
  console.log(
    'Connectors are already set up (CI_CREDENTIALS_KEY exists in apps/api/.env).',
  );
  process.exit(0);
}
// Fernet keys are 32 random bytes in URL-safe base64 with padding.
const key = randomBytes(32).toString('base64url') + '=';
const line = `CI_CREDENTIALS_KEY=${key}`;
const next = /^#?\s*CI_CREDENTIALS_KEY=.*$/m.test(contents)
  ? contents.replace(/^#?\s*CI_CREDENTIALS_KEY=.*$/m, line)
  : `${contents}${contents && !contents.endsWith('\n') ? '\n' : ''}\n# Encrypts Stripe/HubSpot connector credentials. Keep it; changing it breaks saved connections.\n${line}\n`;
writeFileSync(envPath, next, { mode: 0o600 });
console.log(
  'Connectors are on: a new key was saved to apps/api/.env. Restart the API and the worker.',
);
