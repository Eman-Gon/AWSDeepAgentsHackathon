import { SearchPanel } from '@/components/SearchPanel';
import { GlobePanel } from '@/components/GlobePanel';
import { GraphPanel } from '@/components/GraphPanel';
import { NarrativePanel } from '@/components/NarrativePanel';
import { DEMO_INVESTIGATION } from '@/services/mock-data';
import type { InvestigationStatus } from '@/types';

export class App {
  private searchPanel: SearchPanel;
  private globePanel: GlobePanel;
  private graphPanel: GraphPanel;
  private narrativePanel: NarrativePanel;
  private status: InvestigationStatus = 'idle';
  private aborted = false;

  constructor(root: HTMLElement) {
    this.searchPanel = new SearchPanel((query) => this.investigate(query));
    this.globePanel = new GlobePanel();
    this.graphPanel = new GraphPanel();
    this.narrativePanel = new NarrativePanel();

    // Mount into layout
    const searchRow = root.querySelector('#search-row') as HTMLElement;
    const globeArea = root.querySelector('#globe-area') as HTMLElement;
    const graphArea = root.querySelector('#graph-area') as HTMLElement;
    const mainRight = root.querySelector('#main-right') as HTMLElement;

    this.searchPanel.mount(searchRow);
    this.globePanel.mount(globeArea);
    this.graphPanel.mount(graphArea);
    this.narrativePanel.mount(mainRight);
  }

  private async investigate(query: string): Promise<void> {
    if (this.status === 'running') {
      this.aborted = true;
    }
    this.aborted = false;

    this.setStatus('running');
    this.globePanel.clear();
    this.graphPanel.clear();
    this.narrativePanel.clear();
    this.searchPanel.setDisabled(true);

    // Fly globe into SF
    this.globePanel.flyToSF();

    const steps = DEMO_INVESTIGATION;

    for (let i = 0; i < steps.length; i++) {
      if (this.aborted) break;
      const step = steps[i];

      if (step.delay > 0) {
        this.narrativePanel.showTyping();
        await this.sleep(step.delay);
        this.narrativePanel.hideTyping();
      }

      if (this.aborted) break;

      this.narrativePanel.addStep(step, i);

      if (step.nodes && step.nodes.length > 0) {
        this.globePanel.addNodes(step.nodes);
        this.graphPanel.addNodes(step.nodes);
      }
      if (step.edges && step.edges.length > 0) {
        this.globePanel.addEdges(step.edges);
        this.graphPanel.addEdges(step.edges);
      }
    }

    if (!this.aborted) {
      this.setStatus('complete');
    }
    this.searchPanel.setDisabled(false);
  }

  private setStatus(status: InvestigationStatus): void {
    this.status = status;
    this.narrativePanel.setStatus(status);
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
