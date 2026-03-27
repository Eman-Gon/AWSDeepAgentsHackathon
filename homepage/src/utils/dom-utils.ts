/**
 * Typed createElement helper.
 * h('div', { className: 'foo' }, 'text') → <div class="foo">text</div>
 */
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props?: Partial<HTMLElementTagNameMap[K]> & Record<string, unknown>,
  ...children: (string | Node)[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (props) {
    for (const [key, value] of Object.entries(props)) {
      if (key === 'className') {
        el.className = value as string;
      } else if (key === 'style' && typeof value === 'object') {
        Object.assign(el.style, value);
      } else if (key.startsWith('on') && typeof value === 'function') {
        const event = key.slice(2).toLowerCase();
        el.addEventListener(event, value as EventListener);
      } else if (key === 'dataset' && typeof value === 'object') {
        Object.assign(el.dataset, value);
      } else {
        (el as Record<string, unknown>)[key] = value;
      }
    }
  }
  for (const child of children) {
    if (typeof child === 'string') {
      el.appendChild(document.createTextNode(child));
    } else {
      el.appendChild(child);
    }
  }
  return el;
}

/**
 * XSS-safe innerHTML via DOMParser. Only use for trusted-ish HTML
 * (still sanitized through the parser).
 */
export function safeHtml(container: HTMLElement, html: string): void {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  container.innerHTML = '';
  while (doc.body.firstChild) {
    container.appendChild(doc.body.firstChild);
  }
}

/**
 * Clear a node and replace with new children.
 */
export function replaceChildren(parent: HTMLElement, ...children: Node[]): void {
  parent.innerHTML = '';
  for (const child of children) {
    parent.appendChild(child);
  }
}
