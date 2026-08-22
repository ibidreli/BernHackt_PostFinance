import { HttpClient } from '@angular/common/http';
import { Service, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export type Horizon = 'present' | '1y' | '5y' | '10y';
export type Status = 'yes' | 'tight' | 'no_unless' | 'needs_clarification' | 'unsupported';
export type ChartType = 'wealth_over_time' | 'goal_progress' | 'before_after';

export interface Facts {
  target_chf: number;
  projected_chf: number;
  gap_chf: number;
  required_monthly_chf: number;
  months_remaining: number;
  buffer_after_months: number;
  wait_months: number | null;
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
  baseline_chf: number | null;
}

export interface ChartSpec {
  type: ChartType;
  series: ChartPoint[];
  target_line_chf: number | null;
  crossing_date: string | null;
}

export interface AssumptionsUsed {
  salary_growth_pct: number;
  inflation_pct: number;
  savings_rate_pct: number;
  interest_applied: boolean;
  notes: string[];
}

export interface Clarification {
  question: string;
  options: string[];
  field: string;
}

export interface Answer {
  intent: string | null;
  status: Status;
  horizon: Horizon;
  answer: string;
  facts: Facts | null;
  levers: Lever[];
  chart: ChartSpec | null;
  assumptions_used: AssumptionsUsed;
  clarification: Clarification | null;
  source: string;
}

/** `text` is what the chat shows, `sent` what the backend parsed. */
export type Message = { role: 'user'; text: string; sent: string } | ({ role: 'bot' } & Answer);

export const HORIZONS: readonly { value: Horizon; label: string }[] = [
  { value: 'present', label: 'Heute' },
  { value: '1y', label: '1 Jahr' },
  { value: '5y', label: '5 Jahre' },
  { value: '10y', label: '10 Jahre' },
];

const API = '/api/v1/assistant';

/**
 * Owns the conversation and the three assumption sliders.
 *
 * Deliberately thin: it holds no financial logic at all. Every number
 * shown in the UI arrives from the backend, which computes it through
 * `forecast_service` - the same function the Feature 2 slider calls.
 */
@Service()
export class Assistant {
  private readonly http = inject(HttpClient);

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
    const response = await firstValueFrom(
      this.http.get<{ suggestions: string[] }>(`${API}/suggestions`, {
        params: { horizon: this.horizon() },
      }),
    );
    this.suggestions.set(response.suggestions);
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
        this.http.post<Answer>(`${API}/ask`, {
          message,
          horizon: this.horizon(),
          assumptions: {
            salary_growth_pct: this.salaryGrowthPct(),
            inflation_pct: this.inflationPct(),
            savings_rate_pct: this.savingsRatePct(),
          },
          context: { conversation_id: null, pending_clarification: pendingClarification },
        }),
      );
      // A horizon named in the question wins over the switcher, and the
      // switcher visibly follows - the issue's edge case.
      this.horizon.set(answer.horizon);
      this.messages.update((messages) => [...messages, { role: 'bot', ...answer }]);
    } finally {
      this.pending.set(false);
    }
  }

  /**
   * A clarification button carries no question of its own - "Bar" alone
   * is not a supported question. The original question is resent with
   * the chosen option appended, while the chat shows just the option.
   */
  async answerClarification(option: string): Promise<void> {
    const question = this.lastQuestion();
    await this.ask(question ? `${question} ${option}` : option, option);
  }

  /** Re-runs the last question so a moved slider is felt immediately. */
  async replay(): Promise<void> {
    const question = this.lastQuestion();
    if (!question) return;
    this.messages.update((messages) => messages.slice(0, -2));
    await this.ask(question);
  }

  private lastQuestion(): string | null {
    const asked = this.messages().filter((m) => m.role === 'user');
    return asked.at(-1)?.sent ?? null;
  }
}
