import { ArrowLeft, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { OrbitArt } from '../components/OrbitArt';

// Marketing preview only. This page never submits or stores account details.
export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const signup = mode === 'signup';
  return (
    <section className="auth-page">
      <div className="auth-art">
        <span className="eyebrow">
          A LITTLE MORE CONTEXT. A BETTER CONNECTION.
        </span>
        <h1>
          {signup ? (
            <>
              Your next chapter.
              <br />
              <em>More connected.</em>
            </>
          ) : (
            <>
              Good to have
              <br />
              <em>you back.</em>
            </>
          )}
        </h1>
        <OrbitArt compact />
        <div className="auth-art-footer">
          <span>✳</span>
          <p>
            The right next move starts
            <br />
            with a little understanding.
          </p>
        </div>
      </div>
      <div className="auth-form-panel">
        <Link to="/" className="text-link auth-back">
          <ArrowLeft size={15} /> Back to the story
        </Link>
        <div className="auth-form-content">
          <span className="eyebrow">
            {signup ? 'LET’S GET TO KNOW YOU' : 'PICK UP WHERE YOU LEFT OFF'}
          </span>
          <h2>{signup ? 'Start with a connection.' : 'Welcome back.'}</h2>
          <p>Your customer story, in your own workspace.</p>
          <p className="auth-notice">
            Account access is not enabled. This is a design preview.
          </p>
          {signup && (
            <div className="form-field">
              <label htmlFor="auth-name">Your name</label>
              <input id="auth-name" placeholder="Your name" disabled />
            </div>
          )}
          <div className="form-field">
            <label htmlFor="auth-email">Email address</label>
            <input
              id="auth-email"
              type="email"
              placeholder="you@example.com"
              disabled
            />
          </div>
          <div className="form-field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              placeholder="Password"
              disabled
            />
          </div>
          <button className="button button-dark auth-submit" disabled>
            {signup ? 'Create account' : 'Sign in'} <ArrowUpRight size={18} />
          </button>
          <p className="auth-switch">
            {signup ? 'Already have an account?' : 'First time here?'}{' '}
            <Link to={signup ? '/login' : '/signup'}>
              {signup ? 'Sign in' : 'Get started'} <ArrowUpRight size={13} />
            </Link>
          </p>
        </div>
        <span className="auth-fine-print">People first. Evidence always.</span>
      </div>
    </section>
  );
}
