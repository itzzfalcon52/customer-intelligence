import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { ArrowUpRight, Menu, X } from 'lucide-react';
import { authClient } from '../lib/auth';
import { Logo } from './Logo';
import { cn } from '../workspace/style';

const TITLES: Record<string, string> = {
  '/': 'Know who is slipping before they let go',
  '/product': 'Product',
  '/nemotron': 'How Nemotron is used',
  '/pricing': 'Pricing',
  '/login': 'Sign in',
  '/signup': 'Create your account',
};

/** Buttons are cut like tags: the corners at the hanging end are clipped. */
export const TAG_BUTTON =
  'inline-flex h-11 items-center gap-2 px-5 font-display text-[15px] font-[700] transition [clip-path:polygon(10px_0,100%_0,100%_100%,10px_100%,0_50%)] pl-6';

const LINKS: [string, string][] = [
  ['/product', 'Product'],
  ['/nemotron', 'Nemotron'],
  ['/pricing', 'Pricing'],
];

export function SiteLayout() {
  const { pathname, hash } = useLocation();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const session = authClient.useSession();
  const auth = pathname === '/login' || pathname === '/signup';
  useEffect(() => {
    document.title = `${TITLES[pathname] ?? 'Page not found'} · Holdfast`;
    const target = hash ? document.getElementById(hash.slice(1)) : null;
    if (target) target.scrollIntoView();
    else window.scrollTo({ top: 0 });
  }, [pathname, hash]);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  if (auth) return <Outlet />;
  return (
    <div className="site min-h-screen bg-field-800 font-display text-stock">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100] focus:bg-stock focus:px-3 focus:py-2 focus:text-tag-ink"
      >
        Skip to content
      </a>
      <header
        className={cn(
          'fixed inset-x-0 top-0 z-50 transition-[background-color,box-shadow] duration-300',
          scrolled
            ? 'bg-field-900 shadow-[0_1px_0_0_rgb(245_247_244/0.12),0_12px_30px_-18px_rgb(0_0_0/0.6)]'
            : 'bg-transparent',
        )}
      >
        <div className="mx-auto flex h-[72px] max-w-[1320px] items-center gap-10 px-5 sm:px-8">
          <Link
            to="/"
            onClick={() => setOpen(false)}
            aria-label="Holdfast home"
          >
            <Logo dark />
          </Link>
          <nav
            className="hidden flex-1 items-center gap-1 md:flex"
            aria-label="Main"
          >
            {LINKS.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    'relative px-3 py-2 text-[15px] font-[560] transition',
                    isActive ? 'text-stock' : 'text-field-200 hover:text-stock',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {label}
                    {isActive && (
                      <motion.span
                        layoutId="nav-mark"
                        aria-hidden="true"
                        className="absolute top-[52px] left-1/2 h-4 w-7 -translate-x-1/2 bg-tag-red [clip-path:polygon(0_0,100%_0,100%_70%,50%_100%,0_70%)]"
                      />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto hidden items-center gap-3 md:flex">
            {session.data ? (
              <Link
                to="/app"
                className={cn(
                  TAG_BUTTON,
                  'bg-stock text-tag-ink hover:bg-white',
                )}
              >
                Open workspace <ArrowUpRight className="size-4" />
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="px-3 py-2 text-[15px] font-[560] text-field-200 transition hover:text-stock"
                >
                  Sign in
                </Link>
                <Link
                  to="/signup"
                  className={cn(
                    TAG_BUTTON,
                    'bg-stock text-tag-ink hover:bg-white',
                  )}
                >
                  Start free
                </Link>
              </>
            )}
          </div>
          <button
            className="ml-auto cursor-pointer p-2 text-stock md:hidden"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {open ? <X className="size-6" /> : <Menu className="size-6" />}
          </button>
        </div>
        {/* The clipboard rail the nav hangs from, held by two clips. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-[66px] hidden md:block"
        >
          <div className="mx-auto max-w-[1320px] px-5 sm:px-8">
            <div className="relative h-[3px] rounded-full bg-gradient-to-b from-[#d6dbd7] to-[#7f8b87] shadow-[0_2px_3px_rgb(0_0_0/0.35)]">
              <span className="absolute -top-[5px] left-[14%] h-[13px] w-5 rounded-[2px] bg-gradient-to-b from-[#e3e7e4] to-[#8f9a96]" />
              <span className="absolute -top-[5px] right-[14%] h-[13px] w-5 rounded-[2px] bg-gradient-to-b from-[#e3e7e4] to-[#8f9a96]" />
            </div>
          </div>
        </div>
        <AnimatePresence>
          {open && (
            <motion.nav
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden bg-field-900 md:hidden"
              aria-label="Mobile"
            >
              <div className="space-y-1 px-5 pt-2 pb-6">
                {[...LINKS, ['/login', 'Sign in'] as [string, string]].map(
                  ([to, label]) => (
                    <Link
                      key={to}
                      to={to}
                      onClick={() => setOpen(false)}
                      className="block border-b border-stock/10 py-3.5 text-[22px] font-[720] text-stock"
                      style={{ fontStretch: '80%' }}
                    >
                      {label}
                    </Link>
                  ),
                )}
                <Link
                  to="/signup"
                  onClick={() => setOpen(false)}
                  className={cn(
                    TAG_BUTTON,
                    'mt-5 w-full justify-center bg-stock text-tag-ink',
                  )}
                >
                  Start free
                </Link>
              </div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>
      <main id="main-content" tabIndex={-1} className="outline-none">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}

function Footer() {
  return (
    <footer className="overflow-hidden bg-field-950 text-field-200">
      <div className="mx-auto grid max-w-[1320px] gap-10 px-5 pt-16 pb-10 sm:px-8 md:grid-cols-[1.6fr_1fr_1fr_1fr]">
        <div>
          <Logo dark />
          <p className="mt-5 max-w-sm text-[15px] leading-relaxed">
            Churn risk measured by models, explained by NVIDIA Nemotron, checked
            by code, and proven with holdout groups.
          </p>
        </div>
        {[
          [
            'Product',
            [
              ['/product', 'How it works'],
              ['/nemotron', 'How Nemotron is used'],
              ['/pricing', 'Pricing'],
            ],
          ],
          [
            'Account',
            [
              ['/signup', 'Start free'],
              ['/login', 'Sign in'],
              ['/app', 'Workspace'],
            ],
          ],
          [
            'Honesty',
            [
              ['/nemotron#what-it-sees', 'What the AI sees'],
              ['/nemotron#checks', 'How answers are checked'],
              ['/pricing#coming-soon', 'Coming soon'],
            ],
          ],
        ].map(([title, links]) => (
          <div key={title as string}>
            <p className="text-[13px] font-[700] tracking-[0.08em] text-stock uppercase">
              {title as string}
            </p>
            <ul className="mt-4 space-y-2.5 text-[15px]">
              {(links as [string, string][]).map(([to, label]) => (
                <li key={to}>
                  <Link className="transition hover:text-stock" to={to}>
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-stock/10 bg-field-950">
        <p className="mx-auto max-w-[1320px] px-5 py-5 text-[12px] text-field-300 sm:px-8">
          © {new Date().getFullYear()} Holdfast · Product preview · Demo screens
          use labelled synthetic data · AI by NVIDIA Nemotron, served on Nebius
        </p>
      </div>
    </footer>
  );
}
