import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { escapeHtml } from '@/utils/sanitize';
import { renderMarkdown } from '@/utils/markdown';
import { TOOL_ICONS } from '@/config/constants';
import type { AgentStep, InvestigationStatus, StepSource } from '@/types';

export class NarrativePanel extends Panel {
  private listEl: HTMLElement;
  private statusEl: HTMLElement;

  constructor() {
    super({
      id: 'narrative-panel',
      title: 'Investigation Timeline',
      className: 'narrative-panel',
      showCount: true,
      trackActivity: true,
    });

    this.statusEl = h('span', { className: 'timeline__status' });
    const header = this.el.querySelector('.panel__header');
    if (header) header.appendChild(this.statusEl);

    this.listEl = h('div', { className: 'timeline__list' });
    this.content.appendChild(this.listEl);

    this.showIdle();
  }

  private showIdle(): void {
    this.listEl.innerHTML = '';
    const msg = h('p', { className: 'timeline__placeholder' }, 'Agent steps will appear here...');
    this.listEl.appendChild(msg);
  }

  setStatus(status: InvestigationStatus): void {
    this.statusEl.innerHTML = '';
    if (status === 'running') {
      const dot = h('span', { className: 'timeline__dot timeline__dot--pulse' });
      this.statusEl.appendChild(dot);
      this.statusEl.appendChild(document.createTextNode('Running'));
      this.statusEl.className = 'timeline__status timeline__status--running';
    } else if (status === 'complete') {
      this.statusEl.textContent = 'Done';
      this.statusEl.className = 'timeline__status timeline__status--complete';
    } else {
      this.statusEl.textContent = '';
      this.statusEl.className = 'timeline__status';
    }
  }

  clear(): void {
    this.listEl.innerHTML = '';
    this.setCount(0);
    this.showIdle();
  }

  addStep(step: AgentStep, index: number): void {
    const placeholder = this.listEl.querySelector('.timeline__placeholder');
    if (placeholder) placeholder.remove();

    const icon = TOOL_ICONS[step.tool] ?? '>';
    const entry = h('div', { className: 'timeline__entry timeline__entry--animate' });

    // Timeline dot
    const dotCol = h('div', { className: 'timeline__dot-col' });
    const dot = h('div', { className: 'timeline__step-dot' });
    dotCol.appendChild(dot);
    if (index > 0) {
      const line = h('div', { className: 'timeline__line' });
      dotCol.appendChild(line);
    }

    // Content
    const body = h('div', { className: 'timeline__body' });
    const toolRow = h('div', { className: 'timeline__tool-row' });
    toolRow.appendChild(h('span', { className: 'timeline__icon' }, icon));
    toolRow.appendChild(h('span', { className: 'timeline__tool-name' }, step.tool.replace(/_/g, ' ')));
    body.appendChild(toolRow);

    const isBriefing = step.tool === 'briefing' || step.tool === 'final_briefing';
    if (isBriefing) {
      // Render markdown for the final briefing
      const briefingEl = h('div', { className: 'timeline__briefing' });
      briefingEl.innerHTML = renderMarkdown(step.message);
      body.appendChild(briefingEl);

      // Add "Expand" button to open modal
      const expandBtn = h('button', { className: 'timeline__expand-btn' }, 'View Full Briefing');
      expandBtn.addEventListener('click', () => this.openBriefingModal(step.message));
      body.appendChild(expandBtn);
    } else {
      body.appendChild(h('p', { className: 'timeline__message' }, escapeHtml(step.message)));
    }

    if (step.sources && step.sources.length > 0) {
      body.appendChild(this.renderSources(step.sources));
    }

    entry.appendChild(dotCol);
    entry.appendChild(body);
    this.listEl.appendChild(entry);
    this.setCount(index + 1);
    this.pulse();

    // Scroll the section wrapper (which has overflow-y: auto), not the panel content
    const scrollParent = this.el.closest('.right-section--timeline') ?? this.content;
    scrollParent.scrollTop = scrollParent.scrollHeight;
  }

  private renderSources(sources: StepSource[]): HTMLElement {
    const wrap = h('div', { className: 'timeline__sources' });
    wrap.appendChild(h('span', { className: 'timeline__sources-label' }, 'Evidence'));

    for (const source of sources) {
      const item = source.url
        ? h('a', {
          className: 'timeline__source',
          href: source.url,
          target: '_blank',
          rel: 'noreferrer',
        })
        : h('div', { className: 'timeline__source' });

      item.appendChild(h('span', { className: 'timeline__source-system' }, source.system));
      item.appendChild(h('span', { className: 'timeline__source-label' }, source.label));
      if (source.detail) {
        item.appendChild(h('span', { className: 'timeline__source-detail' }, source.detail));
      }
      wrap.appendChild(item);
    }

    return wrap;
  }

  private openBriefingModal(markdown: string): void {
    // Create modal overlay
    const overlay = h('div', { className: 'briefing-modal__overlay' });
    const modal = h('div', { className: 'briefing-modal' });

    // Close button
    const closeBtn = h('button', { className: 'briefing-modal__close' }, '\u00D7');
    const close = () => overlay.remove();
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });

    // Header
    const header = h('div', { className: 'briefing-modal__header' });
    header.appendChild(h('h2', {}, 'Investigation Briefing'));
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // Rendered markdown body
    const body = h('div', { className: 'briefing-modal__body' });
    body.innerHTML = renderMarkdown(markdown);
    modal.appendChild(body);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Escape key closes
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); }
    };
    document.addEventListener('keydown', onKey);
  }

  showTyping(): void {
    if (this.listEl.querySelector('.timeline__typing')) return;
    const dots = h('div', { className: 'timeline__typing' });
    for (let i = 0; i < 3; i++) {
      const d = h('span', { className: 'timeline__bounce-dot' });
      d.style.animationDelay = `${i * 150}ms`;
      dots.appendChild(d);
    }
    this.listEl.appendChild(dots);
    const scrollParent = this.el.closest('.right-section--timeline') ?? this.content;
    scrollParent.scrollTop = scrollParent.scrollHeight;
  }

  hideTyping(): void {
    const t = this.listEl.querySelector('.timeline__typing');
    if (t) t.remove();
  }
}
