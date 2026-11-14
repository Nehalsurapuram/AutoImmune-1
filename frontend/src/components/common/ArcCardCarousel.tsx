import * as React from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

/**
 * Arc Card Carousel: cards hung on the rim of a wheel whose hub sits off the
 * left edge, so only a gentle arc of them shows. The card on the wheel's
 * equator lies flat; cards above tip back, cards below tip forward.
 *
 * The page scroll drives it. The stage pins (CSS sticky) while you scroll
 * through the section, the wheel rolls one card per stretch of scroll, and
 * when you stop it settles on the nearest card. Beside the flat card, its
 * number, title and meta swap in.
 *
 * Sticky pinning needs every ancestor to be free of overflow hidden/auto
 * (overflow: clip is fine).
 */

gsap.registerPlugin(ScrollTrigger);

export type ArcCardItem = {
  /** Card face. Either an image... */
  src?: string;
  alt?: string;
  /** ...or any rendered content. */
  face?: React.ReactNode;
  /** Shown beside the flat card. Without any titles the caption is left out. */
  title?: string;
  /** A small line under the title. */
  meta?: string;
};

export type ArcCardCarouselProps = {
  items: ArcCardItem[];
  /** Height of the pinned stage. Must be a definite length. */
  height?: string;
  /** Distance from the viewport top where the stage pins (e.g. a sticky header). */
  topOffset?: number;
  /** Scroll per card, as a fraction of the stage height. */
  scrollPerCard?: number;
  /** Degrees of the wheel between neighbouring cards. */
  step?: number;
  /** Card corner radius in px. */
  radius?: number;
  /** Show the number, title and meta beside the flat card. */
  caption?: boolean;
  /**
   * Scroll on forever. The page cannot scroll beyond the section, so only use
   * it when the carousel is the whole page.
   */
  loop?: boolean;
  onIndexChange?: (index: number) => void;
  ariaLabel?: string;
  className?: string;
};

// #region wheel
/** Where item `i` sits relative to the position, wrapped to [-n/2, n/2). */
export function offsetOf(i: number, pos: number, n: number): number {
  if (n <= 0) return 0;
  const d = (((i - pos) % n) + n) % n;
  return d >= n / 2 ? d - n : d;
}

/** Cards on the rim: the list repeated to at least ten, so the wrap happens off screen. */
export function ringSize(len: number): number {
  return len > 0 ? Math.ceil(10 / len) * len : 0;
}

export function wrapIndex(i: number, n: number): number {
  if (n <= 0) return 0;
  return ((Math.round(i) % n) + n) % n;
}

/** Every length is a fraction of the stage height `u` (shrunk on narrow stages). */
export function geometry(w: number, h: number) {
  const u = Math.min(h, w / 0.47);
  const cardW = 0.3 * u;
  return { cardW, cardH: cardW / 1.65, radius: 0.71 * u, hubX: 0.284 * u - 0.71 * u, hubY: 0.475 * h };
}

/** Centre and turn (degrees) of a card `d` steps after the flat one. */
export function place(d: number, stepDeg: number, g: { radius: number; hubX: number; hubY: number }) {
  const deg = -d * stepDeg;
  const a = (deg * Math.PI) / 180;
  return { x: g.hubX + g.radius * Math.cos(a), y: g.hubY + g.radius * Math.sin(a), rot: deg };
}

/** Card steps along the section. */
export function spans(count: number, loop: boolean): number {
  return Math.max(0, loop ? count : count - 1);
}

/** The wheel's position for a scroll progress (0-1) after `laps` trips through the section. */
export function positionAt(progress: number, laps: number, steps: number): number {
  return (progress + laps) * steps;
}

/** Scroll offset inside the section that brings card `i` flat. */
export function scrollFor(i: number, steps: number, start: number, end: number): number {
  return steps > 0 ? start + (i / steps) * (end - start) : start;
}
// #endregion

