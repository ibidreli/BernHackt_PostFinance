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
