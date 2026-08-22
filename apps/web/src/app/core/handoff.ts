import { Service, signal } from '@angular/core';

import type { Adjustment } from './forecast';

/**
 * Hand-over channel between the three pages (Sollstatus: a shared
 * service for the live flow; query params only for deep links into
 * /kategorien). Consume-once semantics: a writer sets and navigates,
 * the target page takes the value in its constructor - so nothing
 * leaks into a later, unrelated visit.
 */
@Service()
export class Handoff {
  private readonly pendingAdjustment = signal<Adjustment | null>(null);
  private readonly pendingQuestion = signal<string | null>(null);

  sendAdjustment(adjustment: Adjustment): void {
    this.pendingAdjustment.set(adjustment);
  }

  sendQuestion(question: string): void {
    this.pendingQuestion.set(question);
  }

  takeAdjustment(): Adjustment | null {
    const value = this.pendingAdjustment();
    this.pendingAdjustment.set(null);
    return value;
  }

  takeQuestion(): string | null {
    const value = this.pendingQuestion();
    this.pendingQuestion.set(null);
    return value;
  }
}
