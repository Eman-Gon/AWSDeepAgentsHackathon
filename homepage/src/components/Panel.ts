import { h } from '@/utils/dom-utils';

export interface PanelOptions {
  id: string;
  title: string;
  className?: string;
  showCount?: boolean;
  trackActivity?: boolean;
  infoTooltip?: string;
}

/**
 * Base class for all UI panels. All dashboard components extend this.
 */
export class Panel {
  public readonly el: HTMLElement;
  public readonly content: HTMLElement;
  private headerEl: HTMLElement;
  private titleEl: HTMLElement;
  private countEl: HTMLElement | null = null;
  private opts: PanelOptions;

  constructor(opts: PanelOptions) {
    this.opts = opts;

    this.el = h('section', {
      id: opts.id,
      className: `panel ${opts.className ?? ''}`.trim(),
    });

    // Header
    this.headerEl = h('header', { className: 'panel__header' });

    this.titleEl = h('h2', { className: 'panel__title' }, opts.title);
    this.headerEl.appendChild(this.titleEl);

    if (opts.showCount) {
      this.countEl = h('span', { className: 'panel__count' }, '0');
      this.headerEl.appendChild(this.countEl);
    }

    if (opts.infoTooltip) {
      const tip = h('span', { className: 'panel__tooltip', title: opts.infoTooltip }, '?');
      this.headerEl.appendChild(tip);
    }

    this.el.appendChild(this.headerEl);

    // Scrollable content
    this.content = h('div', { className: 'panel__content' });
    this.el.appendChild(this.content);
  }

  /** Update the count badge */
  protected setCount(n: number): void {
    if (this.countEl) {
      this.countEl.textContent = String(n);
    }
  }

  /** Update panel title */
  protected setTitle(str: string): void {
    this.titleEl.textContent = str;
  }

  /** Trigger activity pulse animation */
  protected pulse(): void {
    if (!this.opts.trackActivity) return;
    this.el.classList.add('panel--pulse');
    setTimeout(() => this.el.classList.remove('panel--pulse'), 600);
  }

  /** Mount this panel into a parent element */
  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }
}
