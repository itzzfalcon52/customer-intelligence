import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from '../generated/prisma/client.js';
export function createPrisma(connectionString: string) {
  return new PrismaClient({
    adapter: new PrismaPg({ connectionString, connectionTimeoutMillis: 5000 }),
    log: [],
  });
}
export type Database = ReturnType<typeof createPrisma>;
