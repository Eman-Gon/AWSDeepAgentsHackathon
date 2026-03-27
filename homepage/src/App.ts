import { SearchPanel } from '@/components/SearchPanel';
import { GlobePanel } from '@/components/GlobePanel';
import { GraphPanel } from '@/components/GraphPanel';
import { NarrativePanel } from '@/components/NarrativePanel';
import { FindingsPanel } from '@/components/FindingsPanel';
import { h } from '@/utils/dom-utils';
import { DEMO_INVESTIGATION } from '@/services/mock-data';
import type { InvestigationStatus, PatternAlert } from '@/types';
import type { AuthSession } from '@/auth/types';
import { CommonsAuthClient } from '@/auth/auth-client';

export class App {
  private searchPanel: SearchPanel;
  private globePanel: GlobePanel;
  private graphPanel: GraphPanel;
  private narrativePanel: NarrativePanel;
  private findingsPanel: FindingsPanel;
  private auth: CommonsAuthClient;
  private session: AuthSession;
  private status: InvestigationStatus = 'idle';
  private aborted = false;
  private entityCount = 0;
  private connectionCount = 0;
  private patternCount = 0;
  private findings: PatternAlert[] = [];

  // Stat pill elements
  private pillEntities: HTMLElement;
  private pillConnections: HTMLElement;
  private pillPatterns: HTMLElement;

  constructor(root: HTMLElement, auth: CommonsAuthClient, session: AuthSession) {
    this.auth = auth;
    this.session = session;
    this.searchPanel = new SearchPanel((query) => this.investigate(query), session.permissions.canInvestigate);
    this.globePanel = new GlobePanel();
    this.graphPanel = new GraphPanel();
    this.narrativePanel = new NarrativePanel();
    this.findingsPanel = new FindingsPanel(() => void this.publishFindings(), session.permissions.canPublish);

    // Mount search
    const searchArea = root.querySelector('#search-area') as HTMLElement;
    this.searchPanel.mount(searchArea);

    // Mount viz
    const globeArea = root.querySelector('#globe-area') as HTMLElement;
    const graphArea = root.querySelector('#graph-area') as HTMLElement;
    this.globePanel.mount(globeArea);
    this.graphPanel.mount(graphArea);

    // Default: show globe, hide graph
    graphArea.style.display = 'none';

    // Tab toggle
    const toggle = root.querySelector('#viz-toggle') as HTMLElement;
    toggle.addEventListener('click', (e) => {
      const btn = (e.target as HTMLElement).closest('.hero-viz__tab') as HTMLElement | null;
      if (!btn) return;
      const view = btn.dataset.view;
      toggle.querySelectorAll('.hero-viz__tab').forEach((t) => t.classList.remove('hero-viz__tab--active'));
      btn.classList.add('hero-viz__tab--active');
      if (view === 'globe') {
        globeArea.style.display = '';
        graphArea.style.display = 'none';
      } else {
        globeArea.style.display = 'none';
        graphArea.style.display = '';
      }
    });

    // Mount right panels
    const timelineArea = root.querySelector('#timeline-area') as HTMLElement;
    const findingsArea = root.querySelector('#findings-area') as HTMLElement;
    this.narrativePanel.mount(timelineArea);
    this.findingsPanel.mount(findingsArea);

    // Stat pills
    const pillsContainer = root.querySelector('#stat-pills') as HTMLElement;
    this.pillEntities = this.makePill('Entities', '0');
    this.pillConnections = this.makePill('Connections', '0');
    this.pillPatterns = this.makePill('Patterns', '0');
    pillsContainer.appendChild(this.pillEntities);
    pillsContainer.appendChild(this.pillConnections);
    pillsContainer.appendChild(this.pillPatterns);

    this.decorateNavbar(root);
  }

  private makePill(label: string, value: string): HTMLElement {
    const pill = h('div', { className: 'stat-pill' });
    pill.appendChild(h('span', { className: 'stat-pill__value' }, value));
    pill.appendChild(h('span', { className: 'stat-pill__label' }, label));
    return pill;
  }

  private updatePills(): void {
    this.pillEntities.querySelector('.stat-pill__value')!.textContent = String(this.entityCount);
    this.pillConnections.querySelector('.stat-pill__value')!.textContent = String(this.connectionCount);
    this.pillPatterns.querySelector('.stat-pill__value')!.textContent = String(this.patternCount);
  }

  private async investigate(query: string): Promise<void> {
    if (!this.session.permissions.canInvestigate) return;
    if (this.status === 'running') {
      this.aborted = true;
    }
    this.aborted = false;

    this.setStatus('running');
    this.globePanel.clear();
    this.graphPanel.clear();
    this.narrativePanel.clear();
    this.findingsPanel.clear();
    this.entityCount = 0;
    this.connectionCount = 0;
    this.patternCount = 0;
    this.findings = [];
    this.updatePills();
    this.searchPanel.setDisabled(true);

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
        this.entityCount += step.nodes.length;
        this.updatePills();
      }
      if (step.edges && step.edges.length > 0) {
        this.globePanel.addEdges(step.edges);
        this.graphPanel.addEdges(step.edges);
        this.connectionCount += step.edges.length;
        this.updatePills();
      }
      if (step.patterns && step.patterns.length > 0) {
        for (const p of step.patterns) {
          this.findingsPanel.addPattern(p);
          this.findings.push(p);
          this.patternCount++;
        }
        this.updatePills();
      }
    }

    if (!this.aborted) {
      this.setStatus('complete');
    }
    this.searchPanel.setDisabled(false);
    this.findingsPanel.setPublishBusy(false);
  }

  private decorateNavbar(root: HTMLElement): void {
    const navRight = root.querySelector('.navbar__right') as HTMLElement | null;
    const signInBtn = root.querySelector('.navbar__signin') as HTMLButtonElement | null;
    if (!navRight || !signInBtn) return;

    const identity = h('div', { className: 'navbar__identity' });
    identity.appendChild(h('span', { className: 'navbar__identity-name' }, this.session.userName));
    identity.appendChild(h('span', { className: 'navbar__identity-role' }, this.session.roles.join(', ') || 'viewer'));
    navRight.insertBefore(identity, signInBtn);

    signInBtn.textContent = 'Log Out';
    signInBtn.addEventListener('click', () => this.auth.logout());
  }

  private async publishFindings(): Promise<void> {
    if (!this.session.permissions.canPublish || this.findings.length === 0) return;

    this.findingsPanel.setPublishBusy(true);
    this.findingsPanel.setPublishFeedback('Publishing findings to the protected backend...');

    try {
      const accessToken = await this.auth.getAccessToken();
      const res = await fetch('/api/publish', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ findings: this.findings }),
      });

      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.error || 'Failed to publish findings');
      }

      this.findingsPanel.setPublishFeedback(`Published ${body.findingsCount} findings successfully.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to publish findings';
      this.findingsPanel.setPublishFeedback(message);
    } finally {
      this.findingsPanel.setPublishBusy(false);
    }
  }

  private setStatus(status: InvestigationStatus): void {
    this.status = status;
    this.narrativePanel.setStatus(status);
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
