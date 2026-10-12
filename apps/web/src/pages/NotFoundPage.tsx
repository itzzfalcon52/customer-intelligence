import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
export function NotFoundPage() {
  return (
    <section className="not-found">
      <span className="eyebrow">404 / A SMALL DETOUR</span>
      <h1>Lost the signal?</h1>
      <p>Let’s get you back to the story.</p>
      <Link to="/" className="button button-dark">
        <ArrowLeft size={18} /> Back home
      </Link>
    </section>
  );
}
