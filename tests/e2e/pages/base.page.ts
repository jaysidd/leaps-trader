/**
 * BasePage — shared navigation and common page interaction helpers
 */
import { Page, Locator, expect } from '@playwright/test';
import { waitForPageLoad } from '../fixtures/test-helpers';

export class BasePage {
  readonly page: Page;
  readonly nav: Locator;
  readonly darkModeToggle: Locator;
  readonly botStatusBar: Locator;
  readonly newsTicker: Locator;

  constructor(page: Page) {
    this.page = page;
    this.nav = page.locator('nav');
    this.darkModeToggle = page.locator('nav button[title*="Mode"]');
    this.botStatusBar = page.locator('.bg-gray-800.text-white.text-sm');
    this.newsTicker = page.locator('.overflow-hidden').first();
  }

  /** Navigate to a specific path */
  async navigateTo(path: string): Promise<void> {
    await this.page.goto(path);
    await waitForPageLoad(this.page);
  }

  /** Get all visible navigation links */
  async getNavLinks(): Promise<string[]> {
    const links = this.nav.locator('a');
    const count = await links.count();
    const texts: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await links.nth(i).innerText();
      texts.push(text.trim());
    }
    return texts;
  }

  /** Click a navigation link by its visible text */
  async clickNavLink(text: string): Promise<void> {
    await this.nav.locator(`a:has-text("${text}")`).click();
    await waitForPageLoad(this.page);
  }

  /** Check if the navigation bar is visible */
  async isNavVisible(): Promise<boolean> {
    return this.nav.isVisible();
  }

  /** Toggle dark mode via the nav button */
  async toggleDarkMode(): Promise<void> {
    await this.darkModeToggle.click();
  }

  /** Check if dark mode is active by inspecting the html element */
  async isDarkMode(): Promise<boolean> {
    const htmlClass = await this.page.locator('html').getAttribute('class');
    return htmlClass?.includes('dark') ?? false;
  }

  /** Check if the bot status bar is visible (only shown when bot is not stopped) */
  async isBotStatusBarVisible(): Promise<boolean> {
    // The BotStatusBar renders a specific div only when bot is not stopped
    const statusBar = this.page.locator('div.bg-gray-800.text-white.text-sm.px-4.py-2');
    return statusBar.isVisible({ timeout: 2000 }).catch(() => false);
  }

  /** Get bot status from the status bar */
  async getBotStatus(): Promise<string | null> {
    const statusBar = this.page.locator('div.bg-gray-800.text-white.text-sm.px-4.py-2');
    if (!(await statusBar.isVisible({ timeout: 2000 }).catch(() => false))) {
      return null;
    }
    const text = await statusBar.innerText();
    // Status format: "RUNNING | PAPER | SIGNAL ONLY ..."
    const match = text.match(/^(\w+)\s*\|/);
    return match ? match[1].toLowerCase() : null;
  }

  /** Get current page heading (h1) */
  async getPageHeading(): Promise<string> {
    const heading = this.page.locator('h1').first();
    await heading.waitFor({ state: 'visible', timeout: 5000 });
    return heading.innerText();
  }

  /** Check if any loading spinner is visible */
  async isLoading(): Promise<boolean> {
    return this.page.locator('.animate-spin').first().isVisible({ timeout: 1000 }).catch(() => false);
  }

  /** Wait until no loading spinners are visible */
  async waitForLoadingToFinish(timeout: number = 10000): Promise<void> {
    const spinner = this.page.locator('.animate-spin').first();
    if (await spinner.isVisible({ timeout: 500 }).catch(() => false)) {
      await spinner.waitFor({ state: 'hidden', timeout });
    }
  }
}
