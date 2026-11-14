import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import LiquidNavbar, { LiquidNavItem } from '../ui/liquid-glass-navbar';
import { useResolvedTheme } from '../common/ThemeToggle';

export interface AppNavItem {
  label: string;
  icon: LucideIcon;
}

function useMinWidth(px: number): boolean {
  const query = `(min-width: ${px}px)`;
  const [match, setMatch] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [query]);
  return match;
}

/**
 * The liquid-glass navbar fitted to this app: text labels where there is room, lucide icons (with the
 * label kept as the accessible name) where there is not, water tone following the site theme. Sizing and
 * colours are overridden in globals.css under `.nimbus-nav.app-liquid`.
 */
export const AppLiquidNav: React.FC<{
  items: AppNavItem[];
  active: number;
  onSelect: (index: number) => void;
  /** viewport width from which text labels are shown; below it the bar shows icons only */
  labelsFrom: number;
  className?: string;
}> = ({ items, active, onSelect, labelsFrom, className }) => {
  const tone = useResolvedTheme();
  const wide = useMinWidth(labelsFrom);
  const navItems: LiquidNavItem[] = useMemo(
    () =>
      items.map((it) => ({
        label: it.label,
        icon: wide ? undefined : <it.icon size={18} strokeWidth={1.8} aria-hidden="true" />,
        fx: wide ? 'none' : 'pop',
      })),
    [items, wide],
  );
  // Icon-only buttons already carry the label as aria-label; add it as a tooltip for pointer users too.
  const wrap = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    wrap.current?.querySelectorAll<HTMLElement>('.nimbus-item').forEach((el, i) => {
      if (wide) el.removeAttribute('title');
      else el.title = items[i]?.label ?? '';
    });
  }, [wide, items]);
  return (
    <span ref={wrap} className="contents">
      <LiquidNavbar
        className={['app-liquid', className].filter(Boolean).join(' ')}
        items={navItems}
        active={Math.max(0, active)}
        onChange={(i) => onSelect(i)}
        tone={tone}
        compact={!wide}
      />
    </span>
  );
};
