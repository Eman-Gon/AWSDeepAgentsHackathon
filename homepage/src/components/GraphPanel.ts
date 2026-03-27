import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { NODE_COLORS } from '@/config/constants';
import type { GraphNode, GraphEdge } from '@/types';
import type { Network } from 'vis-network';
import type { DataSet } from 'vis-data';

const GROUP_LABELS: Record<string, string> = {
  person: 'Person',
  company: 'Company',
  contract: 'Contract',
  campaign: 'Campaign',
  address: 'Address',
};

export class GraphPanel extends Panel {
  private container: HTMLElement;
  private network: Network | null = null;
  private nodeDataSet: DataSet<GraphNode> | null = null;
  private edgeDataSet: DataSet<GraphEdge & { id: string }> | null = null;
  private statsEl: HTMLElement;
  private nodeCount = 0;
  private edgeCount = 0;

  constructor() {
    super({
      id: 'graph-panel',
      title: 'Entity Graph',
      className: 'graph-panel',
      showCount: true,
      trackActivity: true,
    });

    this.container = h('div', { className: 'graph-panel__canvas' });
    this.content.appendChild(this.container);

    // Empty state
    const empty = h('div', { className: 'graph-panel__empty' });
    empty.innerHTML = `
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.3;margin-bottom:8px">
        <path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/>
      </svg>
      <span>Entity graph will appear here</span>
    `;
    this.container.appendChild(empty);

    // Legend
    const legend = h('div', { className: 'graph-panel__legend' });
    for (const [group, color] of Object.entries(NODE_COLORS)) {
      const item = h('div', { className: 'graph-panel__legend-item' });
      const dot = h('span', { className: 'graph-panel__legend-dot' });
      dot.style.backgroundColor = color.background;
      item.appendChild(dot);
      item.appendChild(h('span', {}, GROUP_LABELS[group] ?? group));
      legend.appendChild(item);
    }
    this.el.appendChild(legend);

    // Stats bar
    this.statsEl = h('div', { className: 'graph-panel__stats' });
    this.el.appendChild(this.statsEl);

    this.initNetwork();
  }

  private async initNetwork(): Promise<void> {
    const { DataSet } = await import('vis-data');
    const { Network } = await import('vis-network');

    this.nodeDataSet = new DataSet<GraphNode>();
    this.edgeDataSet = new DataSet<GraphEdge & { id: string }>();

    const options = {
      physics: {
        stabilization: { iterations: 100 },
        barnesHut: {
          gravitationalConstant: -3000,
          centralGravity: 0.2,
          springLength: 150,
          springConstant: 0.04,
          damping: 0.09,
        },
      },
      edges: {
        color: { color: '#4B5563', highlight: '#9CA3AF' },
        font: { color: '#9CA3AF', size: 11, strokeWidth: 0, face: 'Inter, system-ui, sans-serif' },
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
        smooth: { enabled: true, type: 'continuous', roundness: 0.5 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 100,
        zoomView: true,
        dragView: true,
      },
    };

    this.network = new Network(
      this.container,
      { nodes: this.nodeDataSet, edges: this.edgeDataSet },
      options,
    );
  }

  addNodes(nodes: GraphNode[]): void {
    if (!this.nodeDataSet) return;

    // Clear empty state on first add
    const empty = this.container.querySelector('.graph-panel__empty');
    if (empty) empty.remove();

    const existing = new Set(this.nodeDataSet.getIds());
    const toAdd = nodes.filter((n) => !existing.has(n.id));
    if (toAdd.length > 0) {
      this.nodeDataSet.add(toAdd);
      this.nodeCount += toAdd.length;
      this.setCount(this.nodeCount);
      this.pulse();
    }
    this.updateStats();
    this.fit();
  }

  addEdges(edges: GraphEdge[]): void {
    if (!this.edgeDataSet) return;

    const existing = new Set(this.edgeDataSet.getIds());
    const toAdd = edges
      .map((e) => ({ ...e, id: `${e.from}-${e.to}-${e.label}` }))
      .filter((e) => !existing.has(e.id));
    if (toAdd.length > 0) {
      this.edgeDataSet.add(toAdd);
      this.edgeCount += toAdd.length;
    }
    this.updateStats();
  }

  clear(): void {
    this.nodeDataSet?.clear();
    this.edgeDataSet?.clear();
    this.nodeCount = 0;
    this.edgeCount = 0;
    this.setCount(0);
    this.updateStats();
  }

  private fit(): void {
    if (this.network) {
      this.network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
    }
  }

  private updateStats(): void {
    if (this.nodeCount === 0) {
      this.statsEl.textContent = '';
    } else {
      this.statsEl.textContent = `${this.nodeCount} entities · ${this.edgeCount} connections`;
    }
  }
}
