import { httpResource } from '@angular/common/http';
import { Service, computed, effect, signal, untracked } from '@angular/core';

export type GraphMode = 'absolute' | 'delta';
export type GraphFlow = 'expense' | 'income' | 'both';
export type DeltaDirection = 'favourable' | 'unfavourable' | 'neutral';
export type NodeType = 'root' | 'flow' | 'category' | 'merchant' | 'merchant_group' | 'transaction';

export interface GraphDelta {
  baseline_median_chf: number;
  diff_chf: number;
  diff_pct: number | null;
  direction: DeltaDirection;
}

export interface GraphSummary {
  child_count: number;
  transaction_count: number;
  total_amount_chf: number;
  avg_amount_chf: number;
}

export interface TransactionPayload {
  id: string;
  date: string;
  value_date: string;
  merchant: string;
  merchant_canonical: string;
  original_description: string;
  amount_chf: number;
  flow: 'expense' | 'income';
  category_main: string | null;
  category_sub: string | null;
  original_amount: number | null;
  original_currency: string | null;
  status: string | null;
}

export interface GraphNode {
  id: string;
  label: string;
  level: number;
  node_type: NodeType;
  flow: 'expense' | 'income' | null;
  amount_chf: number;
  transaction_count: number;
  rank: number | null;
  merchant_count: number | null;
  category_main: string | null;
  category_sub: string | null;
  merchant: string | null;
  children: GraphNode[] | null;
  transaction: TransactionPayload | null;
  delta: GraphDelta | null;
  summary: GraphSummary | null;
}

export interface GraphResponse {
  month: string;
  mode: GraphMode;
  flow: GraphFlow;
  baseline_months: string[];
  baseline_label: string | null;
  root: GraphNode;
}

/** More than this many children and the graph gets a summary bar. */
export const SUMMARY_THRESHOLD = 15;

const API = '/api/v1';

/**
 * Loads every available month once and serves the explorer from memory.
 *
 * All months are fetched as `flow=both&mode=delta`: the expense subtree
 * of a `both` response is byte-identical to a `flow=expense` response,
 * and `delta` is purely additive. So one request per month covers all
 * six flow/mode combinations, the flow and mode toggles cost nothing,
 * and dragging the slider never touches the network - which is the point
 * (a request per slider step stutters on a projector).
 */
@Service()
export class Graph {
  readonly month = signal<string | null>(null);
  readonly flow = signal<GraphFlow>('expense');
  readonly mode = signal<GraphMode>('absolute');

  private readonly monthsResource = httpResource<{ months: string[]; default: string | null }>(
    () => `${API}/graph/months`,
  );

  readonly months = computed(() =>
    this.monthsResource.hasValue() ? this.monthsResource.value().months : [],
  );

  private readonly cache = signal(new Map<string, GraphResponse>());
  /** Plain Set, not a signal: this only dedupes in-flight requests and
      must not make anything reading it reactive. */
  private readonly inFlight = new Set<string>();

  constructor() {
    // Depends on the month list and nothing else. `preload` writes to the
    // cache, so reading the cache inside a tracked effect would retrigger
    // it on every write - once per month, compounding.
    effect(() => {
      const months = this.months();
      if (months.length) untracked(() => void this.preload());
    });
  }

  /** The month actually shown: the chosen one, else the newest available. */
  readonly activeMonth = computed(() => {
    const months = this.months();
    const chosen = this.month();
    return chosen && months.includes(chosen) ? chosen : (months.at(-1) ?? null);
  });

  readonly response = computed(() => {
    const month = this.activeMonth();
    return month ? (this.cache().get(month) ?? null) : null;
  });

  readonly isLoading = computed(() => this.months().length > 0 && !this.response());

  /** Delta needs three preceding months; the first ones in the file have none. */
  readonly deltaAvailable = computed(() => (this.response()?.baseline_months.length ?? 0) >= 3);

  readonly baselineLabel = computed(() => this.response()?.baseline_label ?? null);

  /**
   * The subtree the chosen flow asks for. `both` keeps the virtual root
   * so the two flow circles sit side by side and their areas compare
   * directly; a single flow drops it and packs that flow alone.
   */
  readonly tree = computed<GraphNode | null>(() => {
    const root = this.response()?.root;
    if (!root) return null;
    const flow = this.flow();
    if (flow === 'both') return root;
    return (root.children ?? []).find((child) => child.flow === flow) ?? null;
  });

  /** Fetches every month once, as soon as the month list arrives. */
  private async preload(): Promise<void> {
    await Promise.all(untracked(() => this.months()).map((month) => this.load(month)));
  }

  private async load(month: string): Promise<void> {
    if (this.inFlight.has(month)) return;
    this.inFlight.add(month);
    try {
      const response = await fetch(`${API}/graph?month=${month}&flow=both&mode=delta`);
      if (!response.ok) return;
      const body: GraphResponse = await response.json();
      this.cache.update((cache) => new Map(cache).set(month, body));
    } catch {
      this.inFlight.delete(month);
    }
  }
}

/** Depth-first search for a node id, used by the breadcrumb and focus. */
export function findNode(root: GraphNode, id: string): GraphNode | null {
  if (root.id === id) return root;
  for (const child of root.children ?? []) {
    const found = findNode(child, id);
    if (found) return found;
  }
  return null;
}

/** Root-to-node path, so the breadcrumb can name every level above focus. */
export function pathTo(root: GraphNode, id: string): GraphNode[] {
  if (root.id === id) return [root];
  for (const child of root.children ?? []) {
    const path = pathTo(child, id);
    if (path.length) return [root, ...path];
  }
  return [];
}
