import { useEffect, useRef } from 'react';
import { ArrowUpRight, Check, MousePointer2 } from 'lucide-react';

/** Native SVG + transform-only CSS. Pointer work is capped to one animation frame. */
export function OrbitArt({ compact = false }: { compact?: boolean }) {
  const scene = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = scene.current;
    if (
      !node ||
      compact ||
      !window.matchMedia(
        '(hover: hover) and (prefers-reduced-motion: no-preference)',
      ).matches
    )
      return;
    let frame = 0;
    const move = (event: PointerEvent) => {
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const box = node.getBoundingClientRect();
        node.style.setProperty(
          '--pointer-x',
          `${(event.clientX - box.left - box.width / 2) / 35}px`,
        );
        node.style.setProperty(
          '--pointer-y',
          `${(event.clientY - box.top - box.height / 2) / 35}px`,
        );
      });
    };
    const reset = () => {
      cancelAnimationFrame(frame);
      node.style.setProperty('--pointer-x', '0px');
      node.style.setProperty('--pointer-y', '0px');
    };
    const visibility = new IntersectionObserver(([entry]) => {
      node.classList.toggle('scene-paused', !entry.isIntersecting);
    });
    visibility.observe(node);
    node.addEventListener('pointermove', move);
    node.addEventListener('pointerleave', reset);
    return () => {
      cancelAnimationFrame(frame);
      visibility.disconnect();
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerleave', reset);
    };
  }, [compact]);
  return (
    <div
      className={`orbit-scene ${compact ? 'orbit-compact' : ''}`}
      ref={scene}
      aria-hidden="true"
    >
      <div className="orbit-grid" />
      <div className="orbit-art-layer">
        <svg className="orbit-sculpture" viewBox="0 0 660 660">
          <defs>
            <linearGradient
              id={compact ? 'petal-small' : 'petal-large'}
              x1="0"
              y1="0"
              x2="1"
              y2="1"
            >
              <stop stopColor="#efe2ff" />
              <stop offset=".52" stopColor="#be93e2" />
              <stop offset="1" stopColor="#6b3a93" />
            </linearGradient>
            <radialGradient
              id={compact ? 'core-small' : 'core-large'}
              cx=".3"
              cy=".25"
            >
              <stop stopColor="#e6ffaa" />
              <stop offset=".75" stopColor="#caf777" />
              <stop offset="1" stopColor="#92bd44" />
            </radialGradient>
          </defs>
          <g
            className="orbit-rings"
            fill="none"
            stroke="#c5a0e3"
            strokeOpacity=".35"
          >
            <ellipse
              cx="330"
              cy="330"
              rx="308"
              ry="138"
              transform="rotate(-32 330 330)"
            />
            <ellipse
              cx="330"
              cy="330"
              rx="308"
              ry="138"
              transform="rotate(38 330 330)"
            />
            <circle cx="330" cy="330" r="250" strokeDasharray="2 13" />
          </g>
          <g className="sculpture-flower">
            {Array.from({ length: 10 }, (_, i) => (
              <path
                key={i}
                d="M323 311 C271 234 261 145 305 111 C346 77 395 120 393 179 C390 234 359 287 337 321Z"
                fill={`url(#${compact ? 'petal-small' : 'petal-large'})`}
                stroke="#d5b1ed"
                strokeWidth="1.5"
                transform={`rotate(${i * 36} 330 330)`}
              />
            ))}
            <circle
              cx="330"
              cy="330"
              r="92"
              fill={`url(#${compact ? 'core-small' : 'core-large'})`}
              stroke="#e2ffa8"
              strokeWidth="2"
            />
            <path
              d="m306 330 17 17 35-37"
              stroke="#3b5027"
              strokeWidth="6"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
          </g>
          <g fill="#d8fc98">
            <path d="m540 115 22-18 22 18-22 26Z" />
            <path
              d="m562 97 0 44M540 115h44"
              stroke="#759b46"
              strokeWidth="1.5"
            />
            <circle cx="105" cy="411" r="8" />
            <path d="m156 100 5 12 12 5-12 5-5 12-5-12-12-5 12-5Z" />
          </g>
          <g fill="#c4ece9" stroke="#6d9f9d">
            <path d="m477 545 34-13 23 22-35 15Z" />
            <path d="m477 545 0 17 22 22v-15m0 15 35-14v-16" />
          </g>
        </svg>
        {!compact && (
          <>
            <div className="signal-tag signal-tag-one">
              <span className="live-dot" /> A signal worth noticing{' '}
              <ArrowUpRight size={15} />
            </div>
            <div className="floating-account">
              <div className="account-top">
                <span className="account-avatar">N</span>
                <div>
                  <strong>Northstar Studio</strong>
                  <small>Customer story, connected.</small>
                </div>
                <span className="account-star">✳</span>
              </div>
              <div className="account-bars">
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
              <div className="account-bottom">
                <span>Usage changed</span>
                <span className="account-chip">
                  Let’s check in <ArrowUpRight size={12} />
                </span>
              </div>
            </div>
            <div className="signal-tag signal-tag-two">
              <Check size={15} /> Every next move, with context.
            </div>
            <div className="scene-cursor">
              <MousePointer2 size={19} fill="#d8fc98" />
              <span>Your team</span>
            </div>
            <span className="orbit-caption">
              GOOD CONNECTIONS DON’T HAPPEN BY ACCIDENT.
            </span>
          </>
        )}
      </div>
    </div>
  );
}
