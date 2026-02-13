/**
 * CommandCenterPage — Page Object for the Command Center (/) dashboard
 *
 * Widgets: Market Pulse, Fear & Greed Gauge, MRI, Catalyst Feed,
 *          Morning Brief, Sector Heatmap, Copilot Chat, News, etc.
 */
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class CommandCenterPage extends BasePage {
  readonly heading: Locator;

  constructor(page: Page) {
    super(page);
    this.heading = page.locator('h1');
  }

  /** Navigate to the Command Center page */
  async goto(): Promise<void> {
    await this.navigateTo('/command-center');
  }

  /**
   * Check that the page has loaded its key elements.
   * The Command Center renders widgets via lazy-loaded components,
   * so we just check for the heading and the main container.
   */
  async isLoaded(): Promise<boolean> {
    try {
      // The page should have a heading or recognizable content
      // The CommandCenter uses a trading mode selector with "LEAPS", "Swing", "Day" buttons
      const hasContent = await this.page
        .locator('text=Command Center')
        .or(this.page.locator('text=LEAPS'))
        .or(this.page.locator('text=Market Pulse'))
        .first()
        .isVisible({ timeout: 5000 });
      return hasContent;
    } catch {
      return false;
    }
  }

  /** Count visible widget containers (cards/sections) on the dashboard */
  async getWidgetCount(): Promise<number> {
    // Widgets are typically wrapped in rounded-xl or rounded-lg containers
    const widgets = this.page.locator('.rounded-xl, .rounded-lg').filter({
      has: this.page.locator('h3, h2'),
    });
    return widgets.count();
  }

  /** Check if the news ticker is visible (it is rendered globally in App.jsx) */
  async isNewsTickerVisible(): Promise<boolean> {
    // The NewsTicker renders an overflow-hidden container with animated items
    // It appears on ALL pages as a global component
    const ticker = this.page.locator('.overflow-hidden').first();
    return ticker.isVisible({ timeout: 3000 }).catch(() => false);
  }

  /** Get the currently selected trading mode */
  async getSelectedTradingMode(): Promise<string | null> {
    // Trading mode buttons have distinct styling when selected
    const selected = this.page.locator('button.bg-green-600, button.bg-blue-600, button.bg-red-600').first();
    if (await selected.isVisible({ timeout: 2000 }).catch(() => false)) {
      return selected.innerText();
    }
    return null;
  }
}
