import { DOCUMENT, inject } from '@angular/core';

/**
 * Reads the app's colour tokens off the document so charts follow the
 * theme toggle without a second palette definition in TypeScript.
 * Call it inside a render effect that also reads `Theme.isDark()`.
 */
export function chartTokens() {
  const root = inject(DOCUMENT).documentElement;
  const token = (name: string) => getComputedStyle(root).getPropertyValue(name).trim();
  return () => ({
    line: token('--color-ring'),
    muted: token('--color-muted-foreground'),
    grid: token('--color-border'),
    accent: token('--color-secondary'),
    danger: token('--color-danger'),
  });
}

const MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

/** "2026-09" -> "Sep 26", "2026-08-22" -> "22.08." */
export function shortLabel(date: string): string {
  const [year, month, day] = date.split('-');
  return day ? `${day}.${month}.` : `${MONTHS[Number(month) - 1]} ${year.slice(2)}`;
}

export function chf(value: number): string {
  const digits = Math.abs(Math.round(value)).toLocaleString('de-CH').replace(/[^\d]/g, "'");
  return `${value < 0 ? '-' : ''}CHF ${digits}`;
}

/** Two decimals - for a single booking, the centimes are the point. */
export function chfExact(value: number): string {
  const digits = Math.abs(value)
    .toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    .replace(/[^\d.,]/g, "'");
  return `${value < 0 ? '-' : ''}CHF ${digits}`;
}
