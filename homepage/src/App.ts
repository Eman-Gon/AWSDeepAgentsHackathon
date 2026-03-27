import { h } from 'preact';
import { useEffect, useMemo, useRef } from 'preact/hooks';
import { useAuth0 } from '@auth0/auth0-react';
import { SearchPanel } from '@/components/SearchPanel';
import { GlobePanel } from '@/components/GlobePanel';
import { GraphPanel } from '@/components/GraphPanel';
import { NarrativePanel } from '@/components/NarrativePanel';
import { FindingsPanel } from '@/components/FindingsPanel';
import { InvestigationsPanel } from '@/components/InvestigationsPanel';
import { TipsPanel } from '@/components/TipsPanel';
import { TipLineInfo } from '@/components/TipLineInfo';
import { h as dom } from '@/utils/dom-utils';
import { DEMO_INVESTIGATION } from '@/services/mock-data';
import { streamInvestigation } from '@/services/investigation-stream';
import { getAuth0Config } from '@/auth/auth-config';
import type { InvestigationStatus, PatternAlert } from '@/types';
import type { AuthSession, UserRole } from '@/auth/types';

interface DashboardAuthBridge {
  session: AuthSession;
  logout: () => void;
  getAccessToken: () => Promise<string>;
}

function getRoles(user: Record<string, unknown> | undefined): UserRole[] {
  if (!user) return [];
  const config = getAuth0Config();
  const namespacedRoles = user[`${config.claimsNamespace}/roles`];
  const roles = Array.isArray(namespacedRoles) ? namespacedRoles : [];
  const filtered = roles.filter((role): role is UserRole => role === 'journalist' || role === 'editor');
  // Default: every authenticated human is at least a journalist
  if (filtered.length === 0) filtered.push('journalist');
  return filtered;
}

function buildSession(user: Record<string, unknown> | undefined): AuthSession {
  const roles = getRoles(user);
  const canInvestigate = roles.includes('journalist') || roles.includes('editor');
  const canPublish = roles.includes('editor');

  return {
    isAuthenticated: true,
    userName: typeof user?.name === 'string'
      ? user.name
      : typeof user?.nickname === 'string'
        ? user.nickname
        : typeof user?.email === 'string'
          ? user.email
          : 'Authenticated User',
    email: typeof user?.email === 'string' ? user.email : '',
    roles,
    isHuman: true,
    permissions: {
      canInvestigate,
      canPublish,
    },
  };
}

export function App() {
  const {
    isAuthenticated,
    isLoading,
    loginWithRedirect,
    logout,
    user,
    getAccessTokenSilently,
  } = useAuth0();

  const session = useMemo(() => buildSession(user as Record<string, unknown> | undefined), [user]);

  if (isLoading) {
    return h('div', { className: 'auth-shell' },
      h('div', { className: 'auth-shell__card' },
        h('h1', {}, 'Loading Auth'),
        h('p', {}, 'Checking your Auth0 session before loading Commons.'),
      ),
    );
  }

  if (!isAuthenticated) {
    return h('div', { className: 'auth-shell' },
      h('div', { className: 'auth-shell__card' },
        h('h1', {}, 'Commons'),
        h('p', {}, 'Sign in to access the investigative dashboard.'),
        h('button', {
          className: 'auth-shell__button',
          onClick: () => void loginWithRedirect(),
        }, 'Sign In'),
      ),
    );
  }

  return h(DashboardMount, {
    auth: {
      session,
      logout: () => void logout({ logoutParams: { returnTo: window.location.origin } }),
      getAccessToken: async () => getAccessTokenSilently({
        authorizationParams: {
          ...(getAuth0Config().audience ? { audience: getAuth0Config().audience } : {}),
        },
      }),
    },
  });
}

function DashboardMount({ auth }: { auth: DashboardAuthBridge }) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!rootRef.current) return;
    rootRef.current.innerHTML = '';
    new DashboardApp(rootRef.current, auth);
  }, [auth]);

  return h('div', { ref: rootRef });
}

class DashboardApp {
  private searchPanel: SearchPanel;
  private globePanel: GlobePanel;
  private graphPanel: GraphPanel;
  private narrativePanel: NarrativePanel;
  private findingsPanel: FindingsPanel;
  private investigationsPanel: InvestigationsPanel;
  private tipsPanel: TipsPanel;
  private tipLineInfo: TipLineInfo;
  private auth: DashboardAuthBridge;
  private session: AuthSession;
  private status: InvestigationStatus = 'idle';
  private aborted = false;
  private abortController: AbortController | null = null;
  private entityCount = 0;
  private connectionCount = 0;
  private patternCount = 0;
  private findings: PatternAlert[] = [];
  private currentQuery = '';
  private collectedEntityIds: string[] = [];

