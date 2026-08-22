import {
  Component,
  ElementRef,
  afterRenderEffect,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';

import { Assistant, HORIZONS, type Horizon, type Status } from '../../core/assistant';
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
  imports: [AssistantChart],
  selector: 'app-assistant',
  templateUrl: './assistant.html',
})
export class AssistantPage {
  protected readonly assistant = inject(Assistant);
  protected readonly horizons = HORIZONS;
  protected readonly draft = signal('');

  private readonly transcript = viewChild.required<ElementRef<HTMLElement>>('transcript');

  constructor() {
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
}
