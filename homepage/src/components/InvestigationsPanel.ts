import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { escapeHtml } from '@/utils/sanitize';

export interface SavedInvestigation {
  id: string;
  title: string;
  summary: string;
  entity_ids: string[];
  findings_count: number;
  status: string;
  outcome: string;
  created_at: number;
  published_at: number | null;
}

interface InvestigationsPanelCallbacks {
  onLoad: (id: string) => void;
  onOutcomeChange: (id: string, outcome: string) => void;
}

const OUTCOME_LABELS: Record<string, { label: string; color: string }> = {
  ongoing:   { label: 'Ongoing',   color: 'var(--accent)' },
  confirmed: { label: 'Confirmed', color: 'var(--green)' },
  dead_end:  { label: 'Dead End',  color: 'var(--text-muted)' },
  published: { label: 'Published', color: 'var(--yellow)' },
};

export class InvestigationsPanel extends Panel {
  private listEl: HTMLElement;
  private emptyEl: HTMLElement;
  private callbacks: InvestigationsPanelCallbacks;
  private investigations: SavedInvestigation[] = [];

  constructor(callbacks: InvestigationsPanelCallbacks) {
    super({
      id: 'investigations-panel',
      title: 'Investigations',
      className: 'investigations-panel',
      showCount: true,
      trackActivity: true,
    });

    this.callbacks = callbacks;

    this.emptyEl = h('div', { className: 'investigations__empty' });
    this.emptyEl.innerHTML = '<span class="investigations__empty-icon">&#128203;</span><p>Saved investigations will appear here</p>';
    this.content.appendChild(this.emptyEl);

    this.listEl = h('div', { className: 'investigations__list' });
    this.content.appendChild(this.listEl);
  }

  async refresh(): Promise<void> {
    try {
      const res = await fetch('/api/investigations');
      if (!res.ok) return;
      this.investigations = await res.json();
      this.render();
    } catch {
      // Backend unavailable — leave list as-is
    }
  }

  private render(): void {
    this.listEl.innerHTML = '';
    this.setCount(this.investigations.length);

    if (this.investigations.length === 0) {
      this.emptyEl.style.display = '';
      return;
    }

    this.emptyEl.style.display = 'none';

    for (const inv of this.investigations) {
      const card = h('div', { className: 'inv-card' });

      // Header row: title + outcome badge
      const header = h('div', { className: 'inv-card__header' });
      const title = h('span', { className: 'inv-card__title' }, escapeHtml(inv.title));
      title.addEventListener('click', () => this.callbacks.onLoad(inv.id));
      header.appendChild(title);

      const outcomeMeta = OUTCOME_LABELS[inv.outcome] || OUTCOME_LABELS.ongoing;
      const badge = h('span', { className: 'inv-card__outcome-badge' }, outcomeMeta.label);
      badge.style.color = outcomeMeta.color;
      badge.style.borderColor = outcomeMeta.color;
      header.appendChild(badge);
      card.appendChild(header);

      // Summary
      card.appendChild(h('p', { className: 'inv-card__summary' }, escapeHtml(inv.summary)));

      // Meta row: date + findings count
      const meta = h('div', { className: 'inv-card__meta' });
      const date = new Date(inv.created_at * 1000);
      meta.appendChild(h('span', {}, date.toLocaleDateString()));
      meta.appendChild(h('span', {}, `${inv.findings_count} findings`));
      card.appendChild(meta);

      // Outcome selector
      const actions = h('div', { className: 'inv-card__actions' });
      const select = document.createElement('select');
      select.className = 'inv-card__outcome-select';
      for (const [value, meta] of Object.entries(OUTCOME_LABELS)) {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = meta.label;
        if (value === inv.outcome) opt.selected = true;
        select.appendChild(opt);
      }
      select.addEventListener('change', () => {
        this.callbacks.onOutcomeChange(inv.id, select.value);
        // Update the badge immediately
        const newMeta = OUTCOME_LABELS[select.value] || OUTCOME_LABELS.ongoing;
        badge.textContent = newMeta.label;
        badge.style.color = newMeta.color;
        badge.style.borderColor = newMeta.color;
      });
      actions.appendChild(select);
      card.appendChild(actions);

      this.listEl.appendChild(card);
    }
  }

  /** Get all saved investigations for prior-investigation cross-reference */
  getInvestigations(): SavedInvestigation[] {
    return this.investigations;
  }
}
