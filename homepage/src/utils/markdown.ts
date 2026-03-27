/**
 * Lightweight markdown → HTML converter for agent briefings.
 * Handles: headings, bold, italic, lists, code blocks, horizontal rules, links, line breaks.
 * No external dependencies.
 */

import { escapeHtml } from './sanitize';

export function renderMarkdown(md: string): string {
  // Escape HTML first, then apply markdown transforms
  const escaped = escapeHtml(md);
  const lines = escaped.split('\n');
  const html: string[] = [];
  let inList = false;
  let inCodeBlock = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Code blocks (```)
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        html.push('</code></pre>');
        inCodeBlock = false;
      } else {
        if (inList) { html.push('</ul>'); inList = false; }
        html.push('<pre class="md-code"><code>');
        inCodeBlock = true;
      }
      continue;
    }
    if (inCodeBlock) {
      html.push(line);
      continue;
    }

    // Close list if current line isn't a list item
    if (inList && !line.match(/^\s*[-*]\s/) && !line.match(/^\s*\d+\.\s/) && line.trim() !== '') {
      html.push('</ul>');
      inList = false;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      html.push('<hr class="md-hr">');
      continue;
    }

    // Headings
    const headingMatch = line.match(/^(#{1,4})\s+(.+)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      html.push(`<h${level} class="md-h${level}">${applyInline(headingMatch[2])}</h${level}>`);
      continue;
    }

    // List items (- or * or 1.)
    const listMatch = line.match(/^\s*[-*]\s+(.+)/) || line.match(/^\s*\d+\.\s+(.+)/);
    if (listMatch) {
      if (!inList) { html.push('<ul class="md-list">'); inList = true; }
      html.push(`<li>${applyInline(listMatch[1])}</li>`);
      continue;
    }

    // Empty line
    if (line.trim() === '') {
      if (inList) { html.push('</ul>'); inList = false; }
      continue;
    }

    // Regular paragraph
    html.push(`<p class="md-p">${applyInline(line)}</p>`);
  }

  if (inList) html.push('</ul>');
  if (inCodeBlock) html.push('</code></pre>');

  return html.join('\n');
}

/** Apply inline markdown: bold, italic, inline code, links */
function applyInline(text: string): string {
  return text
    // Bold: **text** or __text__
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    // Italic: *text* or _text_
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    // Inline code: `text`
    .replace(/`(.+?)`/g, '<code class="md-inline-code">$1</code>');
}
