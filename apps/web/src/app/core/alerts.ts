import { httpResource } from '@angular/common/http';
import { Service, computed } from '@angular/core';

import { chf, chfExact } from './chart-theme';
import type { GraphNode } from './graph';

export type AlertType = 'duplicate_charge' | 'large_payment' | 'category_spike';
export type AlertSeverity = 'danger' | 'warning' | 'info';

export interface AlertDto {
  alert_id: string;
  type: AlertType;
  severity: AlertSeverity;
  date: string | null;
  month: string | null;
  merchant: string | null;
  category_main: string | null;
  category_sub: string | null;
  amount_chf: number;
  baseline_chf: number | null;
  count: number | null;
  booking_text: string | null;
  transaction_id: string | null;
  transaction_ids: string[];
}

const SEVERITY_RANK: Record<AlertSeverity, number> = { danger: 0, warning: 1, info: 2 };

export function worstSeverity(alerts: AlertDto[]): AlertSeverity {
  return alerts.reduce(
    (worst, alert) => (SEVERITY_RANK[alert.severity] < SEVERITY_RANK[worst] ? alert.severity : worst),
    'info' as AlertSeverity,
  );
}

const DATE = new Intl.DateTimeFormat('de-CH', { day: '2-digit', month: '2-digit' });

/** The "Warum sehe ich das?" sentence from the alerts spec - one plain
    sentence per alert, no score, no jargon. */
export function alertSentence(alert: AlertDto): string {
  const merchant = alert.merchant ?? 'unbekanntem Händler';
  switch (alert.type) {
    case 'duplicate_charge': {
      const day = alert.date ? ` am ${DATE.format(new Date(alert.date))}` : '';
      return `${alert.count ?? 2}× derselbe Betrag (${chfExact(alert.amount_chf)}) bei ${merchant}${day} – möglicherweise doppelt belastet.`;
    }
    case 'large_payment': {
      const baseline =
        alert.baseline_chf !== null ? ` – üblich sind ${chf(alert.baseline_chf)} in dieser Kategorie` : '';
      return `${chfExact(alert.amount_chf)} bei ${merchant}${baseline}.`;
    }
    case 'category_spike': {
      const label = alert.category_sub ?? alert.category_main ?? 'Kategorie';
      const baseline = alert.baseline_chf !== null ? ` statt üblich ${chf(alert.baseline_chf)}` : '';
      return `${label}: ${chf(alert.amount_chf)} in diesem Monat${baseline}.`;
    }
  }
}

/** Alert lookup tables for one month's graph tree. */
export interface NodeAlertIndex {
  /** Alerts a node shows as its own (ring + detail panel). */
  own: Map<string, AlertDto[]>;
  /** Every node with an alert at or beneath it - the "Nur
      Auffälligkeiten" filter keeps these and dims the rest. */
  subtree: Set<string>;
}

/**
 * Joins the alert list onto a graph tree, client-side (Sollstatus:
 * "einfachster Start"). Transaction leaves join exactly by id
 * (`Alert.transaction_id(s)` are `Transaction.id`s, which ARE the leaf
 * node ids); merchants aggregate their transactions' alerts; category
 * nodes carry the month's `category_spike` matched on the category
 * fields. Flow and root stay unmarked - a frame with a ring would claim
 * a meaning it doesn't have.
 */
export function buildAlertIndex(
  tree: GraphNode,
  byTransactionId: Map<string, AlertDto[]>,
  spikesByCategory: Map<string, AlertDto> | undefined,
): NodeAlertIndex {
  const own = new Map<string, AlertDto[]>();
  const subtree = new Set<string>();

  const walk = (node: GraphNode): AlertDto[] => {
    let collected: AlertDto[];
    if (!node.children?.length) {
      collected = node.node_type === 'transaction' ? (byTransactionId.get(node.id) ?? []) : [];
      if (collected.length) own.set(node.id, collected);
    } else {
      const seen = new Map<string, AlertDto>();
      for (const child of node.children) {
        for (const alert of walk(child)) seen.set(alert.alert_id, alert);
      }
      collected = [...seen.values()];
      const nodeAlerts =
        node.node_type === 'merchant' || node.node_type === 'merchant_group' ? [...collected] : [];
      if (node.node_type === 'category') {
        const spike = spikesByCategory?.get(`${node.category_main ?? ''}//${node.category_sub ?? ''}`);
        if (spike) {
          nodeAlerts.push(spike);
          collected = [...collected, spike];
        }
      }
      if (nodeAlerts.length) own.set(node.id, nodeAlerts);
    }
    if (collected.length) subtree.add(node.id);
    return collected;
  };

  walk(tree);
  return { own, subtree };
}

/**
 * One fetch for the whole app: alerts are computed eagerly at backend
 * startup and small, so both the Kategorien and the Prognose page slice
 * the same cached list locally instead of issuing `$filter` requests.
 */
@Service()
export class Alerts {
  private readonly resource = httpResource<{ value: AlertDto[] }>(() => ({
    url: '/api/v1/Alerts',
  }));

  readonly all = computed<AlertDto[]>(() =>
    this.resource.hasValue() ? this.resource.value().value : [],
  );

  /** tx-id -> alerts, spanning `transaction_id` and `transaction_ids`. */
  readonly byTransactionId = computed(() => {
    const map = new Map<string, AlertDto[]>();
    for (const alert of this.all()) {
      const ids = new Set(alert.transaction_ids);
      if (alert.transaction_id) ids.add(alert.transaction_id);
      for (const id of ids) {
        const existing = map.get(id);
        if (existing) existing.push(alert);
        else map.set(id, [alert]);
      }
    }
    return map;
  });

  /** month -> (`main//sub` -> spike alert). */
  readonly spikesByMonth = computed(() => {
    const map = new Map<string, Map<string, AlertDto>>();
    for (const alert of this.all()) {
      if (alert.type !== 'category_spike' || !alert.month) continue;
      const byCategory = map.get(alert.month) ?? new Map<string, AlertDto>();
      byCategory.set(`${alert.category_main ?? ''}//${alert.category_sub ?? ''}`, alert);
      map.set(alert.month, byCategory);
    }
    return map;
  });

  /** Alerts of one month, worst severity first, then newest first. */
  forMonth(month: string): AlertDto[] {
    return sortAlerts(
      this.all().filter((alert) => alert.month === month || alert.date?.startsWith(month)),
    );
  }

  /** Alerts from `fromMonth` (YYYY-MM, inclusive) on, worst first. */
  recent(fromMonth: string): AlertDto[] {
    return sortAlerts(this.all().filter((alert) => alertMonthOf(alert) >= fromMonth));
  }
}

export function alertMonthOf(alert: AlertDto): string {
  return alert.month ?? alert.date?.slice(0, 7) ?? '';
}

function sortAlerts(alerts: AlertDto[]): AlertDto[] {
  return [...alerts].sort(
    (a, b) =>
      SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
      (b.date ?? b.month ?? '').localeCompare(a.date ?? a.month ?? ''),
  );
}