// Colours come from the app's theme tokens (src/styles/globals.css), so the
// carousel follows light and dark mode.
const CSS =
  '.acc-track{position:relative;background:var(--page)}' +
  '.acc-stage{position:sticky;overflow:hidden}' +
  '.acc-card{position:absolute;left:0;top:0;overflow:hidden;will-change:transform;cursor:pointer;' +
  'box-shadow:var(--shadow-2);background:var(--surface);border:1px solid var(--line-strong)}' +
  '.acc-card>img{display:block;width:100%;height:100%;max-width:none;object-fit:cover;pointer-events:none}' +
  '.acc-card:focus-visible{outline:2px solid var(--focus);outline-offset:3px}' +
  '.acc-cap{position:absolute;right:6vw;transform:translateY(-50%);color:var(--text);pointer-events:none}' +
  '.acc-num{font-size:13px;letter-spacing:.08em;font-variant-numeric:tabular-nums;color:var(--text-3);margin:0 0 18px}' +
  '.acc-title{margin:0;font-size:clamp(28px,3.6vw,56px);line-height:1.02;letter-spacing:-.03em;font-weight:600}' +
  '.acc-meta{margin:18px 0 0;font-size:15px;line-height:1.5;color:var(--text-2);max-width:52ch}' +
  '.acc-cap[data-narrow]{left:0 !important;right:0;top:auto !important;bottom:0;transform:none;padding:56px 20px 20px;' +
  'background:linear-gradient(to top,var(--page) calc(100% - 56px),transparent)}' +
  '.acc-cap[data-narrow] .acc-num{margin-bottom:8px}' +
  '.acc-cap[data-narrow] .acc-title{font-size:24px}' +
  '.acc-cap[data-narrow] .acc-meta{margin-top:8px;font-size:13px}' +
  '.acc-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}';

