import {
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
  type ChartType,
  type Plugin,
  type TooltipItem,
} from 'chart.js';

import { chartTokens, chf, shortLabel } from '../../core/chart-theme';
import { Theme } from '../../core/theme';
import type { KnownPayment, SeriesPoint } from '../../core/forecast';

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip);

const BAND_LABELS = ['Optimistisch', 'Pessimistisch'];
const MAX_MARKERS = 12;

interface GuideOptions {
  tightIndex: number | null;
  buffer: number;
  bufferColor: string;
  tightColor: string;
}

declare module 'chart.js' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface PluginOptionsByType<TType extends ChartType> {
    guides: GuideOptions;
  }
}

/**
 * Draws the two reference lines Chart.js has no scale concept for: the
 * buffer line the forecast measures against, and the vertical marker on
 * the day the pessimistic band crosses it.
 */
const guides: Plugin<'line'> = {
  id: 'guides',
  afterDatasetsDraw(chart, _args, options: GuideOptions) {
    const { ctx, chartArea, scales } = chart;
    ctx.save();

    const y = scales['y'].getPixelForValue(options.buffer);
    ctx.strokeStyle = options.bufferColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(chartArea.left, y);
    ctx.lineTo(chartArea.right, y);
    ctx.stroke();

    if (options.tightIndex !== null) {
      const x = scales['x'].getPixelForValue(options.tightIndex);
      ctx.strokeStyle = options.tightColor;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
    }
    ctx.restore();
  },
};

@Component({
  selector: 'app-forecast-chart',
  template: `<div class="h-72 sm:h-80"><canvas #canvas></canvas></div>`,
})
export class ForecastChart {
  readonly series = input.required<SeriesPoint[]>();
  /** The unchanged curve, drawn as a dashed ghost while a scenario runs. */
  readonly baseline = input<SeriesPoint[] | null>(null);
  readonly payments = input<KnownPayment[]>([]);
  readonly tightDate = input<string | null>(null);
  readonly buffer = input(0);

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private readonly tokens = chartTokens();
  private readonly theme = inject(Theme);
  private chart?: Chart<'line'>;

  constructor() {
    afterRenderEffect({
      write: () => {
        const config = this.config();
        if (!this.chart) {
          this.chart = new Chart(this.canvas().nativeElement, config);
          return;
        }
        // Update in place rather than recreate: that is what animates the
        // baseline curve into the scenario curve instead of redrawing it.
        this.chart.data = config.data;
        this.chart.options = config.options!;
        this.chart.update();
      },
    });
    inject(DestroyRef).onDestroy(() => this.chart?.destroy());
  }

  /**
   * The series is daily except at 365d, where it is weekly - so a date
   * rarely matches a point exactly. Returns the index of the point that
   * carries that day.
   */
  private indexOf(series: SeriesPoint[], date: string): number {
    const after = series.findIndex((point) => point.date > date);
    return after === -1 ? series.length - 1 : Math.max(after - 1, 0);
  }

  private markers(series: SeriesPoint[]): Map<number, KnownPayment[]> {
    // Only the biggest bookings get a marker. A year holds around a
    // hundred of them against ~52 weekly points, which would turn the
    // curve into a dotted line - and the ones worth pointing at (13th
    // salary, tax instalments, quarterly bills) are the large ones.
    const largest = [...this.payments()]
      .sort((a, b) => b.amount_chf - a.amount_chf)
      .slice(0, MAX_MARKERS);
    const byIndex = new Map<number, KnownPayment[]>();
    for (const payment of largest) {
      const index = this.indexOf(series, payment.date);
      byIndex.set(index, [...(byIndex.get(index) ?? []), payment]);
    }
    return byIndex;
  }

  private config(): ChartConfiguration<'line'> {
    this.theme.isDark(); // re-read the palette when the theme flips
    const { line, muted, grid, accent, danger } = this.tokens();
    const series = this.series();
    const markers = this.markers(series);

    const base = { tension: 0.3, pointRadius: 0, borderWidth: 2 };
    const datasets: ChartDataset<'line'>[] = [
      {
        ...base,
        label: 'Optimistisch',
        data: series.map((point) => point.upper_chf),
        borderWidth: 0,
        fill: '+1',
        backgroundColor: `color-mix(in srgb, ${line} 12%, transparent)`,
      },
      { ...base, label: 'Pessimistisch', data: series.map((point) => point.lower_chf), borderWidth: 0, fill: false },
      {
        ...base,
        label: 'Erwartet',
        data: series.map((point) => point.expected_chf),
        borderColor: line,
        // Everything below the buffer line is shaded red - the curve is
        // not clipped at zero, a negative scenario has to look negative.
        fill: { target: { value: this.buffer() }, above: 'transparent', below: `color-mix(in srgb, ${danger} 22%, transparent)` },
      },
    ];

    const baseline = this.baseline();
    if (baseline) {
      datasets.push({
        ...base,
        label: 'Ohne Änderung',
        data: baseline.map((point) => point.expected_chf),
        borderColor: muted,
        borderDash: [5, 4],
        fill: false,
      });
    }

    if (markers.size) {
      datasets.push({
        ...base,
        label: 'Fixkosten',
        data: series.map((point, index) => (markers.has(index) ? point.expected_chf : null)),
        borderWidth: 0,
        showLine: false,
        pointRadius: 4,
        pointHoverRadius: 7,
        pointBackgroundColor: accent,
        fill: false,
      });
    }

    const tight = this.tightDate();

    return {
      type: 'line',
      data: { labels: series.map((point) => shortLabel(point.date)), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600, easing: 'easeInOutCubic' },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: (item: TooltipItem<'line'>) =>
              !BAND_LABELS.includes(item.dataset.label ?? '') && item.parsed.y !== null,
            callbacks: {
              label: (item: TooltipItem<'line'>) =>
                item.dataset.label === 'Fixkosten'
                  ? (markers.get(item.dataIndex) ?? []).map((p) => `${p.label}: ${chf(p.amount_chf)}`)
                  : `${item.dataset.label}: ${chf(item.parsed.y ?? 0)}`,
            },
          },
          guides: {
            tightIndex: tight ? this.indexOf(series, tight) : null,
            buffer: this.buffer(),
            bufferColor: muted,
            tightColor: danger,
          } satisfies GuideOptions,
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: grid },
            ticks: { color: muted, maxTicksLimit: 7, font: { size: 11 }, maxRotation: 0 },
          },
          y: {
            grid: { color: grid },
            border: { display: false },
            ticks: { color: muted, maxTicksLimit: 5, font: { size: 11 }, callback: (v) => chf(Number(v)) },
          },
        },
      },
      plugins: [guides],
    };
  }
}
