import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

const titles: Record<string, string> = {
  '/': 'Know who needs you. Before they leave.',
  '/features': 'A clearer path from signals to action',
  '/pricing': 'Room to start. Space to grow.',
  '/login': 'Welcome back',
  '/signup': 'Start your next chapter',
};

/** Route-aware focus, scroll and lightweight one-shot section reveals. */
export function usePageEffects() {
  const { pathname, hash } = useLocation();
  const previousPath = useRef(pathname);
  useEffect(() => {
    document.title = `${titles[pathname] ?? 'Page not found'} | Customer Intelligence`;
    const target = hash ? document.getElementById(hash.slice(1)) : null;
    if (target) target.scrollIntoView({ behavior: 'instant' });
    else window.scrollTo({ top: 0, behavior: 'instant' });
    // Focus only on a route change, not on first load or an in-page anchor.
    if (previousPath.current !== pathname) {
      document.getElementById('main-content')?.focus({ preventScroll: true });
      previousPath.current = pathname;
    }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.setAttribute('data-visible', 'true');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08 },
    );
    document.querySelectorAll('[data-reveal]').forEach((element) => {
      // Content near the top is immediately visible; no blocking hero entrance.
      if (element.getAttribute('data-visible') === 'true') return;
      if (element.getBoundingClientRect().top < window.innerHeight) {
        element.setAttribute('data-visible', 'true');
        return;
      }
      element.setAttribute('data-visible', 'false');
      observer.observe(element);
    });
    return () => observer.disconnect();
  }, [pathname, hash]);
}
