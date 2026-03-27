import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { escapeHtml } from '@/utils/sanitize';
import { TOOL_ICONS, SEVERITY_COLORS } from '@/config/constants';
import type { AgentStep, PatternAlert, InvestigationStatus } from '@/types';

export class NarrativePanel extends Panel {
  private listEl: HTMLElement;
  private statusEl: HTMLElement;

  constructor() {
    super({
      id: 'narrative-panel',
      title: 'Agent Activity',
      className: 'narrative-panel',
      showCount: true,
      trackActivity: true,
    });

    this.statusEl = h('span', { className: 'narrative-panel__status' });
    // Insert status into header
    const header = this.el.querySelector('.panel__header');
    if (header) header.appendChild(this.statusEl);

    this.listEl = h('div', { className: 'narrative-panel__list' });
    this.content.appendChild(this.listEl);

    this.showIdle();
  }

  private showIdle(): void {
    this.listEl.innerHTML = '';
    const msg = h('p', { className: 'narrative-panel__placeholder' }, 'Enter an entity name above to start an investigation...');
    this.listEl.appendChild(msg);
  }

  setStatus(status: InvestigationStatus): void {
    this.statusEl.innerHTML = '';
    if (status === 'running') {
      const dot = h('span', { className: 'narrative-panel__dot narrative-panel__dot--pulse' });
      this.statusEl.appendChild(dot);
      this.statusEl.appendChild(document.createTextNode(' Investigating'));
      this.statusEl.className = 'narrative-panel__status narrative-panel__status--running';
    } else if (status === 'complete') {
      this.statusEl.textContent = 'Complete';
      this.statusEl.className = 'narrative-panel__status narrative-panel__status--complete';
    } else {
      this.statusEl.textContent = '';
      this.statusEl.className = 'narrative-panel__status';
    }
  }

  clear(): void {
    this.listEl.innerHTML = '';
    this.setCount(0);
    this.showIdle();
  }

  addStep(step: AgentStep, index: number): void {
    // Remove placeholder
    const placeholder = this.listEl.querySelector('.narrative-panel__placeholder');
    if (placeholder) placeholder.remove();

    const entry = h('div', { className: 'narrative-panel__entry narrative-panel__entry--animate' });

    const icon = TOOL_ICONS[step.tool] ?? '🔧';

    // Header row: icon + tool name
    const headerRow = h('div', { className: 'narrative-panel__entry-header' });
    headerRow.appendChild(h('span', { className: 'narrative-panel__icon' }, icon));

    const body = h('div', { className: 'narrative-panel__entry-body' });
    body.appendChild(h('span', { className: 'narrative-panel__tool' }, step.tool));
    body.appendChild(h('p', { className: 'narrative-panel__message' }, escapeHtml(step.message)));

    headerRow.appendChild(body);
    entry.appendChild(headerRow);

    // Pattern alerts
    if (step.patterns && step.patterns.length > 0) {
      const alertsEl = h('div', { className: 'narrative-panel__alerts' });
      for (const p of step.patterns) {
        alertsEl.appendChild(this.renderAlert(p));
      }
      entry.appendChild(alertsEl);
    }

    this.listEl.appendChild(entry);
    this.setCount(index + 1);
    this.pulse();

    // Auto-scroll
    this.content.scrollTop = this.content.scrollHeight;
  }

  showTyping(): void {
    const existing = this.listEl.querySelector('.narrative-panel__typing');
    if (existing) return;
    const dots = h('div', { className: 'narrative-panel__typing' });
    for (let i = 0; i < 3; i++) {
      const dot = h('span', { className: 'narrative-panel__bounce-dot' });
      dot.style.animationDelay = `${i * 150}ms`;
      dots.appendChild(dot);
    }
    this.listEl.appendChild(dots);
    this.content.scrollTop = this.content.scrollHeight;
  }

  hideTyping(): void {
    const typing = this.listEl.querySelector('.narrative-panel__typing');
    if (typing) typing.remove();
  }

  private renderAlert(p: PatternAlert): HTMLElement {
    const colors = SEVERITY_COLORS[p.severity];
    const alert = h('div', { className: 'narrative-panel__alert' });
    alert.style.borderLeftColor = colors.border;
    alert.style.backgroundColor = colors.bg;
    alert.style.color = colors.text;

    const badgeRow = h('div', { className: 'narrative-panel__alert-header' });

    const badge = h('span', { className: 'narrative-panel__badge' }, p.severity);
    badge.style.backgroundColor = colors.badge;
    badge.style.color = colors.text;
    badgeRow.appendChild(badge);

    badgeRow.appendChild(h('span', { className: 'narrative-panel__alert-type' }, p.type));
    alert.appendChild(badgeRow);

    alert.appendChild(h('p', { className: 'narrative-panel__alert-detail' }, escapeHtml(p.detail)));
    alert.appendChild(h('p', { className: 'narrative-panel__alert-confidence' }, `Confidence: ${Math.round(p.confidence * 100)}%`));

    return alert;
  }
}
