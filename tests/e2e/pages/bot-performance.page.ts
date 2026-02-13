/**
 * BotPerformancePage — Page Object for the Bot Performance (/bot-performance) page
 *
 * Sections: Today banner, Summary stats, Strategy breakdown,
 *           Asset type breakdown, Exit reasons, Daily breakdown table
 */
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class BotPerformancePage extends BasePage {
  readonly heading: Locator;
  readonly periodButtons: Locator;
  readonly todayBanner: Locator;

  constructor(page: Page) {
    super(page);
    this.heading = page.locator('h1:has-text("Bot Performance")');
    this.periodButtons = page.locator('button:has-text("7D"), button:has-text("30D"), button:has-text("90D")');
    this.todayBanner = page.locator('h3:has-text("Today")');
  }

  /** Navigate to the Bot Performance page */
  async goto(): Promise<void> {
    await this.navigateTo('/bot-performance');
  }

  /** Check that the page has loaded (heading and stat cards visible) */
  async isLoaded(): Promise<boolean> {
    try {
      await this.heading.waitFor({ state: 'visible', timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }

  /** Get the daily P&L value from the Today banner */
  async getDailyPnL(): Promise<string | null> {
    // Today banner shows MiniStat components
    // Find the "P&L" label and get the value next to it
    const plLabel = this.page.locator('div:has-text("P&L")').filter({
      has: this.page.locator('.text-xs'),
    }).first();

    if (!(await plLabel.isVisible({ timeout: 3000 }).catch(() => false))) {
      return null;
    }

    const value = plLabel.locator('.font-bold.font-mono');
    return value.innerText().catch(() => null);
  }

  /** Get the win rate from the summary stats grid */
  async getWinRate(): Promise<string | null> {
    // StatCard with "Win Rate" label
    const card = this.page.locator('.rounded-lg.shadow.p-4').filter({
      hasText: 'Win Rate',
    }).first();

    if (!(await card.isVisible({ timeout: 3000 }).catch(() => false))) {
      return null;
    }

    const value = card.locator('.text-xl.font-bold');
    return value.innerText().catch(() => null);
  }

  /** Get a specific stat value by its label */
  async getStatValue(label: string): Promise<string | null> {
    const card = this.page.locator('.rounded-lg.shadow.p-4').filter({
      hasText: label,
    }).first();

    if (!(await card.isVisible({ timeout: 3000 }).catch(() => false))) {
      return null;
    }

    const value = card.locator('.text-xl.font-bold');
    return value.innerText().catch(() => null);
  }

  /** Select a time period (7D, 30D, 90D) */
  async selectPeriod(days: 7 | 30 | 90): Promise<void> {
    await this.page.locator(`button:has-text("${days}D")`).click();
    await this.waitForLoadingToFinish();
  }

  /** Check if the empty state is shown ("No trades recorded yet") */
  async hasNoTrades(): Promise<boolean> {
    return this.page
      .locator('text=No trades recorded yet')
      .isVisible({ timeout: 3000 })
      .catch(() => false);
  }

  /** Check if the error banner is visible */
  async hasError(): Promise<boolean> {
    return this.page
      .locator('.bg-red-50, .bg-red-900\\/20')
      .first()
      .isVisible({ timeout: 2000 })
      .catch(() => false);
  }

  /** Check if the strategy breakdown section is visible */
  async hasStrategyBreakdown(): Promise<boolean> {
    return this.page
      .locator('h3:has-text("By Strategy")')
      .isVisible({ timeout: 3000 })
      .catch(() => false);
  }

  /** Check if the daily breakdown table is visible */
  async hasDailyBreakdown(): Promise<boolean> {
    return this.page
      .locator('h3:has-text("Daily Breakdown")')
      .isVisible({ timeout: 3000 })
      .catch(() => false);
  }
}
