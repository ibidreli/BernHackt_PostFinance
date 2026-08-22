import {
  DOCUMENT,
  Component,
  DestroyRef,
  ElementRef,
  afterRenderEffect,
  inject,
  input,
  viewChild,
} from '@angular/core';
import {
  CategoryScale,
  Chart,
  Filler,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
  type ChartConfiguration,
  type ChartDataset,
  type TooltipItem,
} from 'chart.js';

import { Theme } from '../../core/theme';
import type { ChartSpec } from '../../core/assistant';

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip);

const BAND_LABELS = ['Optimistisch', 'Pessimistisch'];

const MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

/** "2026-09" -> "Sep 26", "2026-08-22" -> "22.08." */
function shortLabel(date: string): string {
  const [year, month, day] = date.split('-');
  return day ? `${day}.${month}.` : `${MONTHS[Number(month) - 1]} ${year.slice(2)}`;
}

/**
 * Renders one of the three fixed chart types. The backend picks the type
 * and supplies the numbers; this component only decides how they look,
 * so a new answer can never arrive with a chart definition of its own.
 */
@Component({
  selector: 'app-assistant-chart',
  template: `<div class="h-56 sm:h-64"><canvas #canvas></canvas></div>`,
})
export class AssistantChart {
  readonly spec = input.required<ChartSpec>();

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private readonly document = inject(DOCUMENT);
  private readonly theme = inject(Theme);
  private chart?: Chart;

  constructor() {
    afterRenderEffect({
      write: () => {
        this.theme.isDark(); // re-render on theme change: the palette below is read from CSS
        this.chart?.destroy();
        this.chart = new Chart(this.canvas().nativeElement, this.config(this.spec()));
      },
    });
    inject(DestroyRef).onDestroy(() => this.chart?.destroy());
  }

  private token(name: string): string {
    return getComputedStyle(this.document.documentElement).getPropertyValue(name).trim();
  }

  private config(spec: ChartSpec): ChartConfiguration<'line'> {
    const line = this.token('--color-ring');
    const muted = this.token('--color-muted-foreground');
    const grid = this.token('--color-border');
    const accent = this.token('--color-secondary');

    // The main curve: `before_after` splits into two series, the other
    // two types carry a single banded series.
    const series = spec.type === 'before_after' ? spec.scenario_series : spec.series;
    const targetValue =
      spec.type === 'wealth_over_time' ? spec.target_line_chf : spec.type === 'goal_progress' ? spec.target_chf : null;

    // Thousands only help once the numbers are big enough - a
    // next-salary-period chart lives in the hundreds.
    const large = Math.max(...series.map((p) => Math.abs(p.expected_chf))) >= 5000;
    const format = (value: number) =>
      large ? `${Math.round(value / 1000)}k` : Math.round(value).toLocaleString('de-CH');

    const base = { tension: 0.35, pointRadius: 0, borderWidth: 2 };
    const expected: ChartDataset<'line'> = {
      ...base,
      label: spec.type === 'before_after' ? 'Mit Änderung' : 'Erwartet',
      data: series.map((p) => p.expected_chf),
      borderColor: line,
      backgroundColor: `color-mix(in srgb, ${line} 14%, transparent)`,
      fill: spec.type === 'goal_progress' ? 'origin' : false,
    };
    const band: ChartDataset<'line'>[] = [
      { ...base, label: 'Optimistisch', data: series.map((p) => p.upper_chf), borderWidth: 0, fill: '+1', backgroundColor: `color-mix(in srgb, ${line} 10%, transparent)` },
      { ...base, label: 'Pessimistisch', data: series.map((p) => p.lower_chf), borderWidth: 0, fill: false },
    ];
    const target: ChartDataset<'line'>[] =
      targetValue === null
        ? []
        : [{ ...base, label: 'Ziel', data: series.map(() => targetValue), borderColor: accent, borderDash: [6, 5], borderWidth: 1.5, fill: false }];
    const baseline: ChartDataset<'line'>[] =
      spec.type !== 'before_after'
        ? []
        : [{ ...base, label: 'Ohne Änderung', data: spec.baseline_series.map((p) => p.expected_chf), borderColor: muted, borderDash: [5, 4], fill: false }];

    const datasets: Record<ChartSpec['type'], ChartDataset<'line'>[]> = {
      wealth_over_time: [...band, expected, ...target],
      goal_progress: [expected, ...target],
      before_after: [...baseline, expected],
    };

    return {
      type: 'line' as const,
      data: { labels: series.map((p) => shortLabel(p.date)), datasets: datasets[spec.type] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700, easing: 'easeOutQuart' as const },
        interaction: { mode: 'index' as const, intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            // The band's two edge datasets carry no line of their own -
            // showing them would triple the tooltip for one curve.
            filter: (item: TooltipItem<'line'>) => !BAND_LABELS.includes(item.dataset.label ?? ''),
            callbacks: {
              label: (item: TooltipItem<'line'>) =>
                `${item.dataset.label}: CHF ${Math.round(item.parsed.y ?? 0).toLocaleString('de-CH')}`,
            },
          },
        },
        scales: {
          x: { grid: { display: false }, border: { color: grid }, ticks: { color: muted, maxTicksLimit: 6, font: { size: 11 } } },
          y: {
            grid: { color: grid },
            border: { display: false },
            ticks: {
              color: muted,
              maxTicksLimit: 5,
              font: { size: 11 },
              callback: (value: string | number) => format(Number(value)),
            },
          },
        },
      },
    };
  }
}
