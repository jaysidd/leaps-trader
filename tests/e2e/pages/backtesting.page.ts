/**
 * BacktestingPage — Page Object for the Backtesting (/backtesting) page
 *
 * Sections: Configuration form, Results (metrics, equity curve, trade log), History
 */
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class BacktestingPage extends BasePage {
  readonly heading: Locator;
  readonly symbolInput: Locator;
  readonly strategySelect: Locator;
  readonly timeframeSelect: Locator;
  readonly capSizeSelect: Locator;
  readonly startDateInput: Locator;
  readonly endDateInput: Locator;
  readonly capitalInput: Locator;
  readonly positionPctInput: Locator;
  readonly runButton: Locator;
  readonly configSection: Locator;

  constructor(page: Page) {
    super(page);
    this.heading = page.locator('h1:has-text("Backtesting")');
    this.configSection = page.locator('h2:has-text("Configuration")').locator('..');

    // Form inputs — use labels to find the related inputs
    this.symbolInput = page.locator('label:has-text("Symbol")').locator('..').locator('input');
    this.strategySelect = page.locator('label:has-text("Strategy")').locator('..').locator('select');
    this.timeframeSelect = page.locator('label:has-text("Timeframe")').locator('..').locator('select');
    this.capSizeSelect = page.locator('label:has-text("Cap Size")').locator('..').locator('select');
    this.startDateInput = page.locator('label:has-text("Start Date")').locator('..').locator('input');
    this.endDateInput = page.locator('label:has-text("End Date")').locator('..').locator('input');
    this.capitalInput = page.locator('label:has-text("Capital")').locator('..').locator('input');
    this.positionPctInput = page.locator('label:has-text("Position Size")').locator('..').locator('input');
    this.runButton = page.locator('button:has-text("Run Backtest")');
  }

  /** Navigate to the Backtesting page */
  async goto(): Promise<void> {
    await this.navigateTo('/backtesting');
  }

  /** Fill the configuration form with provided values */
  async fillConfig(config: {
    symbol?: string;
    strategy?: string;
    timeframe?: string;
    capSize?: string;
    startDate?: string;
    endDate?: string;
    capital?: number;
    positionPct?: number;
  }): Promise<void> {
    if (config.symbol !== undefined) {
      await this.symbolInput.fill(config.symbol);
    }
    if (config.strategy !== undefined) {
      await this.strategySelect.selectOption(config.strategy);
    }
    if (config.timeframe !== undefined) {
      await this.timeframeSelect.selectOption(config.timeframe);
    }
    if (config.capSize !== undefined) {
      await this.capSizeSelect.selectOption(config.capSize);
    }
    if (config.startDate !== undefined) {
      await this.startDateInput.fill(config.startDate);
    }
    if (config.endDate !== undefined) {
      await this.endDateInput.fill(config.endDate);
    }
    if (config.capital !== undefined) {
      await this.capitalInput.fill(String(config.capital));
    }
    if (config.positionPct !== undefined) {
      await this.positionPctInput.fill(String(config.positionPct));
    }
  }

  /** Click the "Run Backtest" button */
  async clickRunBacktest(): Promise<void> {
    await this.runButton.click();
  }

  /** Wait for the backtest to complete (results section becomes visible) */
  async waitForCompletion(timeout: number = 30000): Promise<void> {
    // Wait for the "Results:" heading to appear
    await this.page
      .locator('h2:has-text("Results:")')
      .waitFor({ state: 'visible', timeout });
  }

  /** Check if the running state is shown */
  async isRunning(): Promise<boolean> {
    return this.page
      .locator('text=Running backtest...')
      .isVisible({ timeout: 2000 })
      .catch(() => false);
  }

  /** Extract metric card values from the results section */
  async getMetrics(): Promise<{
    totalReturn: string;
    sharpeRatio: string;
    maxDrawdown: string;
    winRate: string;
    totalTrades: string;
    profitFactor: string;
  }> {
    // StatCard components render: label as .text-xs and value as .text-2xl
    const statCards = this.page.locator('.rounded-xl').filter({
      has: this.page.locator('.text-xs.font-medium.uppercase'),
    });

    const getMetricValue = async (label: string): Promise<string> => {
      const card = statCards.filter({ hasText: label }).first();
      const value = card.locator('.text-2xl.font-bold');
      return value.innerText().catch(() => '--');
    };

    return {
      totalReturn: await getMetricValue('Total Return'),
      sharpeRatio: await getMetricValue('Sharpe Ratio'),
      maxDrawdown: await getMetricValue('Max Drawdown'),
      winRate: await getMetricValue('Win Rate'),
      totalTrades: await getMetricValue('Total Trades'),
      profitFactor: await getMetricValue('Profit Factor'),
    };
  }

  /** Check if the equity curve chart container is visible */
  async isEquityCurveVisible(): Promise<boolean> {
    const chartSection = this.page.locator('h3:has-text("Equity Curve")');
    return chartSection.isVisible({ timeout: 3000 }).catch(() => false);
  }

  /** Count the rows in the trade log table */
  async getTradeLogRowCount(): Promise<number> {
    const tradeLogSection = this.page.locator('h3:has-text("Trade Log")').locator('..');
    const rows = tradeLogSection.locator('table tbody tr');
    return rows.count();
  }

  /** Count the number of backtests in the history table */
  async getHistoryCount(): Promise<number> {
    const historySection = this.page.locator('h2:has-text("Backtest History")').locator('..');
    const rows = historySection.locator('table tbody tr');
    return rows.count();
  }

  /** Check if the error banner is visible */
  async hasError(): Promise<boolean> {
    return this.page
      .locator('.bg-red-50, .bg-red-900\\/30')
      .first()
      .isVisible({ timeout: 2000 })
      .catch(() => false);
  }
}
