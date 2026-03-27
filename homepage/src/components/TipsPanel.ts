import { Panel } from '@/components/Panel';
import { h } from '@/utils/dom-utils';
import { escapeHtml } from '@/utils/sanitize';

export interface BlandTip {
  id: number;
  call_id: string;
  transcript: string;
  summary: string;
  caller_number: string;
  call_length: number;
  entities: string[];
  status: 'new' | 'reviewed' | 'investigating';
  created_at: number;
}

export class TipsPanel extends Panel {
  private tips: BlandTip[] = [];
  private listEl: HTMLElement;
  private filterStatus: string = 'all';
  private emptyEl: HTMLElement;
  private filterBar: HTMLElement;

  constructor() {
    super({
      id: 'tips-panel',
      title: 'Tip Line',
      className: 'tips-panel',
      showCount: true,
      trackActivity: true,
      infoTooltip: 'Incoming tips from the corruption hotline',
    });

    // Filter bar
    this.filterBar = h('div', { className: 'tips__filter-bar' });
    const filters = ['all', 'new', 'reviewed', 'investigating'];
    for (const status of filters) {
      const btn = h('button', {
        className: `tips__filter-btn ${status === 'all' ? 'tips__filter-btn--active' : ''}`,
        dataset: { status },
      }, status);
      btn.addEventListener('click', () => this.setFilter(status));
      this.filterBar.appendChild(btn);
    }
    this.content.appendChild(this.filterBar);

    // Empty state
    this.emptyEl = h('div', { className: 'tips__empty' });
    this.emptyEl.innerHTML = `
      <div class="tips__empty-icon">📞</div>
      <p>No tips received yet.</p>
      <p>Call the corruption tip line to report suspicious activity.</p>
    `;
    this.content.appendChild(this.emptyEl);

    // Tips list
    this.listEl = h('div', { className: 'tips__list' });
    this.content.appendChild(this.listEl);

    this.render();
  }

  /** Fetch tips from the backend */
  async fetchTips(baseUrl: string = ''): Promise<void> {
    try {
      const url = `${baseUrl}/api/bland-tips`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data.tips)) {
        this.tips = data.tips;
        this.setCount(this.tips.length);
        this.render();
        this.pulse();
      }
    } catch {
      // Backend unavailable — keep current state
    }
  }

  /** Add a single tip (for real-time updates) */
  addTip(tip: BlandTip): void {
    this.tips.unshift(tip);
    this.setCount(this.tips.length);
    this.render();
    this.pulse();
  }

  private setFilter(status: string): void {
    this.filterStatus = status;
    this.filterBar.querySelectorAll('.tips__filter-btn').forEach((btn) => {
      btn.classList.toggle('tips__filter-btn--active', (btn as HTMLElement).dataset.status === status);
    });
    this.render();
  }

  private getFilteredTips(): BlandTip[] {
    if (this.filterStatus === 'all') return this.tips;
    return this.tips.filter((t) => t.status === this.filterStatus);
  }

  private render(): void {
    const filtered = this.getFilteredTips();
    this.listEl.innerHTML = '';
    this.emptyEl.style.display = filtered.length === 0 ? '' : 'none';
    this.listEl.style.display = filtered.length === 0 ? 'none' : '';

    for (const tip of filtered) {
      const card = this.buildTipCard(tip);
      this.listEl.appendChild(card);
    }
  }

  private buildTipCard(tip: BlandTip): HTMLElement {
    const card = h('div', { className: 'tip-card tip-card--animate' });

    // Top row: status + timestamp
    const top = h('div', { className: 'tip-card__top' });
    const badge = h('span', {
      className: `tip-card__status tip-card__status--${tip.status}`,
    }, tip.status.toUpperCase());
    const time = h('span', { className: 'tip-card__time' }, this.formatTime(tip.created_at));
    top.appendChild(badge);
    top.appendChild(time);
    card.appendChild(top);

    // Summary
    if (tip.summary) {
      const summary = h('p', { className: 'tip-card__summary' }, tip.summary);
      card.appendChild(summary);
    }

    // Entities
    if (tip.entities && tip.entities.length > 0) {
      const entitiesRow = h('div', { className: 'tip-card__entities' });
      for (const entity of tip.entities) {
        entitiesRow.appendChild(h('span', { className: 'tip-card__entity' }, escapeHtml(entity)));
      }
      card.appendChild(entitiesRow);
    }

    // Meta row: duration + caller
    const meta = h('div', { className: 'tip-card__meta' });
    if (tip.call_length) {
      meta.appendChild(h('span', {}, `⏱ ${Math.round(tip.call_length)}s`));
    }
    if (tip.caller_number) {
      const masked = tip.caller_number.replace(/(\+\d{1})\d+(\d{4})/, '$1****$2');
      meta.appendChild(h('span', {}, `📞 ${masked}`));
    }
    card.appendChild(meta);

    // Expandable transcript
    const transcriptToggle = h('button', { className: 'tip-card__transcript-toggle' }, 'Show transcript');
    const transcriptBody = h('div', { className: 'tip-card__transcript' });
    transcriptBody.style.display = 'none';
    transcriptBody.textContent = tip.transcript || 'No transcript available';

    transcriptToggle.addEventListener('click', () => {
      const showing = transcriptBody.style.display !== 'none';
      transcriptBody.style.display = showing ? 'none' : '';
      transcriptToggle.textContent = showing ? 'Show transcript' : 'Hide transcript';
    });

    card.appendChild(transcriptToggle);
    card.appendChild(transcriptBody);

    return card;
  }

  private formatTime(epoch: number): string {
    const d = new Date(epoch * 1000);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }
}
