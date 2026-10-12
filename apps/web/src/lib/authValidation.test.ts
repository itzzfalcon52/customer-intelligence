import { describe, expect, it } from 'vitest';
import { loginSchema, signupSchema } from './authValidation';
describe('account validation', () => {
  it('rejects malformed email', () =>
    expect(
      loginSchema.safeParse({ email: 'wrong', password: 'secret' }).success,
    ).toBe(false));
  it('requires 12 characters for new passwords', () =>
    expect(
      signupSchema.safeParse({
        name: 'Alex',
        email: 'alex@example.com',
        password: 'short',
      }).success,
    ).toBe(false));
  it('preserves intentional spaces in passwords', () =>
    expect(
      signupSchema.parse({
        name: 'Alex',
        email: ' alex@example.com ',
        password: '  a long password  ',
      }).password,
    ).toBe('  a long password  '));
  it('rejects oversized passwords', () =>
    expect(
      signupSchema.safeParse({
        name: 'Alex',
        email: 'alex@example.com',
        password: 'a'.repeat(129),
      }).success,
    ).toBe(false));
});
