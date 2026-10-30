import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  Loader2,
} from 'lucide-react';
import { motion } from 'motion/react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { authClient } from '../lib/auth';
import { loginSchema, signupSchema } from '../lib/authValidation';
import type { AuthErrors } from '../lib/authValidation';
import { Logo } from '../components/Logo';
import { MiniTag } from '../components/site/Tag';
import { ACCOUNTS } from '../components/site/tags';
import { TAG_BUTTON } from '../components/SiteLayout';

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  return <AuthForm key={mode} mode={mode} />;
}
function AuthForm({ mode }: { mode: 'login' | 'signup' }) {
  const signup = mode === 'signup';
  const session = authClient.useSession();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [errors, setErrors] = useState<AuthErrors>({});
  const [showPassword, setShowPassword] = useState(false);
  if (session.data) return <Navigate to="/app" replace />;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const fields = new FormData(form);
    const result = (signup ? signupSchema : loginSchema).safeParse({
      name: fields.get('name'),
      email: fields.get('email'),
      password: fields.get('password'),
    });
    if (!result.success) {
      const next: AuthErrors = {};
      for (const issue of result.error.issues) {
        const field = issue.path[0] as keyof AuthErrors;
        next[field] ??= issue.message;
      }
      setErrors(next);
      (
        form.elements.namedItem(
          String(result.error.issues[0]?.path[0]),
        ) as HTMLElement | null
      )?.focus();
      return;
    }
    setErrors({});
    setMessage('');
    setBusy(true);
    try {
      const values = result.data;
      const response = signup
        ? await authClient.signUp.email({
            ...values,
            name: 'name' in values ? String(values.name) : '',
          })
        : await authClient.signIn.email({
            email: values.email,
            password: values.password,
          });
      if (response.error) {
        setMessage(
          response.error.status >= 500 || response.error.status === 0
            ? 'Account service is unavailable. Please try again shortly.'
            : response.error.status === 429
              ? 'Too many attempts. Please wait a minute and try again.'
              : signup
                ? 'Unable to create this account. Check your details, or sign in if you already registered.'
                : 'Unable to sign in. Check your email and password.',
        );
      } else {
        form.reset();
        navigate('/app', { replace: true });
      }
    } catch {
      setMessage('Account service is unavailable. Please try again shortly.');
    } finally {
      setBusy(false);
    }
  }
  const input =
    'h-12 w-full border-0 bg-white px-3.5 text-[16px] text-tag-ink ring-1 ring-inset ring-tag-ink/20 transition placeholder:text-tag-slate hover:ring-tag-ink/40 focus:ring-2 focus:ring-field-700 focus:outline-none aria-[invalid=true]:ring-tag-red';
  const fieldError = (id: string, text?: string) =>
    text && (
      <span id={id} className="text-[13px] text-tag-red">
        {text}
      </span>
    );
  return (
    <div className="site grid min-h-screen bg-stock font-display text-tag-ink lg:grid-cols-2">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <div className="flex items-center justify-between">
          <Link to="/">
            <Logo />
          </Link>
          <Link
            to="/"
            className="inline-flex items-center gap-1 text-[15px] font-[560] text-tag-slate hover:text-tag-ink"
          >
            <ArrowLeft className="size-4" /> Home
          </Link>
        </div>
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-12"
        >
          <h1
            className="text-[44px] leading-[0.95] font-[840] tracking-[-0.02em]"
            style={{ fontStretch: '68%' }}
          >
            {signup ? 'Create your account' : 'Welcome back'}
          </h1>
          <p className="mt-3 text-[16px] text-[#3b4441]">
            {signup
              ? 'Find your at-risk customers in minutes. Free during the preview.'
              : 'Sign in to your workspace.'}
          </p>
          {message && (
            <p
              className="mt-6 bg-tag-red px-4 py-3 text-[14px] text-stock"
              role="alert"
            >
              {message}
            </p>
          )}
          <form
            onSubmit={(event) => void submit(event)}
            noValidate
            className="mt-8 space-y-5"
          >
            {signup && (
              <label className="flex flex-col gap-1.5">
                <span className="text-[14px] font-[640]">Your name</span>
                <input
                  id="auth-name"
                  name="name"
                  autoComplete="name"
                  maxLength={100}
                  required
                  className={input}
                  aria-invalid={Boolean(errors.name)}
                  aria-describedby={errors.name ? 'name-error' : undefined}
                />
                {fieldError('name-error', errors.name)}
              </label>
            )}
            <label className="flex flex-col gap-1.5">
              <span className="text-[14px] font-[640]">Work email</span>
              <input
                id="auth-email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                maxLength={254}
                required
                className={input}
                aria-invalid={Boolean(errors.email)}
                aria-describedby={errors.email ? 'email-error' : undefined}
              />
              {fieldError('email-error', errors.email)}
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-[14px] font-[640]">Password</span>
              <span className="relative">
                <input
                  id="auth-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete={signup ? 'new-password' : 'current-password'}
                  placeholder={
                    signup ? 'At least 12 characters' : 'Your password'
                  }
                  maxLength={128}
                  required
                  className={`${input} pr-11`}
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={
                    errors.password ? 'password-error' : undefined
                  }
                />
                <button
                  type="button"
                  className="absolute top-1/2 right-3 -translate-y-1/2 cursor-pointer text-tag-slate hover:text-tag-ink"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? (
                    <EyeOff className="size-4" />
                  ) : (
                    <Eye className="size-4" />
                  )}
                </button>
              </span>
              {fieldError('password-error', errors.password)}
            </label>
            <button
              type="submit"
              disabled={busy}
              className={`${TAG_BUTTON} h-12 w-full cursor-pointer justify-center bg-tag-ink text-[16px] text-stock hover:bg-field-800 disabled:opacity-60`}
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : null}
              {busy ? 'Connecting…' : signup ? 'Create account' : 'Sign in'}
              {!busy && <ArrowRight className="size-4" />}
            </button>
          </form>
          <p className="mt-6 text-center text-[15px] text-tag-slate">
            {signup ? 'Already have an account?' : 'New here?'}{' '}
            <Link
              to={signup ? '/login' : '/signup'}
              className="font-[700] text-tag-ink underline decoration-tag-red decoration-2 underline-offset-4"
            >
              {signup ? 'Sign in' : 'Create an account'}
            </Link>
          </p>
        </motion.div>
      </div>
      <div className="relative hidden overflow-hidden bg-field-800 text-stock lg:flex lg:flex-col lg:justify-between lg:px-14 lg:py-16">
        <h2
          className="max-w-[14ch] text-[clamp(2.6rem,4vw,4rem)] leading-[0.9] font-[840] tracking-[-0.02em]"
          style={{ fontStretch: '66%' }}
        >
          Tomorrow’s board, triaged and explained.
        </h2>
        <div className="relative h-[440px]" aria-hidden="true">
          {ACCOUNTS.slice(0, 3).map((account, i) => (
            <motion.div
              key={account.id}
              initial={{ y: -120, opacity: 0, rotate: -10 }}
              animate={{ y: 0, opacity: 1, rotate: [-5, 3, -2][i] }}
              transition={{
                type: 'spring',
                stiffness: 90,
                damping: 11,
                delay: 0.2 + i * 0.18,
              }}
              className="absolute origin-top"
              style={{
                left: `${[4, 36, 18][i]}%`,
                top: `${[0, 70, 190][i]}px`,
              }}
            >
              <MiniTag account={account} />
            </motion.div>
          ))}
        </div>
        <ul className="space-y-3 text-[15px] text-field-100">
          {[
            'Every account ranked, with what stands out',
            'Nemotron notes, every number checked',
            'Nothing sent to a customer without approval',
          ].map((t) => (
            <li key={t} className="flex items-center gap-3">
              <Check className="size-4 text-tag-amber" strokeWidth={3} />
              {t}
            </li>
          ))}
          <li className="pt-2 text-[12px] text-field-300">
            Tags show synthetic demo accounts.
          </li>
        </ul>
      </div>
    </div>
  );
}
