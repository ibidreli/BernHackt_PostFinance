import { Component, computed, effect, inject, signal } from '@angular/core';

import { chf, chfExact } from '../../core/chart-theme';
import {
  Graph,
  SUMMARY_THRESHOLD,
  findNode,
  pathTo,
  type GraphFlow,
  type GraphMode,
  type GraphNode,
} from '../../core/graph';
import { RailOutlet } from '../../core/rail';
import { Theme } from '../../core/theme';
import { ExplorerGraph } from './explorer-graph';

const MONTH = new Intl.DateTimeFormat('de-CH', { month: 'short', year: '2-digit' });
const DATE = new Intl.DateTimeFormat('de-CH', { day: '2-digit', month: '2-digit', year: 'numeric' });

export const FLOWS: readonly { value: GraphFlow; label: string }[] = [
  { value: 'expense', label: 'Ausgaben' },
  { value: 'income', label: 'Einnahmen' },
  { value: 'both', label: 'Beides' },
];

@Component({
  imports: [ExplorerGraph, RailOutlet],
  selector: 'app-explorer',
  templateUrl: './explorer.html',
})
export class ExplorerPage {
  protected readonly graph = inject(Graph);
  protected readonly theme = inject(Theme);
  protected readonly flows = FLOWS;
  protected readonly chf = chf;
  protected readonly chfExact = chfExact;
  protected readonly summaryThreshold = SUMMARY_THRESHOLD;

  protected readonly focusId = signal<string | null>(null);
  protected readonly selected = signal<GraphNode | null>(null);
  protected readonly showTable = signal(false);

  constructor() {
    // A focus id from one month rarely exists in the next, and a stale
    // one would silently zoom back to the root anyway.
    effect(() => {
      this.graph.activeMonth();
      this.graph.flow();
      this.focusId.set(null);
      this.selected.set(null);
    });
  }

  protected readonly focusNode = computed(() => {
    const tree = this.graph.tree();
    const id = this.focusId();
    return tree ? (id ? (findNode(tree, id) ?? tree) : tree) : null;
  });

  /** The bar owns the table toggle, so the table only shows with it. */
  protected readonly summaryVisible = computed(
    () => (this.focusNode()?.summary?.child_count ?? 0) > SUMMARY_THRESHOLD,
  );

  protected readonly breadcrumb = computed(() => {
    const tree = this.graph.tree();
    const id = this.focusId();
    return tree && id ? pathTo(tree, id) : tree ? [tree] : [];
  });

  /** Leaves of the focused node, for the "Details anzeigen" table. */
  protected readonly focusTransactions = computed(() => {
    const node = this.focusNode();
    if (!node) return [];
    const out: GraphNode[] = [];
    const walk = (current: GraphNode) => {
      if (current.transaction) out.push(current);
      for (const child of current.children ?? []) walk(child);
    };
    walk(node);
    return out.sort((a, b) => (b.amount_chf ?? 0) - (a.amount_chf ?? 0));
  });

  protected monthLabel(month: string): string {
    return MONTH.format(new Date(`${month}-01`));
  }

  protected dateLabel(iso: string): string {
    return DATE.format(new Date(iso));
  }

  protected setFlow(flow: GraphFlow): void {
    this.graph.flow.set(flow);
  }

  protected setMode(mode: GraphMode): void {
    if (mode === 'delta' && !this.graph.deltaAvailable()) return;
    this.graph.mode.set(mode);
  }

  protected setMonthIndex(index: number): void {
    const month = this.graph.months()[index];
    if (month) this.graph.month.set(month);
  }

  protected readonly monthIndex = computed(() =>
    Math.max(this.graph.months().indexOf(this.graph.activeMonth() ?? ''), 0),
  );

  /** Fractional slider position while dragging, null when idle. */
  protected readonly scrub = signal<number | null>(null);

  /** The two months a fractional position sits between, and how far along. */
  private readonly scrubSpan = computed<{ a: string; b: string; t: number } | null>(() => {
    const value = this.scrub();
    const months = this.graph.months();
    if (value === null || !months.length) return null;
    const i = Math.max(0, Math.min(Math.floor(value), months.length - 1));
    const j = Math.min(i + 1, months.length - 1);
    return { a: months[i], b: months[j], t: value - i };
  });

  /** While scrubbing the graph shows floor(v), not the nearest month -
      tree/blendTree/t stay monotone instead of flipping at the midpoint. */
  protected readonly displayTree = computed<GraphNode | null>(() => {
    const span = this.scrubSpan();
    if (!span) return this.graph.tree();
    return this.graph.treeFor(span.a) ?? this.graph.tree();
  });

  protected readonly blendTree = computed<GraphNode | null>(() => {
    const span = this.scrubSpan();
    if (!span || span.a === span.b) return null;
    // Both neighbours must be cached and non-empty; otherwise degrade to
    // the stepped behaviour instead of morphing against nothing.
    const from = this.graph.treeFor(span.a);
    const to = this.graph.treeFor(span.b);
    if (!from || !to || from.amount_chf <= 0 || to.amount_chf <= 0) return null;
    return to;
  });

  protected readonly blendT = computed(() => (this.blendTree() ? this.scrubSpan()!.t : 0));

  protected readonly sliderValue = computed(() => this.scrub() ?? this.monthIndex());

  protected onSliderInput(value: number): void {
    // The blend renders from the root; clearing the focus here keeps the
    // breadcrumb honest instead of naming a node that no longer shows.
    this.focusId.set(null);
    this.scrub.set(value);
    this.setMonthIndex(Math.round(value));
  }

  protected onSliderChange(value: number): void {
    this.scrub.set(null);
    this.setMonthIndex(Math.round(value));
  }

  /** step="any" turns the native arrow keys into 1%-of-range micro-steps;
      keyboard users still get whole months with the normal transition. */
  protected onSliderKeydown(event: KeyboardEvent): void {
    const last = this.graph.months().length - 1;
    if (last < 0) return;
    const current = Math.round(this.sliderValue());
    let next: number;
    switch (event.key) {
      case 'ArrowLeft':
      case 'ArrowDown':
        next = current - 1;
        break;
      case 'ArrowRight':
      case 'ArrowUp':
        next = current + 1;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = last;
        break;
      default:
        return;
    }
    event.preventDefault();
    this.scrub.set(null);
    this.setMonthIndex(Math.max(0, Math.min(next, last)));
  }

  /** Preset: the two flows side by side at root level, absolute. */
  protected presetBoth(): void {
    this.graph.flow.set('both');
    this.graph.mode.set('absolute');
    this.focusId.set(null);
  }

  protected presetOverview(): void {
    this.graph.flow.set('expense');
    this.graph.mode.set('absolute');
    this.focusId.set(null);
  }

  protected presetChange(): void {
    if (!this.graph.deltaAvailable()) return;
    this.graph.flow.set('expense');
    this.graph.mode.set('delta');
    this.focusId.set(null);
  }
}
