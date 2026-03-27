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
  private rootNodeId: string | null = null;
  private userNavigated = false;
  private hasAutoFit = false;
  private ready = false;
  private pendingNodes: GraphNode[] = [];
  private pendingEdges: GraphEdge[] = [];

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
      autoResize: true,
      layout: {
        improvedLayout: true,
        hierarchical: {
          enabled: true,
          direction: 'LR',
          sortMethod: 'directed',
          shakeTowards: 'roots',
          levelSeparation: 180,
          nodeSpacing: 150,
          treeSpacing: 180,
          blockShifting: true,
          edgeMinimization: true,
          parentCentralization: true,
        },
      },
      physics: {
        enabled: true,
        solver: 'hierarchicalRepulsion',
        stabilization: { iterations: 180, fit: false },
        hierarchicalRepulsion: {
          nodeDistance: 180,
          springLength: 150,
          springConstant: 0.02,
          damping: 0.18,
          avoidOverlap: 1,
        },
      },
      nodes: {
        shape: 'dot',
        borderWidth: 2,
        borderWidthSelected: 3,
        margin: { top: 12, right: 12, bottom: 12, left: 12 },
        chosen: false,
        font: {
          color: '#FAFAFA',
          size: 13,
          face: 'Inter, system-ui, sans-serif',
          strokeWidth: 0,
        },
      },
      edges: {
        color: { color: '#4B5563', highlight: '#9CA3AF' },
        font: { color: '#9CA3AF', size: 11, strokeWidth: 0, face: 'Inter, system-ui, sans-serif' },
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
        width: 1.5,
        selectionWidth: 2,
        smooth: { enabled: true, type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.4 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 100,
        zoomView: true,
        dragView: true,
        navigationButtons: true,
        keyboard: { enabled: true, bindToWindow: false },
      },
    };

    this.network = new Network(
      this.container,
      { nodes: this.nodeDataSet, edges: this.edgeDataSet },
      options,
    );

    this.network.once('stabilizationIterationsDone', () => {
      this.fit(true);
      // Disable physics after the first layout so subsequent node additions
      // don't cause the graph to rearrange and visually "jump"
      this.network?.setOptions({ physics: { enabled: false } });
    });
    this.network.on('zoom', () => {
      this.userNavigated = true;
    });
    this.network.on('dragStart', () => {
      this.userNavigated = true;
    });

    this.ready = true;
    if (this.pendingNodes.length > 0) {
      this.addNodes(this.pendingNodes);
      this.pendingNodes = [];
    }
    if (this.pendingEdges.length > 0) {
      this.addEdges(this.pendingEdges);
      this.pendingEdges = [];
    }
  }

  addNodes(nodes: GraphNode[]): void {
    if (!this.ready || !this.nodeDataSet) {
      this.pendingNodes.push(...nodes);
      return;
    }

    // Clear empty state on first add
    const empty = this.container.querySelector('.graph-panel__empty');
    if (empty) empty.remove();

    if (!this.rootNodeId && nodes.length > 0) {
      this.rootNodeId = nodes[0].id;
    }

    const existing = new Set(this.nodeDataSet.getIds());
    const toAdd = nodes
      .filter((n) => !existing.has(n.id))
      .map((n) => ({
        ...n,
        mass: n.id === this.rootNodeId ? 2.4 : 1.2,
      }));

    if (toAdd.length > 0) {
      this.nodeDataSet.add(toAdd);
      this.nodeCount += toAdd.length;
      this.setCount(this.nodeCount);
      this.pulse();
    }
    this.updateStats();
    this.applyTreeLevels();
  }

  addEdges(edges: GraphEdge[]): void {
    if (!this.ready || !this.edgeDataSet) {
      this.pendingEdges.push(...edges);
      return;
    }

    const existing = new Set(this.edgeDataSet.getIds());
    const toAdd = edges
      .map((e) => ({ ...e, id: `${e.from}-${e.to}-${e.label}` }))
      .filter((e) => !existing.has(e.id));
    if (toAdd.length > 0) {
      this.edgeDataSet.add(toAdd);
      this.edgeCount += toAdd.length;
    }
    this.applyTreeLevels();
    this.updateStats();
  }

  clear(): void {
    this.nodeDataSet?.clear();
    this.edgeDataSet?.clear();
    this.pendingNodes = [];
    this.pendingEdges = [];
    this.nodeCount = 0;
    this.edgeCount = 0;
    this.rootNodeId = null;
    this.userNavigated = false;
    this.hasAutoFit = false;
    this.setCount(0);
    this.updateStats();
  }

  private fit(force = false): void {
    if (!this.network) return;
    // Only auto-fit once (the first batch) — repeated fit animations
    // during streaming look jarring. After the first fit, only fit
    // if explicitly forced (e.g., after stabilization) or userNavigated is false
    // and we haven't auto-fit yet.
    if (!force && (this.userNavigated || this.hasAutoFit)) return;

    this.network.fit({
      animation: { duration: 500, easingFunction: 'easeInOutQuad' },
      minZoomLevel: this.hasAutoFit ? 0.55 : 0.45,
      maxZoomLevel: 1.15,
    });
    this.hasAutoFit = true;
  }

  private applyTreeLevels(): void {
    if (!this.nodeDataSet || !this.rootNodeId) return;

    const nodeIds = this.nodeDataSet.getIds() as string[];
    const levels = new Map<string, number>([[this.rootNodeId, 0]]);
    const queue: string[] = [this.rootNodeId];

    while (queue.length > 0) {
      const current = queue.shift()!;
      const currentLevel = levels.get(current) ?? 0;
      const outgoing = this.edgeDataSet?.get({
        filter: (edge) => edge.from === current,
      }) ?? [];

      for (const edge of outgoing) {
        if (levels.has(edge.to)) continue;
        levels.set(edge.to, currentLevel + 1);
        queue.push(edge.to);
      }
    }

    const updates = nodeIds.map((id) => ({
      id,
      level: levels.get(id) ?? 1,
      mass: id === this.rootNodeId ? 2.4 : 1.2,
    }));

    this.nodeDataSet.update(updates);
    this.network?.setOptions({
      physics: {
        enabled: true,
        solver: 'hierarchicalRepulsion',
      },
    });
    this.network?.stabilize(80);
  }

  resetViewport(): void {
    this.userNavigated = false;
    this.fit(true);
  }

  private updateStats(): void {
    if (this.nodeCount === 0) {
      this.statsEl.textContent = '';
    } else {
      this.statsEl.textContent = `${this.nodeCount} entities · ${this.edgeCount} connections`;
    }
  }
}
