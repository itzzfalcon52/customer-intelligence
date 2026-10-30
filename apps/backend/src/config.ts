import { config } from 'dotenv';
import { z } from 'zod';
config({ path: new URL('../.env', import.meta.url), quiet: true });
const schema = z.object({
  INTERNAL_API_SECRET: z.string().min(32).optional(),
  DATABASE_URL: z
    .string()
    .min(1)
    .refine((value) => {
      try {
        return ['postgres:', 'postgresql:'].includes(new URL(value).protocol);
      } catch {
        return false;
      }
    }),
  BETTER_AUTH_SECRET: z.string().min(32),
  APP_ORIGIN: z
    .string()
    .url()
    .default('http://127.0.0.1:5173')
    .refine((value) => new URL(value).origin === value),
  PORT: z.coerce.number().int().min(1024).max(65535).default(3001),
  // Loopback by default; a container sets 0.0.0.0 and stays unpublished behind the proxy.
  HOST: z.string().default('127.0.0.1'),
  // Behind Caddy only: trust the client address the proxy writes into X-Forwarded-For.
  TRUST_PROXY: z
    .enum(['true', 'false'])
    .default('false')
    .transform((value) => value === 'true'),
  NODE_ENV: z
    .enum(['development', 'test', 'production'])
    .default('development'),
});
export function readConfig(environment: NodeJS.ProcessEnv = process.env) {
  const parsed = schema.safeParse(environment);
  if (!parsed.success) {
    // Report field names only: connection strings contain credentials.
    throw new Error(
      `Configure apps/backend/.env: ${parsed.error.issues.map((issue) => issue.path.join('.')).join(', ')}.`,
    );
  }
  if (
    parsed.data.NODE_ENV === 'production' &&
    !parsed.data.APP_ORIGIN.startsWith('https://')
  ) {
    throw new Error('Production APP_ORIGIN must use HTTPS.');
  }
  return parsed.data;
}
export type Configuration = ReturnType<typeof readConfig>;
