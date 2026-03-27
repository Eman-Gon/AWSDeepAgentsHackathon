import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { NODE_COLORS } from '@/config/constants';
import type { GraphNode, GraphEdge } from '@/types';

interface GlobeMarker {
  id: string;
  lat: number;
  lng: number;
  label: string;
  group: string;
  size: number;
  color: string;
}

interface GlobeArc {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  label: string;
  color: string;
}

// SF-area coordinates for entities (spread out for visibility)
const ENTITY_COORDS: Record<string, { lat: number; lng: number }> = {
  'company:recology':       { lat: 37.7505, lng: -122.3872 },   // Pier 96
  'person:paul_giusti':     { lat: 37.7849, lng: -122.4094 },   // Financial District
  'person:mike_sangiacomo': { lat: 37.7920, lng: -122.3980 },   // Embarcadero
  'contract:recology_main': { lat: 37.7793, lng: -122.4193 },   // City Hall
  'contract:recology_2':    { lat: 37.7750, lng: -122.4183 },   // Civic Center
  'address:pier96':         { lat: 37.7505, lng: -122.3872 },   // Pier 96
  'campaign:breed_2018':    { lat: 37.7830, lng: -122.4150 },   // City Hall area
  'campaign:peskin_2016':   { lat: 37.7980, lng: -122.4100 },   // North Beach
  'person:mohammed_nuru':   { lat: 37.7710, lng: -122.4050 },   // DPW offices
  'company:cleanscapes':    { lat: 37.7530, lng: -122.3900 },   // Near Pier 96
};

// Fallback coords for unknown entities (scatter around SF)
function getCoords(id: string): { lat: number; lng: number } {
  if (ENTITY_COORDS[id]) return ENTITY_COORDS[id];
  // Hash-based scatter around SF
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0;
  return {
    lat: 37.76 + (hash % 50) * 0.001,
    lng: -122.42 + ((hash >> 8) % 50) * 0.001,
  };
}

export class GlobePanel extends Panel {
  private container: HTMLElement;
  private globe: any = null;
  private markers: GlobeMarker[] = [];
  private arcs: GlobeArc[] = [];
  private statsEl: HTMLElement;
  private initialized = false;

  constructor() {
    super({
      id: 'globe-panel',
      title: 'Entity Globe',
      className: 'globe-panel',
      showCount: true,
      trackActivity: true,
    });

    this.container = h('div', { className: 'globe-panel__canvas' });
    this.content.appendChild(this.container);

    // Legend
    const legend = h('div', { className: 'graph-panel__legend' });
    const groups: Record<string, string> = {
      person: 'Person', company: 'Company', contract: 'Contract',
      campaign: 'Campaign', address: 'Address',
    };
    for (const [group, label] of Object.entries(groups)) {
      const item = h('div', { className: 'graph-panel__legend-item' });
      const dot = h('span', { className: 'graph-panel__legend-dot' });
      dot.style.backgroundColor = NODE_COLORS[group].background;
      item.appendChild(dot);
      item.appendChild(h('span', {}, label));
      legend.appendChild(item);
    }
    this.el.appendChild(legend);

    // Stats
    this.statsEl = h('div', { className: 'graph-panel__stats' });
    this.el.appendChild(this.statsEl);

    this.initGlobe();
  }

