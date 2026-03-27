import { Panel } from '@/components/Panel';
import { h } from '@/utils/dom-utils';

export class TipLineInfo extends Panel {
  private phoneNumber: string;

  constructor(phoneNumber: string = 'TBD') {
    super({
      id: 'tipline-info',
      title: 'Corruption Tip Line',
      className: 'tipline-info',
    });

    this.phoneNumber = phoneNumber;
    this.buildContent();
  }

  setPhoneNumber(number: string): void {
    this.phoneNumber = number;
    const phoneEl = this.content.querySelector('.tipline__phone-number');
    if (phoneEl) phoneEl.textContent = number;
  }

  private buildContent(): void {
    // Hero section
    const hero = h('div', { className: 'tipline__hero' });

    const icon = h('div', { className: 'tipline__icon' }, '📞');
    hero.appendChild(icon);

    const heading = h('h3', { className: 'tipline__heading' }, 'Report Corruption');
    hero.appendChild(heading);

    const phone = h('div', { className: 'tipline__phone-number' }, this.phoneNumber);
    hero.appendChild(phone);

    const desc = h('p', { className: 'tipline__desc' },
      'Report suspicious government activity. Our AI agent will check your tip against our investigation database in real time.'
    );
    hero.appendChild(desc);

    this.content.appendChild(hero);

    // How it works flow
    const flow = h('div', { className: 'tipline__flow' });
    const flowTitle = h('div', { className: 'tipline__flow-title' }, 'How it works');
    flow.appendChild(flowTitle);

    const steps = [
      { icon: '🗣️', label: 'You Call', desc: 'Call the tip line and describe what you\'ve seen' },
      { icon: '🤖', label: 'AI Agent', desc: 'Bland voice agent processes your report' },
      { icon: '🔍', label: 'Graph Query', desc: 'Checks tip against 186K+ entity knowledge graph' },
      { icon: '📋', label: 'Investigation', desc: 'Team reviews matched patterns and entities' },
    ];

    const stepsRow = h('div', { className: 'tipline__steps' });
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const stepEl = h('div', { className: 'tipline__step' });
      stepEl.appendChild(h('div', { className: 'tipline__step-icon' }, step.icon));
      stepEl.appendChild(h('div', { className: 'tipline__step-label' }, step.label));
      stepEl.appendChild(h('div', { className: 'tipline__step-desc' }, step.desc));
      stepsRow.appendChild(stepEl);

      if (i < steps.length - 1) {
        stepsRow.appendChild(h('div', { className: 'tipline__step-arrow' }, '→'));
      }
    }
    flow.appendChild(stepsRow);
    this.content.appendChild(flow);
  }
}
