import { Injectable, signal } from '@angular/core';

export type Mode = 'auto' | 'light' | 'dark';
export interface Theme { id: string; name: string; swatch: [string, string] }

// Colour families; each has a light and a dark version (styles.css, "Themes")
export const THEMES: Theme[] = [
  { id: 'ocean', name: 'Ocean (white & blue)', swatch: ['#2563eb', '#0ea5e9'] },
  { id: 'indigo', name: 'Indigo', swatch: ['#6366f1', '#06b6d4'] },
  { id: 'emerald', name: 'Emerald', swatch: ['#059669', '#14b8a6'] },
  { id: 'violet', name: 'Violet', swatch: ['#7c3aed', '#ec4899'] },
  { id: 'sunset', name: 'Sunset', swatch: ['#ea580c', '#f59e0b'] },
  { id: 'graphite', name: 'Graphite', swatch: ['#475569', '#0ea5e9'] },
];
const KEY = 'idp-appearance';

// Theme and light/dark choice, kept on this device. "auto" follows the device's light/dark setting,
// live. index.html applies the saved choice before the app loads, so pages never flash the wrong colours.
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly mode = signal<Mode>('auto');
  readonly theme = signal('indigo');
  private readonly media = window.matchMedia('(prefers-color-scheme: dark)');

  constructor() {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
      if (['auto', 'light', 'dark'].includes(saved.mode)) this.mode.set(saved.mode);
      if (THEMES.some((t) => t.id === saved.theme)) this.theme.set(saved.theme);
    } catch {
      /* storage unavailable: defaults */
    }
    this.media.addEventListener('change', () => this.apply());
    this.apply();
  }

  setMode(mode: Mode) {
    this.mode.set(mode);
    this.save();
  }

  setTheme(id: string) {
    this.theme.set(id);
    this.save();
  }

  private save() {
    try {
      localStorage.setItem(KEY, JSON.stringify({ mode: this.mode(), theme: this.theme() }));
    } catch {
      /* private window: applies for this visit only */
    }
    this.apply();
  }

  private apply() {
    const root = document.documentElement;
    const mode = this.mode() === 'auto' ? (this.media.matches ? 'dark' : 'light') : this.mode();
    root.dataset['theme'] = this.theme();
    root.dataset['mode'] = mode;
    // Browser / installed-app title bar follows the page
    const bar = getComputedStyle(root).getPropertyValue('--bg-sidebar').trim();
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', bar || '#0c101c');
  }
}
