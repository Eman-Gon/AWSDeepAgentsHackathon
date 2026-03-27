import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { SUGGESTIONS } from '@/config/constants';

export class SearchPanel extends Panel {
  private input: HTMLInputElement;
  private btn: HTMLButtonElement;
  private onInvestigate: (query: string) => void;

  constructor(onInvestigate: (query: string) => void) {
    super({
      id: 'search-panel',
      title: 'Investigate',
      className: 'search-panel',
    });

    this.onInvestigate = onInvestigate;

    // Search row
    const row = h('div', { className: 'search-panel__row' });

    this.input = h('input', {
      type: 'text',
      className: 'search-panel__input',
      placeholder: 'Investigate an entity — person, company, or contract...',
    });
    this.input.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter') this.submit();
    });

    this.btn = h('button', { className: 'search-panel__btn' }, 'Investigate');
    this.btn.addEventListener('click', () => this.submit());

    row.appendChild(this.input);
    row.appendChild(this.btn);
    this.content.appendChild(row);

    // Suggestions
    const suggestions = h('div', { className: 'search-panel__suggestions' });
    const label = h('span', { className: 'search-panel__label' }, 'Try:');
    suggestions.appendChild(label);

    for (const s of SUGGESTIONS) {
      const chip = h('button', { className: 'search-panel__chip' }, s);
      chip.addEventListener('click', () => {
        this.input.value = s;
        this.submit();
      });
      suggestions.appendChild(chip);
    }

    this.content.appendChild(suggestions);
  }

  private submit(): void {
    const q = this.input.value.trim();
    if (q) this.onInvestigate(q);
  }

  setDisabled(disabled: boolean): void {
    this.input.disabled = disabled;
    this.btn.disabled = disabled;
    this.btn.textContent = disabled ? 'Investigating...' : 'Investigate';
  }
}