  private pillEntities: HTMLElement;
  private pillConnections: HTMLElement;
  private pillPatterns: HTMLElement;

  constructor(root: HTMLElement, auth: DashboardAuthBridge) {
    this.auth = auth;
    this.session = auth.session;

    root.innerHTML = `
      <nav id="navbar" class="navbar">
        <div class="navbar__left">
          <div class="navbar__logo">C</div>
          <span class="navbar__name">Commons</span>
          <span class="navbar__divider"></span>
          <span class="navbar__tagline">Investigation Intelligence</span>
        </div>
        <div class="navbar__right">
          <div id="stat-pills" class="stat-pills"></div>
          <button class="navbar__signin">Sign Out</button>
        </div>
      </nav>

      <div id="search-area" class="search-area"></div>

      <div class="main">
        <div class="main__sidebar" id="investigations-sidebar">
          <div id="investigations-area"></div>
        </div>

        <div class="main__left">
          <div id="hero-viz" class="hero-viz">
            <div id="globe-area" class="hero-viz__globe"></div>
            <div id="graph-area" class="hero-viz__graph"></div>
            <div class="hero-viz__toggle" id="viz-toggle">
              <button class="hero-viz__tab hero-viz__tab--active" data-view="globe">Globe</button>
              <button class="hero-viz__tab" data-view="graph">Network</button>
            </div>
          </div>
        </div>

        <div class="main__right">
          <div id="timeline-area" class="right-section right-section--timeline"></div>
          <div id="bottom-tabs" class="bottom-tabs">
            <button class="bottom-tabs__tab bottom-tabs__tab--active" data-tab="findings">Findings</button>
            <button class="bottom-tabs__tab" data-tab="tips">Tip Line</button>
          </div>
          <div id="findings-area" class="right-section right-section--findings">
            <div id="save-bar" class="save-bar">
              <button id="save-investigation-btn" class="save-bar__btn" disabled>Save Investigation</button>
              <span id="save-feedback" class="save-bar__feedback"></span>
            </div>
          </div>
          <div id="tips-area" class="right-section right-section--findings" style="display:none"></div>
        </div>
      </div>
    `;

    this.searchPanel = new SearchPanel((query) => this.investigate(query), this.session.permissions.canInvestigate);
    this.globePanel = new GlobePanel();
    this.graphPanel = new GraphPanel();
    this.narrativePanel = new NarrativePanel();
    this.findingsPanel = new FindingsPanel(() => void this.publishFindings(), this.session.permissions.canPublish);
    this.investigationsPanel = new InvestigationsPanel({
      onLoad: (id) => void this.loadInvestigation(id),
      onOutcomeChange: (id, outcome) => void this.updateOutcome(id, outcome),
    });
    this.tipsPanel = new TipsPanel();
    this.tipLineInfo = new TipLineInfo();

    const searchArea = root.querySelector('#search-area') as HTMLElement;
    this.searchPanel.mount(searchArea);

    const investigationsArea = root.querySelector('#investigations-area') as HTMLElement;
    this.investigationsPanel.mount(investigationsArea);
    void this.investigationsPanel.refresh();

    const globeArea = root.querySelector('#globe-area') as HTMLElement;
    const graphArea = root.querySelector('#graph-area') as HTMLElement;
    this.globePanel.mount(globeArea);
    this.graphPanel.mount(graphArea);
    graphArea.style.display = 'none';

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

    const timelineArea = root.querySelector('#timeline-area') as HTMLElement;
    const findingsArea = root.querySelector('#findings-area') as HTMLElement;
    const tipsArea = root.querySelector('#tips-area') as HTMLElement;
    this.narrativePanel.mount(timelineArea);
    this.findingsPanel.mount(findingsArea);
    this.tipLineInfo.mount(tipsArea);
    this.tipsPanel.mount(tipsArea);

    // Bottom tabs: switch between Findings and Tip Line
    const bottomTabs = root.querySelector('#bottom-tabs') as HTMLElement;
    bottomTabs.addEventListener('click', (e) => {
      const btn = (e.target as HTMLElement).closest('.bottom-tabs__tab') as HTMLElement | null;
      if (!btn) return;
      const tab = btn.dataset.tab;
      bottomTabs.querySelectorAll('.bottom-tabs__tab').forEach((t) => t.classList.remove('bottom-tabs__tab--active'));
      btn.classList.add('bottom-tabs__tab--active');
      findingsArea.style.display = tab === 'findings' ? '' : 'none';
      tipsArea.style.display = tab === 'tips' ? '' : 'none';
    });

    // Fetch tips on load
    void this.tipsPanel.fetchTips();

    // Save investigation button
    const saveBtn = root.querySelector('#save-investigation-btn') as HTMLButtonElement;
    const saveFeedback = root.querySelector('#save-feedback') as HTMLElement;
    saveBtn.addEventListener('click', () => void this.saveInvestigation(saveBtn, saveFeedback));

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
    const pill = dom('div', { className: 'stat-pill' });
    pill.appendChild(dom('span', { className: 'stat-pill__value' }, value));
    pill.appendChild(dom('span', { className: 'stat-pill__label' }, label));
    return pill;
  }

