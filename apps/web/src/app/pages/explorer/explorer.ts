import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { Alerts, alertSentence, buildAlertIndex, type AlertDto } from '../../core/alerts';
import { chf, chfExact } from '../../core/chart-theme';
import { Forecast, type Adjustment } from '../../core/forecast';
import { Handoff } from '../../core/handoff';
import {
  Graph,
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
  private readonly alerts = inject(Alerts);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly handoff = inject(Handoff);
  private readonly forecast = inject(Forecast);
  protected readonly flows = FLOWS;
  protected readonly chf = chf;
  protected readonly chfExact = chfExact;
  protected readonly alertSentence = alertSentence;

  protected readonly focusId = signal<string | null>(null);
  protected readonly selected = signal<GraphNode | null>(null);
  /** "Nur Auffälligkeiten" - dims everything without an alert. */
  protected readonly alertsOnly = signal(false);

  /** Deep link (`?month=…&category=main~sub&tx=…`) waiting for its
      month's tree - applied once, then released. */
  private readonly pendingDeepLink = signal<{
    month: string | null;
    category: string | null;
    tx: string | null;
  } | null>(null);

  constructor() {
    // Deep-link params are read once, before the effects below first
    // run - so the first run already sees the target month and the
    // clearing effect's guard is armed.
    const params = this.route.snapshot.queryParamMap;
    const month = params.get('month');
    const category = params.get('category');
    const tx = params.get('tx');
    if (month || category || tx) {
      this.pendingDeepLink.set({ month, category, tx });
      // Alerts and their categories live on the expense side.
      this.graph.flow.set('expense');
      if (month) this.graph.month.set(month);
    }

    // A focus id from one month rarely exists in the next, and a stale
    // one would silently zoom back to the root anyway.
    effect(() => {
      this.graph.activeMonth();
      this.graph.flow();
      // While a deep link is pending, the month change is our own doing -
      // clearing here would wipe the focus the apply effect is about to
      // set. Untracked: the pending release must not re-trigger this.
      if (untracked(this.pendingDeepLink)) return;
      this.focusId.set(null);
      this.selected.set(null);
    });

    // One-shot: as soon as the target month's tree is cached, resolve
    // the node, focus it, and release the pending state.
    effect(() => {
      const pending = this.pendingDeepLink();
      if (!pending) return;
      const month = pending.month ?? this.graph.activeMonth();
      const tree = month ? this.graph.treeFor(month) : null;
      if (!tree) return;

      const target = this.resolveDeepLink(tree, pending);
      if (target) {
        const path = pathTo(tree, target.id);
        const focus = target.transaction ? (path.at(-2) ?? target) : target;
        this.focusId.set(focus.id === tree.id ? null : focus.id);
        this.selected.set(target.transaction ? target : null);
      }
      this.pendingDeepLink.set(null);
    });
  }

  private resolveDeepLink(
    tree: GraphNode,
    pending: { category: string | null; tx: string | null },
  ): GraphNode | null {
    if (pending.tx) return findNode(tree, pending.tx);
    if (!pending.category) return null;
    const [main, sub] = pending.category.split('~');
    let fallback: GraphNode | null = null;
    const walk = (node: GraphNode): GraphNode | null => {
      if (node.node_type === 'category' && node.category_main === main) {
        if ((node.category_sub ?? '') === (sub ?? '')) return node;
        fallback ??= node;
      }
      for (const child of node.children ?? []) {
        const found = walk(child);
        if (found) return found;
      }
      return null;
    };
    return walk(tree) ?? fallback;
  }

  protected readonly focusNode = computed(() => {
    const tree = this.graph.tree();
    const id = this.focusId();
    return tree ? (id ? (findNode(tree, id) ?? tree) : tree) : null;
  });

  /** Client-side alert join for the active month's tree. */
  protected readonly alertIndex = computed(() => {
    const tree = this.graph.tree();
    const month = this.graph.activeMonth();
    if (!tree || !month) return null;
    return buildAlertIndex(
      tree,
      this.alerts.byTransactionId(),
      this.alerts.spikesByMonth().get(month),
    );
  });

  /** How many alerts the current view carries - the filter chip's badge. */
  protected readonly monthAlertCount = computed(() => {
    const tree = this.graph.tree();
    const index = this.alertIndex();
    return tree && index ? (index.subtree.has(tree.id) ? this.countTreeAlerts(tree, index) : 0) : 0;
  });

  private countTreeAlerts(tree: GraphNode, index: { own: Map<string, AlertDto[]> }): number {
    const ids = new Set<string>();
    const walk = (node: GraphNode) => {
      for (const alert of index.own.get(node.id) ?? []) ids.add(alert.alert_id);
      for (const child of node.children ?? []) walk(child);
    };
    walk(tree);
    return ids.size;
  }

  /** Alerts of the selected transaction, for the detail panel. */
  protected readonly selectedAlerts = computed<AlertDto[]>(() => {
    const node = this.selected();
    return (node && this.alertIndex()?.own.get(node.id)) || [];
  });

  protected alertClasses(severity: AlertDto['severity']): string {
    if (severity === 'danger') return 'bg-danger/10 text-danger';
    if (severity === 'warning') return 'bg-warning/10 text-warning';
    return 'bg-surface text-muted-foreground';
  }

  /** Category/merchant focus nodes connect into the other two pages
      (Sollstatus). Income stays out - adjust_category and the what-if
      templates act on expenses. */
  protected readonly connectable = computed(() => {
    const node = this.focusNode();
    if (!node || node.flow === 'income') return null;
    const linkable =
      node.node_type === 'category' ||
      node.node_type === 'merchant' ||
      node.node_type === 'merchant_group';
    return linkable ? node : null;
  });

  /** Active subscription behind a merchant node, if any - it decides
      between a cancel_recurring and an adjust_category handoff. */
  private subscriptionFor(node: GraphNode) {
    return node.merchant
      ? this.forecast.expenseSubscriptions().find((payment) => payment.merchant === node.merchant)
      : undefined;
  }

  protected simulateFocus(): void {
    const node = this.connectable();
    if (!node) return;
    const subscription = this.subscriptionFor(node);
    const label = node.category_sub ?? node.category_main ?? node.label;
    const adjustment: Adjustment = subscription
      ? {
          id: `cancel:${subscription.recurring_id}`,
          label: `${node.label} kündigen`,
          payload: { type: 'cancel_recurring', recurring_id: subscription.recurring_id },
        }
      : {
          id: `category:${node.category_main}//${node.category_sub ?? ''}`,
          label: `${label} −50 %`,
          payload: {
            type: 'adjust_category',
            category_main: node.category_main ?? node.label,
            category_sub: node.category_sub,
            percent: -50,
          },
        };
    this.handoff.sendAdjustment(adjustment);
    void this.router.navigate(['/']);
  }

  protected askFutureMe(): void {
    const node = this.connectable();
    if (!node) return;
    const question = this.subscriptionFor(node)
      ? `Was wäre, wenn ich ${node.label} kündige?`
      : `Was wäre, wenn ich ${node.category_sub ?? node.category_main ?? node.label} halbiere?`;
    this.handoff.sendQuestion(question);
    void this.router.navigate(['/future-me']);
  }

  /** Count/average/total for the always-visible details block. Computed
      from the leaves directly - `focusNode().summary` only exists above
      the backend's child-count threshold, the details no longer are. */
  protected readonly focusStats = computed(() => {
    const transactions = this.focusTransactions();
    if (!transactions.length) return null;
    const total = transactions.reduce((sum, node) => sum + (node.amount_chf ?? 0), 0);
    return { count: transactions.length, total, avg: total / transactions.length };
  });

  /** The details table stays quiet: the largest bookings, capped - at
      root focus a month has hundreds of leaves, and a permanently
      rendered full list would dominate the DOM, not the page. */
  protected readonly visibleTransactions = computed(() => this.focusTransactions().slice(0, 50));

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