  private async initGlobe(): Promise<void> {
    const GlobeModule = await import('globe.gl');
    const Globe = GlobeModule.default;

    this.globe = new Globe(this.container)
      .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg')
      .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png')
      .backgroundImageUrl('')
      .backgroundColor('#09090b')
      .atmosphereColor('#4466cc')
      .atmosphereAltitude(0.18)
      .showGraticules(false)
      // HTML markers
      .htmlElementsData([])
      .htmlLat((d: object) => (d as GlobeMarker).lat)
      .htmlLng((d: object) => (d as GlobeMarker).lng)
      .htmlAltitude(0.01)
      .htmlElement((d: object) => this.buildMarker(d as GlobeMarker))
      // Arcs for connections
      .arcsData([])
      .arcStartLat((d: object) => (d as GlobeArc).startLat)
      .arcStartLng((d: object) => (d as GlobeArc).startLng)
      .arcEndLat((d: object) => (d as GlobeArc).endLat)
      .arcEndLng((d: object) => (d as GlobeArc).endLng)
      .arcColor((d: object) => (d as GlobeArc).color)
      .arcLabel((d: object) => (d as GlobeArc).label)
      .arcDashLength(0.6)
      .arcDashGap(0.3)
      .arcDashAnimateTime(2000)
      .arcStroke(0.5);

    // Camera: start zoomed into SF
    const controls = this.globe.controls();
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.3;
    controls.enablePan = false;
    controls.minDistance = 101;
    controls.maxDistance = 600;
    controls.zoomSpeed = 1.4;

    // Point at SF
    this.globe.pointOfView({ lat: 37.77, lng: -122.42, altitude: 1.8 }, 0);

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (this.container.clientWidth > 0 && this.container.clientHeight > 0) {
        this.globe.width(this.container.clientWidth);
        this.globe.height(this.container.clientHeight);
      }
    });
    ro.observe(this.container);

    this.initialized = true;
  }

  private buildMarker(d: GlobeMarker): HTMLElement {
    const el = document.createElement('div');
    el.className = 'globe-marker';
    el.style.width = `${d.size}px`;
    el.style.height = `${d.size}px`;
    el.style.backgroundColor = d.color;
    el.style.borderRadius = '50%';
    el.style.border = '2px solid rgba(255,255,255,0.6)';
    el.style.cursor = 'pointer';
    el.style.transition = 'transform 0.3s ease';
    el.style.animation = 'marker-pop 0.4s ease-out';
    el.title = d.label;

    // Pulse ring for critical entities
    if (d.group === 'person' || d.group === 'company') {
      const ring = document.createElement('div');
      ring.className = 'globe-marker__ring';
      ring.style.position = 'absolute';
      ring.style.inset = '-4px';
      ring.style.borderRadius = '50%';
      ring.style.border = `1px solid ${d.color}`;
      ring.style.animation = 'marker-pulse 2s ease-out infinite';
      ring.style.opacity = '0.6';
      el.style.position = 'relative';
      el.appendChild(ring);
    }

    el.addEventListener('mouseenter', () => { el.style.transform = 'scale(1.3)'; });
    el.addEventListener('mouseleave', () => { el.style.transform = 'scale(1)'; });

    return el;
  }

  addNodes(nodes: GraphNode[]): void {
    if (!this.initialized || !this.globe) return;

    const existingIds = new Set(this.markers.map((m) => m.id));

    for (const node of nodes) {
      if (existingIds.has(node.id)) continue;
      const coords = getCoords(node.id);
      this.markers.push({
        id: node.id,
        lat: coords.lat,
        lng: coords.lng,
        label: node.label,
        group: node.group,
        size: node.group === 'person' || node.group === 'company' ? 14 : 10,
        color: NODE_COLORS[node.group]?.background ?? '#6B7280',
      });
    }

    this.globe.htmlElementsData([...this.markers]);
    this.setCount(this.markers.length);
    this.pulse();
    this.updateStats();
  }

  addEdges(edges: GraphEdge[]): void {
    if (!this.initialized || !this.globe) return;

    for (const edge of edges) {
      const fromCoords = getCoords(edge.from);
      const toCoords = getCoords(edge.to);

      // Determine arc color based on label
      let color = 'rgba(75, 85, 99, 0.6)';
      if (edge.label.includes('DONATED') || edge.label.includes('GIFTED')) {
        color = 'rgba(239, 68, 68, 0.8)'; // red for money/gifts
      } else if (edge.label.includes('AWARDED') || edge.label.includes('APPROVED')) {
        color = 'rgba(234, 179, 8, 0.8)';  // gold for contracts
      } else if (edge.label.includes('OFFICER') || edge.label.includes('CEO')) {
        color = 'rgba(59, 130, 246, 0.8)';  // blue for org ties
      } else if (edge.label.includes('REGISTERED')) {
        color = 'rgba(107, 114, 128, 0.6)'; // gray for addresses
      }

      this.arcs.push({
        startLat: fromCoords.lat,
        startLng: fromCoords.lng,
        endLat: toCoords.lat,
        endLng: toCoords.lng,
        label: edge.label,
        color,
      });
    }

    this.globe.arcsData([...this.arcs]);
    this.updateStats();
  }

  flyToSF(): void {
    if (this.globe) {
      this.globe.pointOfView({ lat: 37.77, lng: -122.42, altitude: 0.15 }, 2000);
      // Stop auto-rotate when investigating
      const controls = this.globe.controls();
      controls.autoRotate = false;
    }
  }

  clear(): void {
    this.markers = [];
    this.arcs = [];
    if (this.globe) {
      this.globe.htmlElementsData([]);
      this.globe.arcsData([]);
    }
    this.setCount(0);
    this.updateStats();
  }

  private updateStats(): void {
    if (this.markers.length === 0) {
      this.statsEl.textContent = '';
    } else {
      this.statsEl.textContent = `${this.markers.length} entities · ${this.arcs.length} connections`;
    }
  }
}
