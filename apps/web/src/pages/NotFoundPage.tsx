import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Grommet, TAG_SHAPE } from '../components/site/Tag';
import { TAG_BUTTON } from '../components/SiteLayout';
import { cn } from '../workspace/style';

export function NotFoundPage() {
  return (
    <section className="grid min-h-[86vh] place-items-center bg-field-800 px-5 pt-28 pb-20">
      <div
        className="relative w-full max-w-md rotate-[-3deg] bg-stock px-8 pt-16 pb-10 text-tag-ink shadow-tag-lift"
        style={{ clipPath: TAG_SHAPE }}
      >
        <Grommet className="absolute top-5 left-1/2 size-5 -translate-x-1/2" />
        <p className="-mx-8 flex items-center justify-between bg-tag-slate px-8 py-2 text-stock">
          <span
            className="text-[13px] font-[780] uppercase"
            style={{ fontStretch: '74%' }}
          >
            Not found
          </span>
          <span className="font-stamp text-[12px] font-semibold">#404</span>
        </p>
        <h1
          className="mt-3 text-[44px] leading-[0.92] font-[840]"
          style={{ fontStretch: '66%' }}
        >
          This tag isn’t on the board.
        </h1>
        <p className="mt-4 text-[16px] text-[#3b4441]">
          The link may be old or mistyped.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-5">
          <Link
            to="/"
            className={cn(
              TAG_BUTTON,
              'bg-tag-ink text-stock hover:bg-field-800',
            )}
          >
            <ArrowLeft className="size-4" /> Back home
          </Link>
          <Link
            to="/app"
            className="text-[15px] font-[640] underline decoration-tag-red decoration-2 underline-offset-4"
          >
            Open workspace
          </Link>
        </div>
      </div>
    </section>
  );
}
