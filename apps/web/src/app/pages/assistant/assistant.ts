import {
  Component,
  ElementRef,
  afterRenderEffect,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { Assistant, HORIZONS, type Horizon, type Lever, type Status } from '../../core/assistant';
import type { AdjustmentPayload } from '../../core/forecast';
import { Handoff } from '../../core/handoff';
import { RailOutlet } from '../../core/rail';
import { AssistantChart } from './assistant-chart';

const STATUS_BADGES: Record<Status, { label: string; classes: string }> = {
  yes: { label: 'Liegt drin', classes: 'bg-success/15 text-success' },
  tight: { label: 'Knapp', classes: 'bg-warning/15 text-warning' },
  no_unless: { label: 'Nein, ausser', classes: 'bg-danger/15 text-danger' },
  needs_clarification: { label: 'Rückfrage', classes: 'bg-surface text-muted-foreground' },
  unsupported: { label: 'Nicht unterstützt', classes: 'bg-surface text-muted-foreground' },
};

const CHF = new Intl.NumberFormat('de-CH', { style: 'currency', currency: 'CHF', maximumFractionDigits: 0 });

@Component({
  imports: [AssistantChart, RailOutlet, RouterLink],
  selector: 'app-assistant',
  templateUrl: './assistant.html',
})
export class AssistantPage {
  protected readonly assistant = inject(Assistant);
  private readonly handoff = inject(Handoff);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  protected readonly horizons = HORIZONS;
  protected readonly draft = signal('');

  private readonly transcript = viewChild.required<ElementRef<HTMLElement>>('transcript');

  constructor() {
    // Prefilled question from Prognose/Kategorien (Handoff) or a shared
    // ?q= deep link - it lands in the input and is NOT auto-submitted
    // (Sollstatus: the user always fires the question themselves).
    const prefill = this.handoff.takeQuestion() ?? this.route.snapshot.queryParamMap.get('q');
    if (prefill) this.draft.set(prefill);

    effect(() => {
      this.assistant.horizon();
      void this.assistant.loadSuggestions();
    });

    // Bring the newest question to the top so its answer reads from the
    // start - an answer card with a chart is taller than the transcript.
    // Instant, not smooth: the card's entrance animation cancels a smooth
    // scroll partway through.
    afterRenderEffect({
      write: () => {
        this.assistant.messages();
        const element = this.transcript().nativeElement;
        const questions = element.querySelectorAll('[data-question]');
        const latest = questions[questions.length - 1];
        if (!latest) return;
        element.scrollTop +=
          latest.getBoundingClientRect().top - element.getBoundingClientRect().top;
      },
    });
  }

  protected badge(status: Status) {
    return STATUS_BADGES[status];
  }

  protected chf(value: number): string {
    return CHF.format(value);
  }

  protected setHorizon(horizon: Horizon): void {
    this.assistant.horizon.set(horizon);
  }

  protected send(message = this.draft()): void {
    this.draft.set('');
    void this.assistant.ask(message);
  }

  /** what_if answers carry their resolved intervention - hand it to the
      Prognose as an active scenario chip. */
  protected adoptScenario(intervention: AdjustmentPayload): void {
    this.handoff.sendAdjustment({
      id: this.interventionId(intervention),
      label: this.interventionLabel(intervention),
      payload: intervention,
    });
    void this.router.navigate(['/']);
  }

  private interventionId(payload: AdjustmentPayload): string {
    switch (payload.type) {
      case 'adjust_category':
        return `category:${payload.category_main}//${payload.category_sub ?? ''}`;
      case 'cancel_recurring':
        return `cancel:${payload.recurring_id}`;
      case 'adjust_recurring':
        return `raise:${payload.recurring_id}`;
      case 'add_recurring':
        return `add:${payload.label}`;
      case 'one_off':
        return `oneoff:${payload.label}`;
    }
  }

  private interventionLabel(payload: AdjustmentPayload): string {
    switch (payload.type) {
      case 'adjust_category': {
        const name = payload.category_sub ?? payload.category_main;
        if (payload.percent !== undefined && payload.percent !== null) {
          return `${name} ${payload.percent > 0 ? '+' : ''}${payload.percent} %`;
        }
        return `${name} ${(payload.delta_chf ?? 0) > 0 ? '+' : ''}${payload.delta_chf ?? 0} CHF`;
      }
      case 'cancel_recurring':
        return 'Kündigung aus Future Me';
      case 'adjust_recurring':
        return `Anpassung ${payload.delta_chf > 0 ? '+' : ''}${payload.delta_chf} CHF`;
      case 'add_recurring':
        return `${payload.label} ${CHF.format(payload.amount_chf)}`;
      case 'one_off':
        return `${payload.label} einmalig ${CHF.format(payload.amount_chf)}`;
    }
  }

  /** Bar segments share one scale: the biggest lever's monthly average
      is 100%, so the bars stay comparable across the list. */
  protected leverPct(value: number, levers: Lever[]): number {
    const max = levers[0]?.monthly_avg_chf || 1;
    return Math.max((value / max) * 100, 0);
  }

  /** The whole derivation in one hover sentence - the bar shows it, the
      title spells it out. */
  protected leverTitle(lever: Lever): string {
    const floor = lever.monthly_avg_chf - lever.potential_chf;
    return (
      `Üblicher Monat: ${CHF.format(lever.monthly_avg_chf)} · sparsamster Monat: ` +
      `${CHF.format(floor)} · Differenz = Sparpotenzial ${CHF.format(lever.potential_chf)}`
    );
  }

  /** Lever category ("Main // Sub") -> its bubble on /kategorien. */
  protected leverLink(category: string): Record<string, string> {
    const [main, sub] = category.split(' // ');
    return { category: `${main}~${sub ?? ''}` };
  }
}
