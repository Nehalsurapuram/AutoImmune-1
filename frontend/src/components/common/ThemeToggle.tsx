import React, { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

type Theme = 'light' | 'dark';
const STORAGE_KEY = 'theme';

function readStored(): Theme | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function currentTheme(): Theme {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

/** The theme currently applied to <html>, kept in sync with the toggle (for components that need it in JS). */
export function useResolvedTheme(): Theme {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  useEffect(() => {
    const mo = new MutationObserver(() => setTheme(currentTheme()));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  }, []);
  return theme;
}

/**
 * Light/dark switch. index.html sets data-theme before first paint; this keeps
 * it in sync, saves an explicit choice, and follows the OS setting until the
 * viewer picks one.
 */
export const ThemeToggle: React.FC = () => {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Keep every toggle on the page (and other tabs) in step, and follow the OS
  // setting while the viewer has not chosen a theme explicitly.
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    const onSystem = () => {
      if (!readStored()) setTheme(systemTheme());
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setTheme(readStored() ?? systemTheme());
    };
    const onLocal = () => setTheme(currentTheme());
    mq?.addEventListener('change', onSystem);
    window.addEventListener('storage', onStorage);
    window.addEventListener('themechange', onLocal);
    return () => {
      mq?.removeEventListener('change', onSystem);
      window.removeEventListener('storage', onStorage);
      window.removeEventListener('themechange', onLocal);
    };
  }, []);

  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable: the choice lasts for this page view only */
    }
    document.documentElement.setAttribute('data-theme', next);
    setTheme(next);
    window.dispatchEvent(new Event('themechange'));
  };

  const isDark = theme === 'dark';
  const label = isDark ? 'Switch to light theme' : 'Switch to dark theme';

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className="h-8 w-8 rounded flex items-center justify-center text-text-2 hover:text-text hover:bg-surface-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
    >
      {isDark ? <Sun size={16} strokeWidth={1.75} aria-hidden="true" /> : <Moon size={16} strokeWidth={1.75} aria-hidden="true" />}
    </button>
  );
};
