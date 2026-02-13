/**
 * PortfolioPage — Page Object for the Portfolio (/portfolio) page
 *
 * Tabs: Overview, Positions, Paper Trading, Brokers
 */
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class PortfolioPage extends BasePage {
  readonly heading: Locator;
  readonly overviewTab: Locator;
  readonly positionsTab: Locator;
  readonly paperTradingTab: Locator;
  readonly brokersTab: Locator;
  readonly refreshButton: Locator;

  constructor(page: Page) {
    super(page);
    this.heading = page.locator('h1:has-text("Portfolio")');
    this.overviewTab = page.locator('button:has-text("Overview")');
    this.positionsTab = page.locator('button:has-text("Positions")');
    this.paperTradingTab = page.locator('button:has-text("Paper Trading")');
    this.brokersTab = page.locator('button:has-text("Brokers")');
    this.refreshButton = page.locator('button:has-text("Refresh")');
  }

  /** Navigate to the Portfolio page */
  async goto(): Promise<void> {
    await this.navigateTo('/portfolio');
  }

  /** Get the count of position rows in the positions table */
  async getPositionCount(): Promise<number> {
    // Positions are shown in a table within the overview or positions tab
    const rows = this.page.locator('table tbody tr');
    return rows.count();
  }

  /** Get the P&L value for a specific symbol from the positions table */
  async getPositionPnL(symbol: string): Promise<string | null> {
    const row = this.page.locator(`table tbody tr:has-text("${symbol}")`);
    if (!(await row.isVisible({ timeout: 2000 }).catch(() => false))) {
      return null;
    }
    // P&L column is typically the 8th td (0-indexed: 7) in the positions table
    const cells = row.locator('td');
    const cellCount = await cells.count();
    // Find the cell that contains a $ sign and +/- (P&L value)
    for (let i = cellCount - 3; i < cellCount; i++) {
      const text = await cells.nth(i).innerText();
      if (text.includes('$') && (text.includes('+') || text.includes('-'))) {
        return text.trim();
      }
    }
    return null;
  }

  /** Get the total portfolio value from the summary card */
  async getTotalValue(): Promise<string | null> {
    const valueLabel = this.page.locator('text=Total Portfolio Value');
    if (!(await valueLabel.isVisible({ timeout: 3000 }).catch(() => false))) {
      return null;
    }
    // The value is in a sibling element with text-3xl
    const valueContainer = valueLabel.locator('..').locator('.text-3xl');
    return valueContainer.innerText().catch(() => null);
  }

  /** Switch to the Positions tab */
  async switchToPositionsTab(): Promise<void> {
    await this.positionsTab.click();
    await this.page.waitForTimeout(500);
  }

  /** Switch to the Paper Trading tab */
  async switchToPaperTradingTab(): Promise<void> {
    await this.paperTradingTab.click();
    await this.page.waitForTimeout(500);
  }

  /** Switch to the Brokers tab */
  async switchToBrokersTab(): Promise<void> {
    await this.brokersTab.click();
    await this.page.waitForTimeout(500);
  }

  /** Check if the "No Broker Connected" empty state is shown */
  async isNoBrokerConnected(): Promise<boolean> {
    return this.page
      .locator('text=No Broker Connected')
      .isVisible({ timeout: 3000 })
      .catch(() => false);
  }

  /** Check if the page has loaded */
  async isLoaded(): Promise<boolean> {
    return this.heading.isVisible({ timeout: 5000 }).catch(() => false);
  }
}
