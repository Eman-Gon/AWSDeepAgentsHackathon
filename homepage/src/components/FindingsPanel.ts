import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { escapeHtml } from '@/utils/sanitize';
import { SEVERITY_COLORS } from '@/config/constants';
import type { PatternAlert } from '@/types';

export class FindingsPanel extends Panel {
  private listEl: HTMLElement;
  private emptyEl: HTMLElement;
  private publishBtn: HTMLButtonElement;
  private publishStatusEl: HTMLElement;
  private onPublish: (() => void) | null;
  private canPublish: boolean;

  constructor(onPublish?: () => void, canPublish = false) {
    super({
      id: 'findings-panel',
      title: 'Findings',
      className: 'findings-panel',
      showCount: true,
      trackActivity: true,
    });

    this.onPublish = onPublish ?? null;
    this.canPublish = canPublish;

    this.emptyEl = h('div', { className: 'findings__empty' });
    this.emptyEl.innerHTML = '<span class="findings__empty-icon">&#9670;</span><p>Patterns will surface here as the agent investigates</p>';
    this.content.appendChild(this.emptyEl);

    const publishBar = h('div', { className: 'findings__publish-bar' });
    this.publishBtn = h('button', { className: 'findings__publish-btn' }, 'Publish Findings');
    this.publishBtn.addEventListener('click', () => this.onPublish?.());
    publishBar.appendChild(this.publishBtn);

    this.publishStatusEl = h('div', { className: 'findings__publish-status' });
    publishBar.appendChild(this.publishStatusEl);
    this.content.appendChild(publishBar);

    this.listEl = h('div', { className: 'findings__list' });
    this.content.appendChild(this.listEl);
    this.setPublishPermission(canPublish);
  }

  addPattern(p: PatternAlert): void {
    this.emptyEl.style.display = 'none';

    const colors = SEVERITY_COLORS[p.severity];
    const card = h('div', { className: 'finding-card finding-card--animate' });
    card.style.setProperty('--accent', colors.border);
    card.style.setProperty('--accent-bg', colors.bg);
    card.style.setProperty('--accent-text', colors.text);

    // Top row: severity + confidence
    const top = h('div', { className: 'finding-card__top' });
    const badge = h('span', { className: `finding-card__severity finding-card__severity--${p.severity.toLowerCase()}` }, p.severity);
    const conf = h('span', { className: 'finding-card__confidence' }, `${Math.round(p.confidence * 100)}% confidence`);
    top.appendChild(badge);
    top.appendChild(conf);
    card.appendChild(top);

    // Type label
    const typeLabel = p.type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    card.appendChild(h('h4', { className: 'finding-card__title' }, typeLabel));

    // Detail
    card.appendChild(h('p', { className: 'finding-card__detail' }, escapeHtml(p.detail)));

    this.listEl.appendChild(card);
    const count = this.listEl.children.length;
    this.setCount(count);
    this.pulse();

    this.content.scrollTop = this.content.scrollHeight;
    this.updatePublishButton();
  }

  clear(): void {
    this.listEl.innerHTML = '';
    this.emptyEl.style.display = '';
    this.setCount(0);
    this.setPublishFeedback('');
    this.updatePublishButton();
  }

  setPublishPermission(canPublish: boolean): void {
    this.canPublish = canPublish;
    this.setPublishFeedback(
      canPublish
        ? 'Editors can publish findings once results appear.'
        : 'Only signed-in human editors can publish findings.',
    );
    this.updatePublishButton();
  }

  setPublishBusy(busy: boolean): void {
    this.publishBtn.disabled = busy || !this.canPublish || this.listEl.children.length === 0;
    this.publishBtn.textContent = busy ? 'Publishing...' : 'Publish Findings';
  }

  setPublishFeedback(message: string): void {
    this.publishStatusEl.textContent = message;
  }

  private updatePublishButton(): void {
    this.publishBtn.disabled = !this.canPublish || this.listEl.children.length === 0;
  }
}
