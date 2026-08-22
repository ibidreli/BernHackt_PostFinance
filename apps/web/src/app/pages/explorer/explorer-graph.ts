import { Component, computed, effect, input, model, output, signal } from '@angular/core';
import { hierarchy, pack, type HierarchyCircularNode } from 'd3-hierarchy';

import { chf } from '../../core/chart-theme';
import type { GraphMode, GraphNode } from '../../core/graph';

/** viewBox units. The SVG scales to its container, so this is arbitrary. */
const SIZE = 1000;

/**
 * Hues per top-level expense category. Fixed rather than generated so a
 * category keeps its colour across months - a palette that reshuffles
 * when the data changes is worse than no palette.
 */
const EXPENSE_HUES: Record<string, number> = {
  Wohnen: 24,
  Einkaufen: 275,
  Freizeit: 340,
  Mobilität: 210,
  Finanzen: 45,
  Gesundheit: 0,
  Bildung: 300,
  Versicherungen: 190,
};
const FALLBACK_HUES = [15, 60, 100, 130, 165, 200, 240, 260, 290, 320];
/** Income keeps the teal-green band to itself so the two flows never mix up. */
const INCOME_HUE = 158;

/** viewBox units - a circle below this can't hold readable text. */
const LABEL_MIN_R = 70;
const AMOUNT_MIN_R = 105;
/** Rough glyph width as a share of the font size - enough to tell
    whether a label fits inside its circle without measuring text. */
const GLYPH_WIDTH = 0.56;

/** Categories arrive as "Einkaufen // Supermärkte"; inside a circle the
    leaf half is the informative one and the parent is in the breadcrumb. */
function displayLabel(node: GraphNode): string {
  if (node.node_type === 'category') return node.category_sub ?? node.category_main ?? node.label;
  return node.label;
}

interface PackedNode {
  id: string;
  data: GraphNode;
  x: number;
  y: number;
  r: number;
  depth: number;
  fill: string;
  label: string;
  labelY: number;
  amount: string;
  showLabel: boolean;
  showAmount: boolean;
  fontSize: number;
  isLeaf: boolean;
}

function hueFor(node: HierarchyCircularNode<GraphNode>): number | null {
  // The root and the two flow circles are frames, not categories - giving
  // them a hue would claim a meaning they don't have, and a green
  // "Ausgaben" circle reads as income.
  if (node.data.node_type === 'root' || node.data.node_type === 'flow') return null;
  if (node.data.flow === 'income') return INCOME_HUE;
  const category = node.ancestors().find((a) => a.data.node_type === 'category')?.data;
  const name = category?.category_main ?? category?.label ?? node.data.label;
  if (EXPENSE_HUES[name] !== undefined) return EXPENSE_HUES[name];
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) % 997;
  return FALLBACK_HUES[hash % FALLBACK_HUES.length];
}

/** Nearest ancestor carrying a delta - leaves have none of their own. */
function deltaOf(node: HierarchyCircularNode<GraphNode>) {
  return node.ancestors().find((a) => a.data.delta)?.data.delta ?? null;
}

@Component({
  selector: 'app-explorer-graph',
  templateUrl: './explorer-graph.html',
  styleUrl: './explorer-graph.css',
  host: { '[style.--transition-ms.ms]': 'durationMs()' },
})
export class ExplorerGraph {
  readonly tree = input.required<GraphNode>();
  readonly mode = input<GraphMode>('absolute');
  readonly dark = input(false);
  /** Two-way, so the breadcrumb outside can drive the zoom too. */
  readonly focusId = model<string | null>(null);
  readonly selectedId = input<string | null>(null);
  readonly leafSelected = output<GraphNode>();

  /** Zoom and slider transitions have different pacing, and both run
      through the same CSS property - so the last interaction picks. */
  private readonly lastInteraction = signal<'zoom' | 'data'>('data');
  protected readonly durationMs = computed(() => (this.lastInteraction() === 'zoom' ? 750 : 500));

  protected readonly size = SIZE;

  private readonly layout = computed(() => {
    const root = hierarchy<GraphNode>(this.tree(), (node) => node.children ?? undefined)
      // Only leaves contribute: containers already carry the sum, and
      // adding both would double-count. Area therefore tracks francs,
      // not booking count - rent is 12 bookings and CHF 21'840, the
      // canteen 121 bookings and CHF 1'616.
      .sum((node) => (node.children?.length ? 0 : Math.max(node.amount_chf, 0)))
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    return pack<GraphNode>().size([SIZE, SIZE]).padding(3)(root);
  });

