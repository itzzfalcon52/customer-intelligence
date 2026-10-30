import { betterAuth } from 'better-auth';
import { prismaAdapter } from 'better-auth/adapters/prisma';
import { organization } from 'better-auth/plugins';
import { allowedOrigins, type Configuration } from '../config.js';
import type { Database } from './prisma.js';

export function createAuth(database: Database, config: Configuration) {
  return betterAuth({
    appName: 'Customer Intelligence',
    secret: config.BETTER_AUTH_SECRET,
    baseURL: config.APP_ORIGIN,
    basePath: '/api/auth',
    trustedOrigins: allowedOrigins(config),
    database: prismaAdapter(database, {
      provider: 'postgresql',
      transaction: true,
    }),
    emailAndPassword: {
      enabled: true,
      requireEmailVerification: false,
      autoSignIn: true,
      minPasswordLength: 12,
      maxPasswordLength: 128,
    },
    session: {
      expiresIn: 60 * 60 * 24 * 7,
      updateAge: 60 * 60 * 24,
      cookieCache: { enabled: false },
    },
    advanced: {
      useSecureCookies: config.NODE_ENV === 'production',
      ipAddress: { ipAddressHeaders: ['x-forwarded-for'] },
      defaultCookieAttributes: { httpOnly: true, sameSite: 'lax' },
    },
    rateLimit: {
      enabled: true,
      storage: 'database',
      window: 60,
      max: 100,
      customRules: {
        '/sign-in/email': { window: 60, max: 10 },
        '/sign-up/email': { window: 60, max: 5 },
      },
    },
    plugins: [organization()],
    logger: { disabled: true },
  });
}
export type Auth = ReturnType<typeof createAuth>;
