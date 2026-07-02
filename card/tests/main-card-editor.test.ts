import { describe, it, expect } from 'vitest';
import '../src/adaptive-cover-card-editor';
import type { AdaptiveCoverCardConfig } from '../src/types';

interface EditorLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: unknown;
  setConfig(config: AdaptiveCoverCardConfig): void;
  _entries: { entry_id: string; title: string }[] | null;
  _onCoverColorChange(value: string): void;
  _onCoverColorReset(): void;
  _onSectionToggle(key: string, enabled: boolean): void;
}

function makeEditor(): EditorLike {
  const el = document.createElement('adaptive-cover-card-editor') as EditorLike;
  el.hass = { states: {}, callWS: async () => [] };
  return el;
}

describe('main-card editor cover colors (issue #132)', () => {
  it('renders a color input when entry_id is set', async () => {
    const el = makeEditor();
    el._entries = [{ entry_id: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:adaptive-cover-card', entry_id: 'a' });
    document.body.appendChild(el);
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('input[type="color"]')).toBeTruthy();
  });

  it('does not render a color input when entry_id is empty', async () => {
    const el = makeEditor();
    el._entries = [{ entry_id: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:adaptive-cover-card', entry_id: '' });
    document.body.appendChild(el);
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('input[type="color"]')).toBeNull();
  });

  it('emits cover_colors:[value] on color change', () => {
    const el = makeEditor();
    el._entries = [{ entry_id: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:adaptive-cover-card', entry_id: 'a' });

    let emitted: AdaptiveCoverCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onCoverColorChange('#123456');
    expect(emitted).not.toBeNull();
    expect(emitted!.cover_colors).toEqual(['#123456']);
  });

  // The Pro-era opt-in "Solar calculation" section is gone with the move to
  // the Adaptive Cover integration: the card has exactly six sections.
  it('renders the six section toggles and no Solar calculation section', async () => {
    const el = makeEditor();
    el._entries = [{ entry_id: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:adaptive-cover-card', entry_id: 'a' });
    document.body.appendChild(el);
    await el.updateComplete;
    const labels = Array.from(el.shadowRoot!.querySelectorAll('.toggle-label')).map(
      (n) => n.textContent?.trim() ?? '',
    );
    expect(labels).toContain('Sky compass');
    expect(labels).toContain('Sun today');
    expect(labels).toContain('Decision strip');
    expect(labels).toContain('Cover positions');
    expect(labels).toContain('Overrides panel');
    expect(labels).toContain('Climate panel');
    expect(labels).not.toContain('Solar calculation');
  });

  it('toggling a default-on section off emits show_sections without it, order preserved', async () => {
    const el = makeEditor();
    el._entries = [{ entry_id: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:adaptive-cover-card', entry_id: 'a' });
    document.body.appendChild(el);
    await el.updateComplete;

    let emitted: AdaptiveCoverCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });
    el._onSectionToggle('climate', false);
    expect(emitted).not.toBeNull();
    // All sections are on by default, so dropping climate leaves the other five.
    expect(emitted!.show_sections).toEqual(['sky', 'elevation', 'decision', 'covers', 'overrides']);
  });

  it('reset emits a config without cover_colors', () => {
    const el = makeEditor();
    el._entries = [{ entry_id: 'a', title: 'Kitchen' }];
    el.setConfig({
      type: 'custom:adaptive-cover-card',
      entry_id: 'a',
      cover_colors: ['#123456'],
    });

    let emitted: AdaptiveCoverCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onCoverColorReset();
    expect(emitted).not.toBeNull();
    expect(emitted!.cover_colors).toBeUndefined();
  });
});
