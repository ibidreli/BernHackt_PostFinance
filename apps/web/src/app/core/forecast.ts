import { httpResource } from '@angular/common/http';
import { Service, computed, signal } from '@angular/core';

export type Horizon = 'next_salary' | '30d' | '90d' | '365d';
export type Interval = 'monthly' | 'quarterly' | 'yearly' | 'irregular';

export interface SeriesPoint {
  date: string;
  expected_chf: number;
  lower_chf: number;
  upper_chf: number;
}

export interface KnownPayment {
  date: string;
  label: string;
  amount_chf: number;
  category: string | null;
  recurring_id: string | null;
}

export interface ForecastResult {
  as_of: string;
  horizon: Horizon;
  horizon_end: string;
  opening_balance_chf: number;
  next_salary: { date: string; amount_chf: number } | null;
  free_to_spend: { expected_chf: number; lower_chf: number; upper_chf: number };
  tight_date: {
    date: string;
    days_until: number;
    days_before_salary: number | null;
    projected_balance_chf: number;
  } | null;
  known_payments: KnownPayment[];
  series: SeriesPoint[];
  assumptions: {
    variable_baseline_method: string;
    band_method: string;
    excluded_outliers: string[];
    interest_applied: boolean;
    salary_day_detected: boolean;
    variable_baseline_months_used: number;
    notes: string[];
  };
}

export interface Diff {
  monthly_chf: number;
  cumulative_series: { date: string; diff_chf: number }[];
  total_at_horizon_chf: number;
  tight_date_shift_days: number | null;
}

export interface RecurringPayment {
  recurring_id: string;
  merchant: string;
  category_main: string | null;
  amount_chf: number;
  interval: Interval;
  flow: 'expense' | 'income';
  is_active: boolean;
}

export type AdjustmentPayload =
  | { type: 'cancel_recurring'; recurring_id: string }
  | { type: 'adjust_recurring'; recurring_id: string; delta_chf: number }
  | { type: 'add_recurring'; label: string; amount_chf: number; interval: Interval; start_date: string }
  | { type: 'one_off'; label: string; amount_chf: number; date: string };

/** An adjustment plus the chip label the UI shows for it. */
export interface Adjustment {
  id: string;
  label: string;
  payload: AdjustmentPayload;
}

export const HORIZONS: readonly { value: Horizon; label: string }[] = [
  { value: 'next_salary', label: 'Bis Lohn' },
  { value: '30d', label: '30 Tage' },
  { value: '90d', label: '90 Tage' },
  { value: '365d', label: '1 Jahr' },
];

type SimulateResult = { baseline: ForecastResult; scenario: ForecastResult; diff: Diff };

const ODATA = '/odata';

/**
 * Owns the horizon, the active scenario adjustments, and the forecast
 * they produce. One resource serves both cases: with no adjustments it
 * reads the baseline (`GetForecast`), otherwise it asks for baseline and
 * scenario in one round trip (`Simulate`) so both curves can be drawn
 * without a second request.
 */
@Service()
export class Forecast {
  readonly horizon = signal<Horizon>('next_salary');
  readonly adjustments = signal<Adjustment[]>([]);

  private readonly data = httpResource<ForecastResult | SimulateResult>(() => {
    const horizon = this.horizon();
    const adjustments = this.adjustments();
    return adjustments.length
      ? {
          url: `${ODATA}/Simulate`,
          method: 'POST',
          body: { horizon, adjustments: adjustments.map((adjustment) => adjustment.payload) },
        }
      : { url: `${ODATA}/GetForecast`, method: 'GET', params: { horizon } };
  });

  /** Active expense subscriptions, for the cancel picker. */
  readonly recurring = httpResource<{ value: RecurringPayment[] }>(() => ({
    url: `${ODATA}/RecurringPayments`,
    params: { $filter: "is_active eq true and flow eq 'expense'", $orderby: 'amount_chf desc' },
  }));

  readonly isLoading = this.data.isLoading;
  readonly error = this.data.error;

  private readonly result = computed(() => (this.data.hasValue() ? this.data.value() : null));

  readonly baseline = computed<ForecastResult | null>(() => {
    const result = this.result();
    if (!result) return null;
    return 'baseline' in result ? result.baseline : result;
  });

  /** Non-null only while a scenario is active. */
  readonly scenario = computed<ForecastResult | null>(() => {
    const result = this.result();
    return result && 'scenario' in result ? result.scenario : null;
  });

  readonly diff = computed<Diff | null>(() => {
    const result = this.result();
    return result && 'diff' in result ? result.diff : null;
  });

  /** The curve the headline numbers describe: scenario if there is one. */
  readonly current = computed(() => this.scenario() ?? this.baseline());

  readonly expenseSubscriptions = computed(() =>
    this.recurring.hasValue() ? this.recurring.value().value : [],
  );

  /** The largest recurring expenses, used to build data-driven presets. */
  readonly topMonthly = computed(() =>
    this.expenseSubscriptions().filter((payment) => payment.interval === 'monthly'),
  );

  add(adjustment: Adjustment): void {
    this.adjustments.update((current) =>
      current.some((existing) => existing.id === adjustment.id) ? current : [...current, adjustment],
    );
  }

  remove(id: string): void {
    this.adjustments.update((current) => current.filter((adjustment) => adjustment.id !== id));
  }

  reset(): void {
    this.adjustments.set([]);
  }
}
