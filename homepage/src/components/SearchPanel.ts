import { Panel } from './Panel';
import { h } from '@/utils/dom-utils';
import { SUGGESTIONS } from '@/config/constants';

export class SearchPanel extends Panel {
  private input: HTMLInputElement;
  private btn: HTMLButtonElement;
  private hint: HTMLElement;
  private onInvestigate: (query: string) => void;
  private canInvestigate: boolean;

  constructor(onInvestigate: (query: string) => void, canInvestigate = true) {
    super({
      id: 'search-panel',
      title: 'Investigate',
      className: 'search-panel',
    });

    this.onInvestigate = onInvestigate;
    this.canInvestigate = canInvestigate;

    // Search row
    const row = h('div', { className: 'search__row' });

    const iconWrap = h('div', { className: 'search__icon-wrap' });
    iconWrap.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>';
    row.appendChild(iconWrap);

    this.input = h('input', {
      type: 'text',
      className: 'search__input',
      placeholder: 'Investigate a person, company, or contract...',
    });
    this.input.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter') this.submit();
    });
    row.appendChild(this.input);

    this.btn = h('button', { className: 'search__btn' }, 'Investigate');
    this.btn.addEventListener('click', () => this.submit());
    row.appendChild(this.btn);

    this.content.appendChild(row);

    this.hint = h('div', { className: 'search__auth-hint' });
    this.content.appendChild(this.hint);

    // Chips
    const chips = h('div', { className: 'search__chips' });
    for (const s of SUGGESTIONS) {
      const chip = h('button', { className: 'search__chip' }, s);
      chip.addEventListener('click', () => {
        this.input.value = s;
        this.submit();
      });
      chips.appendChild(chip);
    }
    this.content.appendChild(chips);
    this.setPermission(canInvestigate);
  }

  private submit(): void {
    if (!this.canInvestigate) return;
    const q = this.input.value.trim();
    if (q) this.onInvestigate(q);
  }

  setPermission(canInvestigate: boolean): void {
    this.canInvestigate = canInvestigate;
    this.input.disabled = !canInvestigate;
    this.btn.disabled = !canInvestigate;
    this.input.placeholder = canInvestigate
      ? 'Investigate a person, company, or contract...'
      : 'Your account does not have investigation access';
    this.hint.textContent = canInvestigate
      ? 'Signed-in journalists and editors can run investigations.'
      : 'You need the journalist or editor role to run investigations.';
  }

  setDisabled(disabled: boolean): void {
    this.input.disabled = disabled || !this.canInvestigate;
    this.btn.disabled = disabled || !this.canInvestigate;
    this.btn.textContent = disabled ? 'Investigating...' : 'Investigate';
  }
}