  private readonly focus = computed(() => {
    const packed = this.layout();
    const id = this.focusId();
    return (id && packed.descendants().find((node) => node.data.id === id)) || packed;
  });

  protected readonly nodes = computed<PackedNode[]>(() => {
    const packed = this.layout();
    const focus = this.focus();
    const mode = this.mode();
    const dark = this.dark();
    const k = SIZE / (focus.r * 2);

    // Only the focused subtree plus the ancestors that frame it. Pack
    // circles never overlap, but at zoom the siblings of the focus crowd
    // into the viewport and paint over it - hiding them is what makes a
    // zoomed level readable.
    const inFocus = new Set(focus.descendants().map((node) => node.data.id));
    for (const ancestor of focus.ancestors()) inFocus.add(ancestor.data.id);

    return packed
      .descendants()
      .filter((node) => inFocus.has(node.data.id))
      // Shallow first, so a child always paints over its parent.
      .sort((a, b) => a.depth - b.depth)
      .map((node) => {
      const r = node.r * k;
      const isLeaf = !node.data.children?.length;
      // Inside a merchant circle every leaf repeats the merchant name;
      // the amount is the only thing that differs, so show that instead.
      const parentLabel = node.parent ? displayLabel(node.parent.data) : null;
      const own = displayLabel(node.data);
      const label = isLeaf && own === parentLabel ? chf(node.data.amount_chf) : own;
      const fontSize = r > 150 ? 30 : 22;
      const fits = label.length * fontSize * GLYPH_WIDTH < r * 1.85;
      return {
        id: node.data.id,
        data: node.data,
        x: (node.x - focus.x) * k + SIZE / 2,
        y: (node.y - focus.y) * k + SIZE / 2,
        r,
        depth: node.depth,
        fill: mode === 'delta' ? this.deltaFill(node, dark) : this.absoluteFill(node, dark),
        label,
        // A container's label rides near its top edge; centred, it lands
        // on top of the children it is supposed to name.
        labelY: (node.y - focus.y) * k + SIZE / 2 - (isLeaf ? 0 : r - fontSize * 1.3),
        amount: chf(node.data.amount_chf),
        // Only the ring directly below focus gets labels, and only where
        // the circle is actually big enough to hold one - deeper or
        // smaller ones overlap into noise.
        showLabel: node.depth === focus.depth + 1 && r > LABEL_MIN_R && fits,
        showAmount: !isLeaf && node.depth === focus.depth + 1 && r > AMOUNT_MIN_R && fits,
        fontSize,
        isLeaf,
      };
      });
  });

  private absoluteFill(node: HierarchyCircularNode<GraphNode>, dark: boolean): string {
    const hue = hueFor(node);
    if (hue === null) return dark ? 'hsl(200 8% 18%)' : 'hsl(200 12% 94%)';
    // Lightness steps with depth so a family reads as one family while
    // the nesting stays legible - inverted for the dark theme.
    const step = Math.min(node.depth, 4);
    const lightness = dark ? 26 + step * 9 : 88 - step * 11;
    return `hsl(${hue} 52% ${lightness}%)`;
  }

  private deltaFill(node: HierarchyCircularNode<GraphNode>, dark: boolean): string {
    if (node.data.node_type === 'root') return dark ? 'hsl(200 8% 18%)' : 'hsl(200 12% 94%)';
    const delta = deltaOf(node);
    if (!delta || delta.direction === 'neutral') return dark ? 'hsl(200 6% 30%)' : 'hsl(200 6% 86%)';
    // Direction, not the sign of diff_chf: more income is favourable,
    // more spending is not, and a raise must never glow red.
    const hue = delta.direction === 'favourable' ? 150 : 8;
    const intensity = Math.min(Math.abs(delta.diff_pct ?? 40), 100) / 100;
    const lightness = dark ? 22 + intensity * 26 : 90 - intensity * 34;
    return `hsl(${hue} ${40 + intensity * 30}% ${lightness}%)`;
  }

  constructor() {
    effect(() => {
      this.tree();
      this.lastInteraction.set('data');
    });
  }

  protected activate(node: PackedNode): void {
    if (node.isLeaf) {
      this.leafSelected.emit(node.data);
      return;
    }
    this.lastInteraction.set('zoom');
    this.focusId.set(node.id);
  }

  /** Background click zooms out one level. */
  protected zoomOut(): void {
    const focus = this.focus();
    this.lastInteraction.set('zoom');
    this.focusId.set(focus.parent ? focus.parent.data.id : null);
  }
}
