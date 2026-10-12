import { z } from 'zod';
export const loginSchema = z.object({
  email: z.string().trim().email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.').max(128),
});
export const passwordSchema = z
  .string()
  .min(12, 'Use at least 12 characters.')
  .max(128, 'Use no more than 128 characters.');
export const signupSchema = loginSchema.extend({
  name: z
    .string()
    .trim()
    .min(2, 'Enter your name (at least 2 characters).')
    .max(100),
  password: passwordSchema,
});
export type AuthErrors = Partial<Record<'name' | 'email' | 'password', string>>;
