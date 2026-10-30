import { randomUUID, timingSafeEqual } from 'node:crypto';
import { fromNodeHeaders } from 'better-auth/node';
import express from 'express';
import helmet from 'helmet';
import { toNodeHandler } from 'better-auth/node';
import type { Auth } from './lib/auth.js';
import type { Database } from './lib/prisma.js';
import type { Configuration } from './config.js';
import { requireSession } from './middleware/session.js';

export function createApp(
  auth: Auth,
  database: Database,
  config: Configuration,
) {
  const app = express();
  app.disable('x-powered-by');
  app.use(helmet());
  app.use((request, response, next) => {
    response.setHeader('Cache-Control', 'no-store');
    // Rate limits key on the client address. Locally the socket address is the client; behind
    // the production proxy, Caddy overwrites X-Forwarded-For with the real client address
    // (it ignores client-supplied values), so the last entry is trustworthy there only.
    const forwarded = String(request.headers['x-forwarded-for'] ?? '')
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)
      .pop();
    request.headers['x-forwarded-for'] =
      config.TRUST_PROXY && forwarded
        ? forwarded
        : request.socket.remoteAddress || '127.0.0.1';
    if (
      !['GET', 'HEAD', 'OPTIONS'].includes(request.method) &&
      request.headers.origin &&
      request.headers.origin !== config.APP_ORIGIN
    ) {
      response.status(403).json({ message: 'Request origin is not allowed.' });
      return;
    }
    if (Number(request.headers['content-length'] || 0) > 32 * 1024) {
      response.status(413).json({ message: 'Request is too large.' });
      return;
    }
    next();
  });
  app.get('/health', async (_request, response) => {
    try {
      await database.$queryRaw`SELECT 1`;
      response.json({ status: 'ok', service: 'customer-intelligence-backend' });
    } catch {
      response.status(503).json({
        status: 'unavailable',
        message: 'Account database is unavailable.',
      });
    }
  });
  app.get('/internal/identity', async (request, response) => {
    const expected = config.INTERNAL_API_SECRET;
    const supplied = request.headers.authorization || '';
    if (
      request.headers.origin ||
      !expected ||
      supplied.length !== expected.length + 7 ||
      !timingSafeEqual(Buffer.from(supplied), Buffer.from('Bearer ' + expected))
    ) {
      response.status(401).json({ message: 'Unauthorized.' });
      return;
    }
    try {
      const session = await auth.api.getSession({
        headers: fromNodeHeaders(request.headers),
      });
      if (!session) {
        response.status(401).json({ message: 'Sign in to continue.' });
        return;
      }
      // An active organisation counts only while the user is still a member of it.
      const organizationId = session.session.activeOrganizationId;
      const membership = organizationId
        ? await database.member.findUnique({
            where: {
              organizationId_userId: {
                organizationId,
                userId: session.user.id,
              },
            },
            select: { role: true },
          })
        : null;
      response.json({
        user_id: session.user.id,
        organization_id: membership ? organizationId : null,
        role: membership ? membership.role : 'owner',
        // For email digests the user opts into; the API never stores it otherwise.
        email: session.user.email,
      });
    } catch {
      response.status(503).json({ message: 'Account service unavailable.' });
    }
  });
  // No email provider, Google sign-in, invitations or recovery flows in this milestone.
  app.use('/api/auth', (request, response, next) => {
    if (
      /^\/(request-password-reset|reset-password|send-verification-email|verify-email|organization\/(invite-member|accept-invitation|reject-invitation))\/?$/.test(
        request.path,
      )
    ) {
      response
        .status(404)
        .json({ message: 'This account feature is not enabled.' });
      return;
    }
    next();
  });
  // Better Auth owns its request parsing. Mount before express.json().
  app.all('/api/auth/*splat', toNodeHandler(auth));
  app.use(express.json({ limit: '32kb' }));
  app.get('/api/backend/me', requireSession(auth), (_request, response) => {
    const { id, name, email, image } = response.locals.identity;
    response.json({ user: { id, name, email, image } });
  });
  app.get(
    '/api/backend/organizations',
    requireSession(auth),
    async (_request, response) => {
      const memberships = await database.member.findMany({
        where: { userId: response.locals.identity.id },
        select: {
          role: true,
          organization: { select: { id: true, name: true, slug: true } },
        },
      });
      response.json({ organizations: memberships });
    },
  );
  const MEMBER_ROLES = ['admin', 'member', 'viewer'];
  async function managerOf(userId: string, organizationId: string) {
    const member = await database.member.findUnique({
      where: { organizationId_userId: { organizationId, userId } },
      select: { role: true },
    });
    return member && ['owner', 'admin'].includes(member.role);
  }
  app.get(
    '/api/backend/organizations/:id/members',
    requireSession(auth),
    async (request, response) => {
      const organizationId = String(request.params.id);
      const self = await database.member.findUnique({
        where: {
          organizationId_userId: {
            organizationId,
            userId: response.locals.identity.id,
          },
        },
      });
      if (!self) {
        response.status(404).json({ message: 'Organisation not found.' });
        return;
      }
      const members = await database.member.findMany({
        where: { organizationId },
        orderBy: { createdAt: 'asc' },
        select: {
          id: true,
          role: true,
          user: { select: { name: true, email: true } },
        },
      });
      response.json({ members, role: self.role });
    },
  );
  // Adds an existing account by email. No invitation emails exist in this product.
  app.post(
    '/api/backend/organizations/:id/members',
    requireSession(auth),
    async (request, response) => {
      const organizationId = String(request.params.id);
      if (!(await managerOf(response.locals.identity.id, organizationId))) {
        response
          .status(403)
          .json({ message: 'Only owners and admins can add members.' });
        return;
      }
      const email = String(request.body?.email ?? '')
        .trim()
        .toLowerCase();
      const role = String(request.body?.role ?? 'member');
      if (!email || email.length > 254 || !MEMBER_ROLES.includes(role)) {
        response.status(400).json({
          message: 'Give an email and a role: admin, member or viewer.',
        });
        return;
      }
      const user = await database.user.findUnique({ where: { email } });
      if (!user) {
        response.status(404).json({
          message: 'No account uses that email. Ask them to sign up first.',
        });
        return;
      }
      try {
        const member = await database.member.create({
          data: {
            id: randomUUID(),
            organizationId,
            userId: user.id,
            role,
          },
          select: { id: true, role: true },
        });
        response.status(201).json(member);
      } catch {
        response
          .status(409)
          .json({ message: 'That account is already a member.' });
      }
    },
  );
  // A member leaves a team. The owner cannot leave (they would orphan the workspace).
  app.delete(
    '/api/backend/organizations/:id/members/me',
    requireSession(auth),
    async (request, response) => {
      const organizationId = String(request.params.id);
      const member = await database.member.findUnique({
        where: {
          organizationId_userId: {
            organizationId,
            userId: response.locals.identity.id,
          },
        },
      });
      if (!member) {
        response.status(404).json({ message: 'You are not in this team.' });
        return;
      }
      if (member.role === 'owner') {
        response
          .status(409)
          .json({ message: 'The owner cannot leave their own team.' });
        return;
      }
      await database.member.delete({ where: { id: member.id } });
      response.status(204).end();
    },
  );
  app.patch(
    '/api/backend/organizations/:id/members/:memberId',
    requireSession(auth),
    async (request, response) => {
      const organizationId = String(request.params.id);
      if (!(await managerOf(response.locals.identity.id, organizationId))) {
        response
          .status(403)
          .json({ message: 'Only owners and admins can change roles.' });
        return;
      }
      const role = String(request.body?.role ?? '');
      if (!MEMBER_ROLES.includes(role)) {
        response
          .status(400)
          .json({ message: 'Choose a role: admin, member or viewer.' });
        return;
      }
      const member = await database.member.findFirst({
        where: { id: String(request.params.memberId), organizationId },
      });
      if (!member || member.role === 'owner') {
        response.status(member ? 409 : 404).json({
          message: member
            ? "The owner's role cannot be changed."
            : 'Member not found.',
        });
        return;
      }
      const updated = await database.member.update({
        where: { id: member.id },
        data: { role },
        select: { id: true, role: true },
      });
      response.json(updated);
    },
  );
  app.delete(
    '/api/backend/organizations/:id/members/:memberId',
    requireSession(auth),
    async (request, response) => {
      const organizationId = String(request.params.id);
      if (!(await managerOf(response.locals.identity.id, organizationId))) {
        response
          .status(403)
          .json({ message: 'Only owners and admins can remove members.' });
        return;
      }
      const member = await database.member.findFirst({
        where: { id: String(request.params.memberId), organizationId },
      });
      if (!member || member.role === 'owner') {
        response.status(member ? 409 : 404).json({
          message: member
            ? 'The owner cannot be removed.'
            : 'Member not found.',
        });
        return;
      }
      await database.member.delete({ where: { id: member.id } });
      response.status(204).end();
    },
  );
  app.use((_request, response) => {
    response.status(404).json({ message: 'Endpoint not found.' });
  });
  app.use(((
    error: unknown,
    _request: express.Request,
    response: express.Response,
    _next: express.NextFunction,
  ) => {
    const status =
      error &&
      typeof error === 'object' &&
      'status' in error &&
      error.status === 413
        ? 413
        : 503;
    response.status(status).json({
      message:
        status === 413
          ? 'Request is too large.'
          : 'Account service is unavailable. Please try again.',
    });
  }) as express.ErrorRequestHandler);
  return app;
}
