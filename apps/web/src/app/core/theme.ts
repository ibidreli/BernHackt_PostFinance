import { DOCUMENT, Service, computed, effect, inject, signal } from '@angular/core';

export type ColorScheme = 'light' | 'dark';

const STORAGE_KEY = 'theme';

/** Owns the app-wide colour scheme and keeps it in sync with the DOM and storage. */
@Service()
export class Theme {
  private readonly document = inject(DOCUMENT);
  private readonly scheme = signal<ColorScheme>(this.readStoredScheme());

  readonly isDark = computed(() => this.scheme() === 'dark');

  constructor() {
    effect(() => {
      const scheme = this.scheme();
      this.document.documentElement.classList.toggle('dark', scheme === 'dark');
      this.document.defaultView?.localStorage.setItem(STORAGE_KEY, scheme);
    });
  }

  toggle(): void {
    this.scheme.update((scheme) => (scheme === 'dark' ? 'light' : 'dark'));
  }

  set(scheme: ColorScheme): void {
    this.scheme.set(scheme);
  }

  private readStoredScheme(): ColorScheme {
    const view = this.document.defaultView;
    const stored = view?.localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') {
      return stored;
    }
    return view?.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
}
