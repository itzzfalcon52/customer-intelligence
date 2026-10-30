import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { test } from 'node:test';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { createPrisma } from '../src/lib/prisma.js';
import { createAuth } from '../src/lib/auth.js';
import { createApp } from '../src/app.js';
import { readConfig } from '../src/config.js';

const testUrl = process.env.AUTH_TEST_DATABASE_URL;
test(
  'real PostgreSQL email/password, session and organization isolation',
  { skip: !testUrl },
  async (t) => {
    const url = new URL(testUrl!);
    // Never run fixture cleanup against Neon or the real application database.
    assert.ok(
      ['127.0.0.1', 'localhost'].includes(url.hostname) &&
        url.pathname.endsWith('_test'),
      'Use a dedicated local database ending in _test.',
    );
    const config = readConfig({
      DATABASE_URL: testUrl,
      BETTER_AUTH_SECRET: randomBytes(32).toString('hex'),
      APP_ORIGIN: 'http://127.0.0.1:5173',
      NODE_ENV: 'test',
      INTERNAL_API_SECRET: randomBytes(32).toString('hex'),
    });
    const database = createPrisma(testUrl!);
    const app = createApp(createAuth(database, config), database, config);
    const server = app.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const prefix = randomBytes(8).toString('hex');
    const password = randomBytes(18).toString('hex');
    const emails = [`${prefix}-one@example.com`, `${prefix}-two@example.com`];
    const call = (
      path: string,
      body?: unknown,
      cookie?: string,
      origin = config.APP_ORIGIN,
    ) =>
      fetch(base + path, {
        method: body ? 'POST' : 'GET',
        headers: {
          ...(body
            ? { 'Content-Type': 'application/json', Origin: origin }
            : {}),
          ...(cookie ? { Cookie: cookie } : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
    let cookie = '';
    let otherCookie = '';
    let userId = '';
    let organizationId = '';
    try {
      await t.test(
        'signup signs in immediately without verification or plaintext password storage',
        async () => {
          const response = await call('/api/auth/sign-up/email', {
            name: 'Test Member',
            email: emails[0],
            password,
          });
          assert.equal(response.status, 200);
          const cookies = response.headers.getSetCookie();
          cookie = cookies.map((value) => value.split(';')[0]).join('; ');
          assert.ok(
            cookies.some(
              (value) => /HttpOnly/i.test(value) && /SameSite=Lax/i.test(value),
            ),
            'Session cookie must be HttpOnly and SameSite=Lax.',
          );
          const result = await response.json();
          userId = result.user.id;
          assert.equal(result.user.emailVerified, false);
          const saved = await database.account.findFirst({ where: { userId } });
          assert.ok(
            saved?.password && saved.password !== password,
            'Only a password hash may be stored.',
          );
          assert.equal(await database.verification.count(), 0);
          assert.equal(
            (await call('/api/backend/me', undefined, cookie)).status,
            200,
          );
        },
      );
      await t.test(
        'private identity bridge requires both service secret and live session',
        async () => {
          const path = base + '/internal/identity';
          assert.equal((await fetch(path)).status, 401);
          const headers = {
            Authorization: 'Bearer ' + config.INTERNAL_API_SECRET,
            Cookie: cookie,
          };
          const valid = await fetch(path, { headers });
          assert.equal(valid.status, 200);
          assert.equal((await valid.json()).user_id, userId);
          assert.equal(
            (
              await fetch(path, {
                headers: { ...headers, Origin: config.APP_ORIGIN },
              })
            ).status,
            401,
          );
          assert.equal(
            (
              await fetch(path, {
                headers: { ...headers, Authorization: 'Bearer invalid' },
              })
            ).status,
            401,
          );
        },
      );
      await t.test(
        'missing sessions, invalid credentials and foreign origins are rejected',
        async () => {
          assert.equal((await call('/api/backend/me')).status, 401);
          assert.equal(
            (
              await call('/api/auth/sign-in/email', {
                email: emails[0],
                password: 'not-the-correct-password',
              })
            ).status,
            401,
          );
          assert.equal(
            (
              await call(
                '/api/auth/sign-up/email',
                { name: 'No', email: 'no@example.com', password },
                undefined,
                'https://untrusted.example',
              )
            ).status,
            403,
          );
          assert.equal(
            (
              await call('/api/auth/send-verification-email', {
                email: emails[0],
              })
            ).status,
            404,
          );
        },
      );
      await t.test(
        'organizations are returned only to their own members',
        async () => {
          const created = await call(
            '/api/auth/organization/create',
            { name: 'Test Organization', slug: `test-${prefix}` },
            cookie,
          );
          assert.equal(created.status, 200);
          const organization = await created.json();
          organizationId = organization.id;
          assert.ok(organizationId);
          const ours = await (
            await call('/api/backend/organizations', undefined, cookie)
          ).json();
          assert.equal(ours.organizations.length, 1);
          assert.equal(ours.organizations[0].organization.id, organizationId);
          assert.equal(ours.organizations[0].role, 'owner');
          const other = await call('/api/auth/sign-up/email', {
            name: 'Other Member',
            email: emails[1],
            password,
          });
          assert.equal(other.status, 200);
          otherCookie = other.headers
            .getSetCookie()
            .map((value) => value.split(';')[0])
            .join('; ');
          const theirs = await (
            await call('/api/backend/organizations', undefined, otherCookie)
          ).json();
          assert.equal(theirs.organizations.length, 0);
          assert.equal(
            (
              await call(
                '/api/auth/organization/get-full-organization?organizationId=' +
                  organizationId,
                undefined,
                otherCookie,
              )
            ).status,
            403,
          );
        },
      );
      await t.test(
        'logout invalidates the session and login creates a new valid session',
        async () => {
          assert.equal(
            (await call('/api/auth/sign-out', {}, cookie)).status,
            200,
          );
          assert.equal(
            (await call('/api/backend/me', undefined, cookie)).status,
            401,
          );
          const signedIn = await call('/api/auth/sign-in/email', {
            email: emails[0],
            password,
          });
          assert.equal(signedIn.status, 200);
          const freshCookie = signedIn.headers
            .getSetCookie()
            .map((value) => value.split(';')[0])
            .join('; ');
          assert.equal(
            (await call('/api/backend/me', undefined, freshCookie)).status,
            200,
          );
        },
      );
    } finally {
      try {
        if (organizationId)
          await database.organization.deleteMany({
            where: { id: organizationId },
          });
        await database.user.deleteMany({ where: { email: { in: emails } } });
      } finally {
        await new Promise<void>((resolve) => server.close(() => resolve()));
        await database.$disconnect();
      }
    }
  },
);
