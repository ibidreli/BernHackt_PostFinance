import { Component, computed, inject, signal } from '@angular/core';

import { chf } from '../../core/chart-theme';
import {
  Forecast,
  HORIZONS,
  type Adjustment,
  type Horizon,
  type Interval,
  type RecurringPayment,
} from '../../core/forecast';
import { RailOutlet } from '../../core/rail';
import { ForecastChart } from './forecast-chart';

const DATE = new Intl.DateTimeFormat('de-CH', { day: 'numeric', month: 'long' });

@Component({
  imports: [ForecastChart, RailOutlet],
  selector: 'app-forecast',
  templateUrl: './forecast.html',
})
export class ForecastPage {
  protected readonly forecast = inject(Forecast);
  protected readonly horizons = HORIZONS;
  protected readonly chf = chf;

  protected readonly newLabel = signal('Fitnessabo');
  protected readonly newAmount = signal(89);
  protected readonly newInterval = signal<Interval>('monthly');
  protected readonly cancelId = signal('');

  /**
   * Presets built from the actual data rather than hard-coded merchants:
   * "Miete +200" only exists if this account has a rent payment. The two
   * largest monthly expenses stand in for the issue's rent and Netflix.
   */
  protected readonly presets = computed<Adjustment[]>(() => {
    const [first, second] = this.forecast.topMonthly();
    const presets: Adjustment[] = [];
    if (first) {
      presets.push({
        id: `raise:${first.recurring_id}`,
        label: `${this.name(first)} +200`,
        payload: { type: 'adjust_recurring', recurring_id: first.recurring_id, delta_chf: 200 },
      });
    }
    const cancellable = second ?? first;
    if (cancellable) {
      presets.push({
        id: `cancel:${cancellable.recurring_id}`,
        label: `${this.name(cancellable)} kündigen`,
        payload: { type: 'cancel_recurring', recurring_id: cancellable.recurring_id },
      });
    }
    presets.push({
      id: 'add:Fitnessabo',
      label: 'Fitnessabo CHF 89',
      payload: {
        type: 'add_recurring',
        label: 'Fitnessabo',
        amount_chf: 89,
        interval: 'monthly',
        start_date: this.forecast.baseline()?.as_of ?? new Date().toISOString().slice(0, 10),
      },
    });
    return presets;
  });

  /** The full list runs to dozens of merchants - name a few, count the rest. */
  protected readonly outliers = computed(() => {
    const names = this.forecast.current()?.assumptions.excluded_outliers ?? [];
    const shown = names.slice(0, 3).join(', ');
    return names.length > 3 ? `${shown} und ${names.length - 3} weitere` : shown;
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

  protected cancelSelected(): void {
    const payment = this.forecast
      .expenseSubscriptions()
      .find((candidate) => candidate.recurring_id === this.cancelId());
    if (!payment) return;
    this.forecast.add({
      id: `cancel:${payment.recurring_id}`,
      label: `${this.name(payment)} kündigen`,
      payload: { type: 'cancel_recurring', recurring_id: payment.recurring_id },
    });
    this.cancelId.set('');
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
  }
}
