/**
 * SignalsPage — Page Object for the Signal Queue (/signals) page
 *
 * Tabs: Signal Queue, Trading Signals
 * Modals: SignalDetailModal, StrategyDetailModal, SendToBotModal, BatchAnalysisModal
 */
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class SignalsPage extends BasePage {
  readonly heading: Locator;
  readonly queueTab: Locator;
  readonly signalsTab: Locator;
  readonly queueTable: Locator;
  readonly signalsTable: Locator;

  constructor(page: Page) {
    super(page);
    this.heading = page.locator('h1:has-text("Signal Processing")');
    this.queueTab = page.locator('button:has-text("Signal Queue")');
    this.signalsTab = page.locator('button:has-text("Trading Signals")');
    this.queueTable = page.locator('table').first();
    this.signalsTable = page.locator('table').first();
  }

  /** Navigate to the Signals page */
  async goto(): Promise<void> {
    await this.navigateTo('/signals');
  }

  /** Get the count of signal rows in the Trading Signals table */
  async getSignalCount(): Promise<number> {
    // Switch to signals tab first
    await this.signalsTab.click();
    await this.page.waitForTimeout(500);

    const rows = this.page.locator('table tbody tr');
    return rows.count();
  }

  /** Get the count of queue items in the Signal Queue table */
  async getQueueCount(): Promise<number> {
    // Make sure we are on the queue tab
    await this.queueTab.click();
    await this.page.waitForTimeout(500);

    const rows = this.page.locator('table tbody tr');
    return rows.count();
  }

  /** Switch to the Trading Signals tab */
  async switchToSignalsTab(): Promise<void> {
    await this.signalsTab.click();
    await this.page.waitForTimeout(500);
  }

  /** Switch to the Signal Queue tab */
  async switchToQueueTab(): Promise<void> {
    await this.queueTab.click();
    await this.page.waitForTimeout(500);
  }

  /** Click the "Trade" button on a signal at the given row index (0-based) */
  async clickTradeButton(index: number = 0): Promise<void> {
    await this.switchToSignalsTab();
    const tradeButtons = this.page.locator('table tbody tr').nth(index).locator('button:has-text("Trade")');
    await tradeButtons.click();
  }

  /** Check if the SendToBotModal is currently open */
  async isSendToBotModalOpen(): Promise<boolean> {
    const modal = this.page.locator('text=Send to Bot');
    return modal.isVisible({ timeout: 3000 }).catch(() => false);
  }

  /** Get preview data from the SendToBotModal (when in PREVIEW_READY state) */
  async getPreviewData(): Promise<{
    symbol: string | null;
    direction: string | null;
    riskApproved: boolean;
    quantity: string | null;
  }> {
    const modal = this.page.locator('.fixed.inset-0');

    // Extract symbol from the modal
    const symbolText = await modal.locator('text=Symbol').locator('..').locator('span').last().innerText().catch(() => null);

    // Extract direction (BUY/SELL badge)
    const directionBadge = modal.locator('span:has-text("BUY"), span:has-text("SELL")').first();
    const direction = await directionBadge.innerText().catch(() => null);

    // Check risk approval
    const riskApproved = await modal.locator('text=Approved').isVisible({ timeout: 1000 }).catch(() => false);

    // Extract quantity
    const quantityText = await modal.locator('text=Quantity').locator('..').locator('span').last().innerText().catch(() => null);

    return {
      symbol: symbolText,
      direction,
      riskApproved,
      quantity: quantityText,
    };
  }

  /** Click the "Confirm & Execute" button in the SendToBotModal */
  async clickExecute(): Promise<void> {
    const executeButton = this.page.locator('button:has-text("Confirm & Execute")');
    await executeButton.click();
  }

  /** Get the status text of a signal at the given row index */
  async getSignalStatus(index: number = 0): Promise<string> {
    await this.switchToSignalsTab();
    const row = this.page.locator('table tbody tr').nth(index);
    // Check if "Executed" badge is present
    const executed = row.locator('text=Executed');
    if (await executed.isVisible({ timeout: 500 }).catch(() => false)) {
      return 'executed';
    }
    // Check for Trade button presence
    const tradeBtn = row.locator('button:has-text("Trade")');
    if (await tradeBtn.isVisible({ timeout: 500 }).catch(() => false)) {
      return 'active';
    }
    return 'unknown';
  }

  /** Wait for the success screen in SendToBotModal */
  async waitForTradeSuccess(timeout: number = 10000): Promise<boolean> {
    return this.page
      .locator('text=Trade Executed!')
      .isVisible({ timeout })
      .catch(() => false);
  }

  /** Click "Done" on the success screen of SendToBotModal */
  async clickDone(): Promise<void> {
    await this.page.locator('button:has-text("Done")').click();
  }

  /** Get the stat card values (Active, Paused, Total Signals, Unread) */
  async getStatValues(): Promise<{
    active: string;
    paused: string;
    totalSignals: string;
    unread: string;
  }> {
    const cards = this.page.locator('.text-3xl.font-bold');
    return {
      active: await cards.nth(0).innerText().catch(() => '0'),
      paused: await cards.nth(1).innerText().catch(() => '0'),
      totalSignals: await cards.nth(2).innerText().catch(() => '0'),
      unread: await cards.nth(3).innerText().catch(() => '0'),
    };
  }
}
