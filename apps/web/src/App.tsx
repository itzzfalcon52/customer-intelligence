import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { SiteLayout } from './components/SiteLayout';
import { HomePage } from './pages/HomePage';
import { FeaturesPage } from './pages/FeaturesPage';
import { PricingPage } from './pages/PricingPage';
import { NotFoundPage } from './pages/NotFoundPage';
// The account forms (and Zod validation) load only when an account route is visited.
const AuthPage = lazy(() =>
  import('./pages/AuthPage').then((module) => ({ default: module.AuthPage })),
);

function AccountRoute({ mode }: { mode: 'login' | 'signup' }) {
  return (
    <Suspense
      fallback={
        <section className="route-loading" role="status">
          Opening your next chapter…
        </section>
      }
    >
      <AuthPage mode={mode} />
    </Suspense>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route index element={<HomePage />} />
          <Route path="features" element={<FeaturesPage />} />
          <Route path="pricing" element={<PricingPage />} />
          <Route path="login" element={<AccountRoute mode="login" />} />
          <Route path="signup" element={<AccountRoute mode="signup" />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