export default function ArcCardCarousel({
  items,
  height = '100svh',
  topOffset = 0,
  scrollPerCard = 0.6,
  step = 14,
  radius = 10,
  caption = true,
  loop = false,
  onIndexChange,
  ariaLabel = 'Card carousel',
  className = '',
}: ArcCardCarouselProps) {
  const count = items.length;
  const n = ringSize(count);
  const cards = React.useMemo(() => Array.from({ length: n }, (_, i) => items[i % count]), [items, n, count]);
  const trackRef = React.useRef<HTMLDivElement | null>(null);
  const stageRef = React.useRef<HTMLDivElement | null>(null);
  const capRef = React.useRef<HTMLDivElement | null>(null);
  const cardRefs = React.useRef<(HTMLDivElement | null)[]>([]);
  const pos = React.useRef({ v: 0 });
  const st = React.useRef<ScrollTrigger | null>(null);
  const geo = React.useRef(geometry(1, 1));
  const [index, setIndex] = React.useState(0);
  const [narrow, setNarrow] = React.useState(false);
  const [reduced, setReduced] = React.useState(false);
  const onIndexRef = React.useRef(onIndexChange);
  onIndexRef.current = onIndexChange;
  const showCaption = caption && items.some((it) => it.title);

  const placeCaption = React.useCallback(() => {
    const cap = capRef.current;
    const el = stageRef.current;
    if (!cap || !el) return;
    const g = geo.current;
    cap.style.top = g.hubY + 'px';
    cap.style.left = g.hubX + g.radius + g.cardW / 2 + Math.max(24, 0.06 * el.clientHeight) + 'px';
  }, []);

  const render = React.useCallback(() => {
    const g = geo.current;
    const p = pos.current.v;
    for (let i = 0; i < n; i++) {
      const el = cardRefs.current[i];
      if (!el) continue;
      const d = offsetOf(i, p, n);
      const c = place(d, step, g);
      el.style.transform =
        'translate3d(' +
        (c.x - g.cardW / 2).toFixed(2) +
        'px,' +
        (c.y - g.cardH / 2).toFixed(2) +
        'px,0) rotate(' +
        c.rot.toFixed(3) +
        'deg)';
      // Earlier cards (below) overlap later ones.
      el.style.zIndex = String(Math.round((n - d) * 10));
    }
    const now = wrapIndex(p, count);
    setIndex((prev) => (prev === now ? prev : now));
  }, [n, count, step]);

  React.useEffect(() => {
    onIndexRef.current?.(index);
  }, [index]);

  React.useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setReduced(mq.matches);
    on();
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);

  // Size: every length is a fraction of the stage height.
  React.useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const g = geometry(el.clientWidth, el.clientHeight);
      geo.current = g;
      for (const c of cardRefs.current) {
        if (!c) continue;
        c.style.width = g.cardW + 'px';
        c.style.height = g.cardH + 'px';
      }
      placeCaption();
      setNarrow(el.clientWidth < 0.9 * el.clientHeight || el.clientWidth < 640);
      render();
      ScrollTrigger.refresh();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [render, placeCaption]);

  React.useLayoutEffect(placeCaption, [showCaption, placeCaption]);

  // The page scroll rolls the wheel; letting go settles on the nearest card.
  const steps = spans(count, loop);
  React.useEffect(() => {
    const track = trackRef.current;
    if (!track || count < 2) return;
    let laps = 0;
    let target = 0;
    const trigger = ScrollTrigger.create({
      trigger: track,
      start: `top ${topOffset}px`,
      end: 'bottom bottom',
      snap: reduced
        ? undefined
        : { snapTo: 1 / steps, duration: { min: 0.5, max: 1.4 }, delay: 0.12, ease: 'power2.inOut' },
      onUpdate: (self) => {
        // Looping: the bottom of the section looks like its top, so jump there unseen.
        if (loop && self.progress >= 1 && self.direction > 0) {
          laps += 1;
          self.scroll(self.start + 1);
          return;
        }
        target = positionAt(self.progress, laps, steps);
      },
    });
    // At the very top there is no scroll left to fire onUpdate, so a wheel up wraps.
    const onWheel = (e: WheelEvent) => {
      if (!loop || e.deltaY >= 0 || trigger.scroll() > trigger.start + 1) return;
      const r = track.getBoundingClientRect();
      if (r.top > topOffset + 1 || r.bottom < window.innerHeight - 1) return;
      laps -= 1;
      trigger.scroll(trigger.end - 1);
    };
    window.addEventListener('wheel', onWheel, { passive: true });
    target = positionAt(trigger.progress, 0, steps);
    pos.current.v = target;
    const tick = (_t: number, dt: number) => {
      const p = pos.current.v;
      const next = reduced ? target : p + (target - p) * (1 - Math.exp(-dt / 110));
      if (Math.abs(next - p) < 1e-4 && next === target) return;
      pos.current.v = Math.abs(target - next) < 1e-4 ? target : next;
      render();
    };
    gsap.ticker.add(tick);
    st.current = trigger;
    render();
    return () => {
      gsap.ticker.remove(tick);
      window.removeEventListener('wheel', onWheel);
      trigger.kill();
      st.current = null;
    };
  }, [count, steps, loop, reduced, render, topOffset]);

  // The caption swaps in with the flat card.
  React.useEffect(() => {
    const cap = capRef.current;
    if (!cap || reduced) return;
    const tw = gsap.fromTo(
      cap.querySelectorAll('.acc-num,.acc-title,.acc-meta'),
      { y: 14, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.6, ease: 'power2.out', stagger: 0.05 },
    );
    return () => void tw.kill();
  }, [index, reduced]);

  const bringFlat = (i: number) => {
    const s = st.current;
    if (!s) return;
    window.scrollTo({ top: scrollFor(i % count, steps, s.start, s.end), behavior: reduced ? 'auto' : 'smooth' });
  };

  const current = items[index];
  return (
    <div
      ref={trackRef}
      className={'acc-track ' + className}
      style={{ height: 'calc(' + height + ' * ' + (1 + steps * scrollPerCard) + ')' }}
      role="region"
      aria-roledescription="carousel"
      aria-label={ariaLabel}
    >
      <style>{CSS}</style>
      <div ref={stageRef} className="acc-stage" style={{ height, top: topOffset }}>
        {cards.map((it, i) => (
          <div
            key={i}
            ref={(el) => {
              cardRefs.current[i] = el;
            }}
            className="acc-card"
            style={{ borderRadius: radius }}
            role="button"
            tabIndex={i < count ? 0 : -1}
            aria-hidden={i < count ? undefined : true}
            aria-roledescription="slide"
            aria-label={(it.title ?? it.alt ?? 'Card') + ', ' + ((i % count) + 1) + ' of ' + count}
            onClick={() => bringFlat(i)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                bringFlat(i);
              }
            }}
          >
            {it.face ?? (it.src ? <img src={it.src} alt={it.alt ?? ''} draggable={false} decoding="async" /> : null)}
          </div>
        ))}
        {showCaption && current && (
          <div ref={capRef} className="acc-cap" data-narrow={narrow ? '' : undefined} style={{ zIndex: n * 20 }}>
            <p className="acc-num">
              {String(index + 1).padStart(2, '0')} / {String(count).padStart(2, '0')}
            </p>
            {current.title && <h3 className="acc-title">{current.title}</h3>}
            {current.meta && <p className="acc-meta">{current.meta}</p>}
          </div>
        )}
        <p className="acc-sr" aria-live="polite">
          {count ? 'Card ' + (index + 1) + ' of ' + count + (current?.title ? ': ' + current.title : '') : ''}
        </p>
      </div>
    </div>
  );
}