  private updatePills(): void {
    this.pillEntities.querySelector('.stat-pill__value')!.textContent = String(this.entityCount);
    this.pillConnections.querySelector('.stat-pill__value')!.textContent = String(this.connectionCount);
    this.pillPatterns.querySelector('.stat-pill__value')!.textContent = String(this.patternCount);
  }

  private async investigate(query: string): Promise<void> {
    if (!this.session.permissions.canInvestigate) return;

    // Abort any in-progress investigation
    if (this.status === 'running') {
      this.aborted = true;
      this.abortController?.abort();
    }
    this.aborted = false;

    this.setStatus('running');
    this.currentQuery = query;
    this.collectedEntityIds = [];
    this.globePanel.clear();
    this.graphPanel.clear();
    this.narrativePanel.clear();
    this.findingsPanel.clear();
    this.entityCount = 0;
    this.connectionCount = 0;
    this.patternCount = 0;
    this.findings = [];
    this.updatePills();
    this.updateSaveButton(false);
    this.searchPanel.setDisabled(true);

    this.globePanel.flyToSF();

    // Create an AbortController so we can cancel the SSE stream
    // if the user starts a new investigation before this one finishes
    this.abortController = new AbortController();
    let stepIndex = 0;

    try {
      // Stream real investigation from the Python backend via SSE
      await streamInvestigation(
        query,
        (step) => {
          if (this.aborted) return;

          // Process each AgentStep exactly like the mock data loop did
          this.narrativePanel.addStep(step, stepIndex);
          stepIndex++;

          if (step.nodes && step.nodes.length > 0) {
            this.globePanel.addNodes(step.nodes);
            this.graphPanel.addNodes(step.nodes);
            this.entityCount += step.nodes.length;
            for (const n of step.nodes) this.collectedEntityIds.push(n.id);
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

          // US-012: Check for overlapping entities in prior investigations
          if (step.tool === 'search_entity' && step.nodes && step.nodes.length > 0) {
            this.checkPriorInvestigations(step.nodes.map(n => n.id));
          }
        },
        this.abortController.signal,
      );
    } catch (err) {
      // If the real backend is unavailable, fall back to mock data
      // so the demo still works without the Python server running
      if (!this.aborted) {
        console.warn('[commons] Backend unavailable, falling back to demo data:', err);
        await this.investigateWithMockData(stepIndex);
      }
    }

    if (!this.aborted) {
      this.setStatus('complete');
      this.updateSaveButton(true);
      void this.loadPatternConfidence();
    }
    this.searchPanel.setDisabled(false);
    this.findingsPanel.setPublishBusy(false);
  }

  /**
   * Fallback: play the mock investigation data when the Python backend
   * is unreachable. Preserves the demo experience for presentations.
   */
  private async investigateWithMockData(startIndex: number): Promise<void> {
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

      this.narrativePanel.addStep(step, startIndex + i);

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
  }

  // ── US-013: Save investigation ──────────────────────────────────────
  private async saveInvestigation(btn: HTMLButtonElement, feedback: HTMLElement): Promise<void> {
    if (this.findings.length === 0 && this.collectedEntityIds.length === 0) return;

    btn.disabled = true;
    btn.textContent = 'Saving...';
    feedback.textContent = '';

    try {
      const res = await fetch('/api/investigations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: this.currentQuery || 'Untitled Investigation',
          summary: `Investigation of "${this.currentQuery}" — found ${this.entityCount} entities, ${this.connectionCount} connections, ${this.patternCount} patterns.`,
          entity_ids: [...new Set(this.collectedEntityIds)],
          findings: this.findings,
        }),
      });

      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || 'Failed to save');

      feedback.textContent = `Saved as ${body.investigation_id}`;
      feedback.style.color = 'var(--green)';
      void this.investigationsPanel.refresh();
    } catch (err) {
      feedback.textContent = err instanceof Error ? err.message : 'Save failed';
      feedback.style.color = 'var(--red)';
      btn.disabled = false;
      btn.textContent = 'Save Investigation';
    }
  }

  private updateSaveButton(enabled: boolean): void {
    const btn = document.getElementById('save-investigation-btn') as HTMLButtonElement | null;
    const feedback = document.getElementById('save-feedback') as HTMLElement | null;
    if (btn) {
      btn.disabled = !enabled;
      btn.textContent = 'Save Investigation';
    }
    if (feedback) {
      feedback.textContent = '';
    }
  }

  // ── US-014: Update investigation outcome ──────────────────────────────
  private async updateOutcome(id: string, outcome: string): Promise<void> {
    try {
      await fetch(`/api/investigations/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ outcome }),
      });
    } catch {
      // Silently fail — the badge already updated optimistically
    }
  }

  // ── US-012: Load a prior investigation ────────────────────────────────
  private async loadInvestigation(id: string): Promise<void> {
    try {
      const res = await fetch(`/api/investigations/${id}`);
      if (!res.ok) return;
      const inv = await res.json();

      // Show the loaded investigation narrative
      this.narrativePanel.clear();
      this.narrativePanel.addStep({
        tool: 'file_investigation',
        message: `Loaded saved investigation: "${inv.title}"\n\n${inv.summary}`,
        delay: 0,
      }, 0);

      // Show findings if any
      this.findingsPanel.clear();
      if (inv.findings && inv.findings.length > 0) {
        for (const f of inv.findings) {
          this.findingsPanel.addPattern(f);
        }
        this.findings = inv.findings;
        this.patternCount = inv.findings.length;
        this.updatePills();
      }
    } catch {
      // Backend unavailable
    }
  }

  // ── US-012: Check for overlapping entities in prior investigations ────
  private checkPriorInvestigations(entityIds: string[]): void {
    const priorInvestigations = this.investigationsPanel.getInvestigations();
    if (priorInvestigations.length === 0) return;

    for (const inv of priorInvestigations) {
      const overlap = inv.entity_ids.filter(id => entityIds.includes(id));
      if (overlap.length > 0) {
        this.narrativePanel.addStep({
          tool: 'check_prior_investigations',
          message: `Prior investigation "${inv.title}" (${inv.outcome}) also flagged ${overlap.length} of these entities. This entity was previously investigated.`,
          delay: 0,
        }, -1);
        break;  // Only show the first match to avoid noise
      }
    }
  }

  // ── US-015/016: Load pattern confidence from historical outcomes ──────
  private async loadPatternConfidence(): Promise<void> {
    if (this.findings.length === 0) return;
    try {
      const res = await fetch('/api/pattern-confidence');
      if (!res.ok) return;
      const data = await res.json();
      if (data.total_investigations_with_outcomes === 0) return;

      // Annotate the narrative with confidence info
      const lines: string[] = [];
      for (const finding of this.findings) {
        const ptype = finding.type;
        const stats = data.patterns[ptype];
        if (stats && stats.total_occurrences > 0) {
          const pct = Math.round(stats.confidence_rate * 100);
          lines.push(`${ptype.replace(/_/g, ' ')}: ${pct}% confirmation rate (${stats.confirmed}/${stats.total_occurrences} prior cases)`);
        }
      }

      if (lines.length > 0) {
        this.narrativePanel.addStep({
          tool: 'get_pattern_confidence',
          message: `Historical pattern confidence from ${data.total_investigations_with_outcomes} prior investigations:\n${lines.join('\n')}`,
          delay: 0,
        }, -1);
      }
    } catch {
      // Confidence data unavailable
    }
  }

  private decorateNavbar(root: HTMLElement): void {
    const navRight = root.querySelector('.navbar__right') as HTMLElement | null;
    const signOutBtn = root.querySelector('.navbar__signin') as HTMLButtonElement | null;
    if (!navRight || !signOutBtn) return;

    const identity = dom('div', { className: 'navbar__identity' });
    identity.appendChild(dom('span', { className: 'navbar__identity-name' }, this.session.userName));
    identity.appendChild(dom('span', { className: 'navbar__identity-role' }, this.session.roles.join(', ') || 'viewer'));
    navRight.insertBefore(identity, signOutBtn);

    signOutBtn.addEventListener('click', () => this.auth.logout());
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
