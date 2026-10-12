import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export function FinalCTA() {
  return (
    <section className="final-cta" data-reveal>
      <div className="cta-orbit" aria-hidden="true">
        <span />
        <span />
        <span />
        <i>✳</i>
      </div>
      <div>
        <span className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</span>
        <h2>
          Keep the connection.
          <br />
          <em>Change the story.</em>
        </h2>
        <Link to="/signup" className="button button-lime">
          Let’s get started <ArrowUpRight size={20} />
        </Link>
      </div>
      <p>
        Your data. Your judgment.
        <br />A little more intelligence.
      </p>
    </section>
  );
}
