import { HttpClient } from '@angular/common/http';
import { Service, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export type Horizon = 'present' | '1y' | '5y' | '10y';
export type Status = 'yes' | 'tight' | 'no_unless' | 'needs_clarification' | 'unsupported';
export type Intent = 'affordability' | 'what_if' | 'time_to_goal' | 'unsupported';

/** Which fields are populated depends on intent/status; unused ones stay null. */
export interface Facts {
  target_chf: number | null;
  projected_chf: number | null;
  gap_chf: number | null;
  required_monthly_chf: number | null;
  months_remaining: number | null;
  buffer_after_months: number | null;
  wait_months: number | null;
  goal_date: string | null;
  goal_date_earliest: string | null;
  goal_date_latest: string | null;
  impact_monthly_chf: number | null;
  impact_cumulative_chf: number | null;
}

export interface Lever {
  category: string;
  monthly_avg_chf: number;
  potential_chf: number;
}

export interface ChartPoint {
  date: string;
  expected_chf: number;
  lower_chf: number;
  upper_chf: number;
}

export interface WealthOverTimeChart {
  type: 'wealth_over_time';
  series: ChartPoint[];
  target_line_chf: number | null;
  crossing_date: string | null;
}

export interface GoalProgressChart {
  type: 'goal_progress';
  series: ChartPoint[];
  target_chf: number;
  expected_date: string | null;
  earliest_date: string | null;
  latest_date: string | null;
}

export interface BeforeAfterChart {
  type: 'before_after';
  baseline_series: ChartPoint[];
  scenario_series: ChartPoint[];
  diff_at_horizon_chf: number;
}

/** Discriminated on `type` — the backend picks one of three fixed shapes. */
export type ChartSpec = WealthOverTimeChart | GoalProgressChart | BeforeAfterChart;

export interface AssumptionsUsed {
  salary_growth_pct: number;
  inflation_pct: number;
  savings_rate_pct: number;
  interest_applied: boolean;
}

export interface Clarification {
  question: string;
  options: string[];
  field: string;
}

export interface Answer {
  intent: Intent;
  status: Status;
  answer: string;
  facts: Facts | null;
  levers: Lever[];
  chart: ChartSpec | null;
  /** null when status is needs_clarification or unsupported. */
  assumptions_used: AssumptionsUsed | null;
  clarification: Clarification | null;
  source: 'live' | 'cached';
}

/** `text` is what the chat shows, `sent` what the backend parsed. */
export type Message =
  | { role: 'user'; text: string; sent: string }
  | { role: 'error'; text: string }
  | ({ role: 'bot' } & Answer);

export const HORIZONS: readonly { value: Horizon; label: string }[] = [
  { value: 'present', label: 'Heute' },
  { value: '1y', label: '1 Jahr' },
  { value: '5y', label: '5 Jahre' },
  { value: '10y', label: '10 Jahre' },
];

const api = '/api/v1/assistant';

/**
 * Owns the conversation and the three assumption sliders.
 *
 * Deliberately thin: it holds no financial logic at all. Every number
 * shown in the UI arrives from the backend, which computes it through
 * `forecast_service` - the same function the Prognose page's
 * `GetForecast`/`Simulate` calls go through. The LLM only interprets the
 * question and phrases the answer; a 502/504 from either call surfaces
 * here as an error message in the transcript, never a silent fallback.
 */
@Service()
export class Assistant {
  private readonly http = inject(HttpClient);

  /** One conversation per page visit - lets the backend resolve follow-ups. */
  private readonly conversationId = crypto.randomUUID();

  readonly horizon = signal<Horizon>('5y');
  readonly salaryGrowthPct = signal(1);
  readonly inflationPct = signal(1.5);
  /** `null` = derived from the transaction history rather than overridden. */
  readonly savingsRatePct = signal<number | null>(null);

  readonly messages = signal<Message[]>([]);
  readonly pending = signal(false);
  readonly suggestions = signal<string[]>([]);

  /** The clarification the next message answers, if any (max one open). */
  readonly pendingClarification = computed(() => {
    const last = this.messages().at(-1);
    return last?.role === 'bot' ? (last.clarification?.field ?? null) : null;
  });

  async loadSuggestions(): Promise<void> {
    try {
      const response = await firstValueFrom(
        this.http.get<{ suggestions: string[] }>(`${api}/suggestions`, {
          params: { horizon: this.horizon() },
        }),
      );
      this.suggestions.set(response.suggestions);
    } catch {
      // Keep the previous chips - suggestions are a convenience, not data.
    }
  }

  /**
   * `display` is what the chat shows; `message` is what the backend
   * parses. They differ when a clarification is answered - see
   * {@link answerClarification}.
   */
  async ask(message: string, display = message): Promise<void> {
    if (!message.trim() || this.pending()) return;
    const pendingClarification = this.pendingClarification();
    this.messages.update((messages) => [...messages, { role: 'user', text: display, sent: message }]);
    this.pending.set(true);
    try {
      const answer = await firstValueFrom(
        this.http.post<Answer>(`${api}/ask`, {
          message,
          horizon: this.horizon(),
          assumptions: {
            salary_growth_pct: this.salaryGrowthPct(),
            inflation_pct: this.inflationPct(),
            savings_rate_pct: this.savingsRatePct(),
          },
          context: { conversation_id: this.conversationId, pending_clarification: pendingClarification },
        }),
      );
      this.messages.update((messages) => [...messages, { role: 'bot', ...answer }]);
    } catch (error) {
      this.messages.update((messages) => [...messages, { role: 'error', text: describe(error) }]);
    } finally {
      this.pending.set(false);
    }
  }

  /**
   * A clarification answer is just the chosen option - the backend
   * resolves it against the open clarification via `conversation_id`
   * plus `pending_clarification`, without a second LLM call.
   */
  async answerClarification(option: string): Promise<void> {
    await this.ask(option);
  }

  /**
   * Re-runs the last real question so a moved slider is felt
   * immediately. A clarification answer ("Bar") is not a question of
   * its own, so replay goes back to the question that triggered it -
   * the backend then asks the clarification again.
   */
  async replay(): Promise<void> {
    const question = this.lastQuestion();
    if (!question) return;
    this.messages.update((messages) => messages.slice(0, -2));
    await this.ask(question);
  }

  private lastQuestion(): string | null {
    const messages = this.messages();
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message.role !== 'user') continue;
      // Skip clarification answers: the user message right before a
      // clarification answer's bot reply is the question to replay.
      const previousBot = messages
        .slice(0, i)
        .reverse()
        .find((m) => m.role === 'bot');
      if (previousBot && previousBot.role === 'bot' && previousBot.clarification) continue;
      return message.sent;
    }
    return null;
  }
}

/** The backend answers errors in the OData shape `{error: {message}}` service-wide. */
function describe(error: unknown): string {
  const body = (error as { error?: { error?: { message?: string } } } | null)?.error;
  return body?.error?.message ?? 'Anfrage fehlgeschlagen. Bitte versuch es noch einmal.';
}
