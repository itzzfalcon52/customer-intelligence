import { Link } from 'react-router-dom';

export function Brand({ inverse = false }: { inverse?: boolean }) {
  return (
    <Link
      to="/"
      className={`brand ${inverse ? 'brand-inverse' : ''}`}
      aria-label="Customer Intelligence home"
    >
      <svg viewBox="0 0 40 40" aria-hidden="true">
        <path
          d="M20 3 26 12 37 14 30 23 31 35 20 30 9 35 10 23 3 14 14 12Z"
          fill="currentColor"
        />
        <circle cx="20" cy="20" r="5" fill={inverse ? '#211131' : '#faf8f3'} />
      </svg>
      <span>
        customer
        <br />
        intelligence
      </span>
    </Link>
  );
}
