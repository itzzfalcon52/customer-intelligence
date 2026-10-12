import { lazy, Suspense, useState } from 'react';
import { ArrowRight, ArrowUpRight, Menu, X } from 'lucide-react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { Brand } from './Brand';
import { DemoDialog } from './DemoDialog';
import { usePageEffects } from '../hooks/usePageEffects';

const AccountLinks = lazy(() =>
  import('./AccountLinks').then((module) => ({ default: module.AccountLinks })),
);

export type SiteContext = { openDemo: () => void };
export function SiteLayout() {
  const [menuForPath, setMenuForPath] = useState<string | null>(null);
  const [demoOpen, setDemoOpen] = useState(false);
  const { pathname } = useLocation();
  const menuOpen = menuForPath === pathname;
  usePageEffects();
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="site-header">
        <Brand />
        <nav
          className={`desktop-nav ${menuOpen ? 'nav-open' : ''}`}
          id="site-navigation"
          aria-label="Main navigation"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setMenuForPath(null);
              document.getElementById('menu-toggle')?.focus();
            }
          }}
        >
          <NavLink to="/features" onClick={() => setMenuForPath(null)}>
            The platform
          </NavLink>
          <NavLink to="/pricing" onClick={() => setMenuForPath(null)}>
            Pricing
          </NavLink>
          <button
            onClick={() => {
              setMenuForPath(null);
              setDemoOpen(true);
            }}
          >
            Take a tour <ArrowUpRight size={14} />
          </button>
          <Link
            to="/login"
            className="mobile-login"
            onClick={() => setMenuForPath(null)}
          >
            Log in
          </Link>
        </nav>
        <div className="header-actions">
          <Suspense
            fallback={
              <Link className="button button-dark button-small" to="/signup">
                Get started <ArrowUpRight size={15} />
              </Link>
            }
          >
            <AccountLinks />
          </Suspense>
          <button
            id="menu-toggle"
            className="menu-toggle icon-button"
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={menuOpen}
            aria-controls="site-navigation"
            onClick={() => setMenuForPath(menuOpen ? null : pathname)}
          >
            {menuOpen ? <X /> : <Menu />}
          </button>
        </div>
      </header>
      <main id="main-content" tabIndex={-1}>
        <Outlet
          context={{ openDemo: () => setDemoOpen(true) } satisfies SiteContext}
        />
      </main>
      <footer className="site-footer">
        <div className="footer-top">
          <div>
            <Brand inverse />
            <p>
              For the customers you have.
              <br />
              And the relationships ahead.
            </p>
          </div>
          <div className="footer-links">
            <span>EXPLORE</span>
            <Link to="/features">
              The platform <ArrowUpRight size={13} />
            </Link>
            <Link to="/pricing">
              Pricing <ArrowUpRight size={13} />
            </Link>
            <button onClick={() => setDemoOpen(true)}>
              Product tour <ArrowUpRight size={13} />
            </button>
          </div>
          <div className="footer-links">
            <span>YOUR NEXT CHAPTER</span>
            <Link to="/signup">
              Get started <ArrowRight size={13} />
            </Link>
            <Link to="/login">
              Log in <ArrowRight size={13} />
            </Link>
            <Link to="/features#roadmap">
              What’s coming <ArrowRight size={13} />
            </Link>
          </div>
          <div className="footer-signoff">
            Less guesswork.
            <br />
            <span>More connection.</span>
            <svg viewBox="0 0 80 80" aria-hidden="true">
              <path
                d="M40 2 48 26 73 14 58 37 78 47 52 49 53 76 39 55 20 76 26 50 1 44 27 34 12 11 36 26Z"
                fill="currentColor"
              />
            </svg>
          </div>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} Customer Intelligence</span>
          <span>Built with curiosity. Designed for people.</span>
          <span className="footer-preview">
            <i /> Product preview
          </span>
        </div>
      </footer>
      <DemoDialog open={demoOpen} onClose={() => setDemoOpen(false)} />
    </>
  );
}
