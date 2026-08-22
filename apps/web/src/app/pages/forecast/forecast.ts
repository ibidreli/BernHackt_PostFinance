import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { Alerts, alertMonthOf, alertSentence, type AlertDto } from '../../core/alerts';
import { chf } from '../../core/chart-theme';
import {
  Forecast,
  HORIZONS,
  type Adjustment,
  type Horizon,
  type Interval,
  type RecurringPayment,
} from '../../core/forecast';
import { Graph } from '../../core/graph';
import { Handoff } from '../../core/handoff';
import { RailOutlet } from '../../core/rail';
import { ForecastChart } from './forecast-chart';

const DATE = new Intl.DateTimeFormat('de-CH', { day: 'numeric', month: 'long' });

/** YYYY-MM arithmetic for the alert window. */
function monthsBack(month: string, count: number): string {
  const [year, monthNumber] = month.split('-').map(Number);
  const index = year * 12 + (monthNumber - 1) - count;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`;
}

/** One rail chip: a category and its alerts. `severity` is the worst
    one - the source window is already sorted worst-first. */
interface AlertGroup {
  label: string;
  severity: AlertDto['severity'];
  alerts: AlertDto[];
}

@Component({
  imports: [ForecastChart, RailOutlet, RouterLink],
  selector: 'app-forecast',
  templateUrl: './forecast.html',
  // Document-level: the chip that opens the overlay sits in the rail
  // (rendered by the layout), so a local escape handler would never see
  // the key while focus is still out there.
  host: { '(document:keydown.escape)': 'openGroup.set(null)' },
})
export class ForecastPage {
  protected readonly forecast = inject(Forecast);
  protected readonly graph = inject(Graph);
  private readonly alerts = inject(Alerts);
  private readonly handoff = inject(Handoff);
  private readonly router = inject(Router);
  protected readonly horizons = HORIZONS;

  constructor() {
    // Handed over from /kategorien ("In Prognose simulieren") or
    // /future-me ("Als Szenario übernehmen") - consume-once, so a later
    // plain visit starts clean.
    const pending = this.handoff.takeAdjustment();
    if (pending) this.forecast.add(pending);
  }

  /** Active scenario -> a prefilled what-if question on /future-me. */
  protected askFutureMe(): void {
    const labels = this.forecast
      .adjustments()
      .map((adjustment) => adjustment.label)
      .join(' und ');
    if (!labels) return;
    this.handoff.sendQuestion(`Was wäre, wenn ich Folgendes umsetze: ${labels}?`);
    void this.router.navigate(['/future-me']);
  }
  protected readonly chf = chf;
  protected readonly alertSentence = alertSentence;

  /** Alerts of the last three data months - shown where the money story
      is told, each row deep-linking to its bubble on /kategorien. */
  private readonly recentWindow = computed(() => {
    const asOf = this.forecast.baseline()?.as_of;
    return asOf ? this.alerts.recent(monthsBack(asOf.slice(0, 7), 2)) : [];
  });

  /** Alerts grouped per category for the rail chips - the details live
      in the overlay a chip opens. */
  protected readonly alertGroups = computed<AlertGroup[]>(() => {
    const groups = new Map<string, AlertGroup>();
    for (const alert of this.recentWindow()) {
      const label = alert.category_sub ?? alert.category_main ?? alert.merchant ?? 'Sonstiges';
      const group = groups.get(label) ?? { label, severity: alert.severity, alerts: [] };
      group.alerts.push(alert);
      groups.set(label, group);
    }
    return [...groups.values()];
  });

  /** The category group currently shown in the centered overlay. */
  protected readonly openGroup = signal<AlertGroup | null>(null);

  /** A tight date with a concurrent category spike names its driver. */
  protected readonly spikeDriver = computed(() => {
    const asOf = this.forecast.baseline()?.as_of;
    if (!asOf || !this.forecast.current()?.tight_date) return null;
    return (
      this.alerts.forMonth(asOf.slice(0, 7)).find((alert) => alert.type === 'category_spike') ??
      null
    );
  });

  /** Query params for /kategorien: the alert's own bubble. */
  protected alertLink(alert: AlertDto): Record<string, string> {
    const params: Record<string, string> = {};
    const month = alertMonthOf(alert);
    if (month) params['month'] = month;
    if (alert.type === 'category_spike') {
      params['category'] = `${alert.category_main ?? ''}~${alert.category_sub ?? ''}`;
    } else if (alert.transaction_id) {
      params['tx'] = alert.transaction_id;
    }
    return params;
  }

  protected dotClass(severity: AlertDto['severity']): string {
    if (severity === 'danger') return 'bg-danger';
    if (severity === 'warning') return 'bg-warning';
    return 'bg-ring';
  }

  protected readonly newLabel = signal('Fitnessabo');
  protected readonly newAmount = signal(89);
  protected readonly newInterval = signal<Interval>('monthly');
  /** The "+" popover holding the free-form inputs. */
  protected readonly menuOpen = signal(false);

  /** Selected category for the adjust_category form, keyed main//sub. */
  protected readonly catKey = signal('');
  protected readonly catPercent = signal(-50);

  /** Expense categories from the graph cache, largest first. */
  protected readonly categories = computed(() => this.graph.expenseCategories());

  protected categoryKey(category: { main: string; sub: string | null }): string {
    return `${category.main}//${category.sub ?? ''}`;
  }

  protected addCategoryAdjustment(): void {
    const category =
      this.categories().find((c) => this.categoryKey(c) === this.catKey()) ?? this.categories()[0];
    const percent = this.catPercent();
    if (!category || !percent) return;
    this.forecast.add({
      id: `category:${this.categoryKey(category)}`,
      label: `${category.label} ${percent > 0 ? '+' : ''}${percent} %`,
      payload: {
        type: 'adjust_category',
        category_main: category.main,
        category_sub: category.sub,
        percent,
      },
    });
    this.menuOpen.set(false);
  }

  /**
   * Presets built entirely from the actual data, nothing hard-coded:
   * the two largest monthly recurring expenses (raise/cancel), the
   * largest variable category, and - when the alert service found a
   * category spike - that spike's category. Each account gets its own
   * set; an account without a spike simply has one preset fewer.
   */
  private readonly allPresets = computed<Adjustment[]>(() => {
    const [first, second] = this.forecast.topMonthly();
    const presets: Adjustment[] = [];
    const cancellable = second ?? first;
    if (cancellable) {
      presets.push({
        id: `cancel:${cancellable.recurring_id}`,
        label: `${this.name(cancellable)} kündigen`,
        payload: { type: 'cancel_recurring', recurring_id: cancellable.recurring_id },
      });
    }

    const categoryPreset = (
      main: string,
      sub: string | null,
      label: string,
    ): Adjustment => ({
      id: `category:${main}//${sub ?? ''}`,
      label: `${label} −50 %`,
      payload: { type: 'adjust_category', category_main: main, category_sub: sub, percent: -50 },
    });
    const topCategory = this.categories()[0];
    if (topCategory) {
      presets.push(categoryPreset(topCategory.main, topCategory.sub, topCategory.label));
    }
    // A spiking category is the intervention the data itself suggests.
    const spike = this.recentWindow().find((alert) => alert.type === 'category_spike');
    if (spike?.category_main) {
      const preset = categoryPreset(
        spike.category_main,
        spike.category_sub,
        spike.category_sub ?? spike.category_main,
      );
      if (!presets.some((existing) => existing.id === preset.id)) presets.push(preset);
    }
    return presets;
  });

  /** An applied preset is already shown as a chip - don't offer it twice. */
  protected readonly presets = computed(() => {
    const taken = new Set(this.forecast.adjustments().map((adjustment) => adjustment.id));
    return this.allPresets().filter((preset) => !taken.has(preset.id));
  });

  /** Already-cancelled subscriptions drop out of the picker. */
  protected readonly cancellable = computed(() => {
    const taken = new Set(this.forecast.adjustments().map((adjustment) => adjustment.id));
    return this.forecast
      .expenseSubscriptions()
      .filter((payment) => !taken.has(`cancel:${payment.recurring_id}`));
  });

  /** A negative balance is not an amount that is "free". */
  protected readonly headline = computed(() => {
    const expected = this.forecast.current()?.free_to_spend.expected_chf ?? 0;
    return expected < 0 ? `${chf(Math.abs(expected))} im Minus` : `${chf(expected)} frei`;
  });

  protected readonly tightLabel = computed(() => {
    const current = this.forecast.current();
    if (!current) return null;
    if (!current.tight_date) {
      const low = Math.min(...current.series.map((point) => point.lower_chf));
      return `Der Puffer hält im ganzen Horizont. Tiefster Punkt: ${chf(low)}.`;
    }
    const { date, days_before_salary } = current.tight_date;
    const when = DATE.format(new Date(date));
    return days_before_salary === null
      ? `Reicht bis zum ${when}.`
      : `Reicht bis zum ${when} - ${days_before_salary} Tage vor deinem Lohn.`;
  });

  protected abs(value: number): number {
    return Math.abs(value);
  }

  protected name(payment: RecurringPayment): string {
    return payment.merchant.replace(/[.,].*$/, '');
  }

  protected setHorizon(horizon: Horizon): void {
    this.forecast.horizon.set(horizon);
  }

  protected cancelSubscription(payment: RecurringPayment): void {
    this.forecast.add({
      id: `cancel:${payment.recurring_id}`,
      label: `${this.name(payment)} kündigen`,
      payload: { type: 'cancel_recurring', recurring_id: payment.recurring_id },
    });
    this.menuOpen.set(false);
  }

  protected addSubscription(): void {
    const label = this.newLabel().trim();
    const amount = this.newAmount();
    if (!label || !amount) return;
    this.forecast.add({
      id: `add:${label}`,
      label: `${label} ${chf(amount)}`,
      payload: {
        type: 'add_recurring',
        label,
        amount_chf: amount,
        interval: this.newInterval(),
        start_date: this.forecast.baseline()?.as_of ?? new Date().toISOString().slice(0, 10),
      },
    });
    this.menuOpen.set(false);
  }
}
