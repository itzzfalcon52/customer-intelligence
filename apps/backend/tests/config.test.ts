import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readConfig } from '../src/config.js';
test('configuration errors never reflect database credentials', () => {
  const credential = 'private-password-do-not-log';
  assert.throws(
    () => readConfig({ DATABASE_URL: credential, BETTER_AUTH_SECRET: 'short' }),
    (error) =>
      error instanceof Error &&
      !error.message.includes(credential) &&
      error.message.includes('DATABASE_URL'),
  );
});
test('production requires an HTTPS browser origin', () => {
  assert.throws(
    () =>
      readConfig({
        DATABASE_URL: 'postgresql://localhost/test',
        BETTER_AUTH_SECRET: 'a'.repeat(64),
        APP_ORIGIN: 'http://example.com',
        NODE_ENV: 'production',
      }),
    /HTTPS/,
  );
});
