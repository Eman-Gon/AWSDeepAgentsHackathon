import { h, type FunctionalComponent } from 'preact';
import { useEffect, useMemo, useRef } from 'preact/hooks';
import { useAuth0 } from '@auth0/auth0-react';
import { SearchPanel } from '@/components/SearchPanel';
import { GlobePanel } from '@/components/GlobePanel';
import { GraphPanel } from '@/components/GraphPanel';
import { NarrativePanel } from '@/components/NarrativePanel';
import { EntitiesPanel } from '@/components/EntitiesPanel';
import { FindingsPanel } from '@/components/FindingsPanel';
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

export function AuthenticatedApp() {
  const {
    isAuthenticated,
    isLoading,
    loginWithRedirect,
    logout,
    user,
    getAccessTokenSilently,
  } = useAuth0();

  const session = useMemo(() => buildSession(user as Record<string, unknown> | undefined), [user]);
  const authError = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get('error');
    const description = params.get('error_description');
    if (!error) return '';
    return description ? `${error}: ${description}` : error;
  }, []);

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
        authError
          ? h('p', { className: 'auth-shell__error' }, authError)
          : null,
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

export function AppWithBypass() {
  const session: AuthSession = {
    isAuthenticated: true,
    userName: 'Hackathon Demo',
    email: 'demo@commons.local',
    roles: ['journalist'],
    isHuman: true,
    permissions: {
      canInvestigate: true,
      canPublish: false,
    },
  };

  return h(DashboardMount, {
    auth: {
      session,
      logout: () => window.location.reload(),
      getAccessToken: async () => {
        throw new Error('Dev bypass is enabled. No Auth0 token is available.');
      },
    },
  });
}

export const App: FunctionalComponent<{ devBypass?: boolean }> = ({ devBypass }) => {
  if (devBypass) {
    return h(AppWithBypass, {});
  }

  return h(AuthenticatedApp, {});
};

function DashboardMount({ auth }: { auth: DashboardAuthBridge }) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!rootRef.current) return;
    rootRef.current.innerHTML = '';
    new DashboardApp(rootRef.current, auth);
  }, [auth]);

  return h('div', { ref: rootRef, style: 'display:flex;flex-direction:column;flex:1;min-height:0;height:100%' });
}

class DashboardApp {
  private searchPanel: SearchPanel;
  private globePanel: GlobePanel;
  private graphPanel: GraphPanel;
  private narrativePanel: NarrativePanel;
  private entitiesPanel: EntitiesPanel;
  private findingsPanel: FindingsPanel;
  private auth: DashboardAuthBridge;
  private session: AuthSession;
  private status: InvestigationStatus = 'idle';
  private aborted = false;
  private abortController: AbortController | null = null;
  private entityCount = 0;
  private connectionCount = 0;
  private patternCount = 0;
  private findings: PatternAlert[] = [];

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
          <div id="entities-area" class="right-section right-section--entities"></div>
          <div id="findings-area" class="right-section right-section--findings"></div>
        </div>
      </div>
    `;

    this.searchPanel = new SearchPanel((query) => this.investigate(query), this.session.permissions.canInvestigate);
    this.globePanel = new GlobePanel();
    this.graphPanel = new GraphPanel();
    this.narrativePanel = new NarrativePanel();
    this.entitiesPanel = new EntitiesPanel();
    this.findingsPanel = new FindingsPanel(() => void this.publishFindings(), this.session.permissions.canPublish);

    const searchArea = root.querySelector('#search-area') as HTMLElement;
    this.searchPanel.mount(searchArea);

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
    const entitiesArea = root.querySelector('#entities-area') as HTMLElement;
    const findingsArea = root.querySelector('#findings-area') as HTMLElement;
    this.narrativePanel.mount(timelineArea);
    this.entitiesPanel.mount(entitiesArea);
    this.findingsPanel.mount(findingsArea);

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
    this.globePanel.clear();
    this.graphPanel.clear();
    this.narrativePanel.clear();
    this.entitiesPanel.clear();
    this.findingsPanel.clear();
    this.entityCount = 0;
    this.connectionCount = 0;
    this.patternCount = 0;
    this.findings = [];
    this.updatePills();
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
            this.entitiesPanel.addNodes(step.nodes);
            this.entityCount += step.nodes.length;
            this.updatePills();
          }
          if (step.edges && step.edges.length > 0) {
            this.globePanel.addEdges(step.edges);
            this.graphPanel.addEdges(step.edges);
            this.entitiesPanel.addEdges(step.edges);
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
        },
        this.abortController.signal,
      );

      // If the stream completed but yielded zero steps (e.g., Vercel
      // placeholder returned JSON instead of SSE), fall back to mock data
      if (stepIndex === 0 && !this.aborted) {
        console.warn('[commons] Stream returned zero steps, falling back to demo data');
        await this.investigateWithMockData(stepIndex);
      }
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
        this.entitiesPanel.addNodes(step.nodes);
        this.entityCount += step.nodes.length;
        this.updatePills();
      }
      if (step.edges && step.edges.length > 0) {
        this.globePanel.addEdges(step.edges);
        this.graphPanel.addEdges(step.edges);
        this.entitiesPanel.addEdges(step.edges);
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
