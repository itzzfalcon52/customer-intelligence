import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
export function AccountLinks() {
  return (
    <>
      <Link className="login-link" to="/login">
        Log in
      </Link>
      <Link className="button button-dark button-small" to="/signup">
        Get started <ArrowUpRight size={15} />
      </Link>
    </>
  );
}
