import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { escapeHtml } from '@/utils/sanitize';
import { NODE_COLORS } from '@/config/constants';
import type { GraphNode, GraphEdge } from '@/types';

type RiskLevel = 'high' | 'medium' | 'low';

const RISK_CONFIG: Record<RiskLevel, { label: string; color: string; bg: string }> = {
  high:   { label: 'High Risk',   color: '#f87171', bg: 'rgba(239,68,68,0.12)' },
  medium: { label: 'Medium Risk', color: '#facc15', bg: 'rgba(234,179,8,0.10)' },
  low:    { label: 'Low Risk',    color: '#9CA3AF', bg: 'rgba(156,163,175,0.08)' },
};

const GROUP_LABELS: Record<string, string> = {
  person: 'Person',
  company: 'Company',
  contract: 'Contract',
  campaign: 'Campaign',
  address: 'Address',
};

export class EntitiesPanel extends Panel {
  private listEl: HTMLElement;
  private emptyEl: HTMLElement;
  private nodes = new Map<string, GraphNode>();
  private edgeCounts = new Map<string, number>();

  constructor() {
    super({
      id: 'entities-panel',
      title: 'Entities',
      className: 'entities-panel',
      showCount: true,
      trackActivity: true,
    });

    this.emptyEl = h('div', { className: 'entities__empty' });
    this.emptyEl.innerHTML = '<p>Entities will appear here as the agent discovers them</p>';
    this.content.appendChild(this.emptyEl);

    this.listEl = h('div', { className: 'entities__list' });
    this.content.appendChild(this.listEl);
  }

  addNodes(nodes: GraphNode[]): void {
    for (const n of nodes) {
      if (this.nodes.has(n.id)) continue;
      this.nodes.set(n.id, n);
    }
    this.rebuild();
  }

  addEdges(edges: GraphEdge[]): void {
    for (const e of edges) {
      this.edgeCounts.set(e.from, (this.edgeCounts.get(e.from) ?? 0) + 1);
      this.edgeCounts.set(e.to, (this.edgeCounts.get(e.to) ?? 0) + 1);
    }
    this.rebuild();
  }

  clear(): void {
    this.nodes.clear();
    this.edgeCounts.clear();
    this.listEl.innerHTML = '';
    this.emptyEl.style.display = '';
    this.setCount(0);
  }

  private classifyRisk(node: GraphNode): RiskLevel {
    const connections = this.edgeCounts.get(node.id) ?? 0;
    // Campaigns and contracts with multiple links are higher risk
    if (node.group === 'campaign' || connections >= 4) return 'high';
    if (node.group === 'contract' || node.group === 'person' || connections >= 2) return 'medium';
    return 'low';
  }

  private rebuild(): void {
    if (this.nodes.size === 0) return;
    this.emptyEl.style.display = 'none';

    const grouped: Record<RiskLevel, GraphNode[]> = { high: [], medium: [], low: [] };
    for (const node of this.nodes.values()) {
      grouped[this.classifyRisk(node)].push(node);
    }

    this.listEl.innerHTML = '';

    for (const level of ['high', 'medium', 'low'] as RiskLevel[]) {
      const items = grouped[level];
      if (items.length === 0) continue;

      const config = RISK_CONFIG[level];
      const section = h('div', { className: `entities__group entities__group--${level}` });

      const header = h('div', { className: 'entities__group-header' });
      const dot = h('span', { className: 'entities__risk-dot' });
      dot.style.backgroundColor = config.color;
      header.appendChild(dot);
      header.appendChild(h('span', { className: 'entities__risk-label' }, config.label));
      header.appendChild(h('span', { className: 'entities__risk-count' }, String(items.length)));
      section.appendChild(header);

      for (const node of items) {
        const row = h('div', { className: 'entities__item' });
        const nodeColor = NODE_COLORS[node.group];
        const typeDot = h('span', { className: 'entities__type-dot' });
        typeDot.style.backgroundColor = nodeColor?.background ?? '#6B7280';
        row.appendChild(typeDot);

        const info = h('div', { className: 'entities__item-info' });
        info.appendChild(h('span', { className: 'entities__item-name' }, escapeHtml(node.label)));
        const conns = this.edgeCounts.get(node.id) ?? 0;
        const meta = `${GROUP_LABELS[node.group] ?? node.group}${conns > 0 ? ` · ${conns} connections` : ''}`;
        info.appendChild(h('span', { className: 'entities__item-meta' }, meta));
        row.appendChild(info);

        section.appendChild(row);
      }

      this.listEl.appendChild(section);
    }

    this.setCount(this.nodes.size);
    this.pulse();
  }
}
