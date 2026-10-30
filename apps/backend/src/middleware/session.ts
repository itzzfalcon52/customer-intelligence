import type { RequestHandler } from 'express';
import { fromNodeHeaders } from 'better-auth/node';
import type { Auth } from '../lib/auth.js';
export function requireSession(auth: Auth): RequestHandler {
  return async (request, response, next) => {
    try {
      const session = await auth.api.getSession({
        headers: fromNodeHeaders(request.headers),
      });
      if (!session) {
        response.status(401).json({ message: 'Sign in to continue.' });
        return;
      }
      response.locals.identity = session.user;
      next();
    } catch {
      response
        .status(503)
        .json({ message: 'Account service is unavailable. Please try again.' });
    }
  };
}
