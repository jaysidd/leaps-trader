/**
 * SettingsPage — Page Object for the Settings (/settings) page
 *
 * Tabs: API Keys, Trading, Auto Trading, Screening Defaults,
 *       Performance, Features, Automation, System
 */
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class SettingsPage extends BasePage {
  readonly heading: Locator;
  readonly tabNav: Locator;
  readonly saveButton: Locator;

  constructor(page: Page) {
    super(page);
    this.heading = page.locator('h1:has-text("Settings")');
    this.tabNav = page.locator('nav.flex.space-x-8');
    this.saveButton = page.locator('button:has-text("Save Changes")');
  }

  /** Navigate to the Settings page */
  async goto(): Promise<void> {
    await this.navigateTo('/settings');
  }

  /** Click a settings tab by its label text */
  async clickTab(tabLabel: string): Promise<void> {
    await this.page.locator(`nav button:has-text("${tabLabel}")`).click();
    await this.page.waitForTimeout(500);
  }

  /** Get the bot configuration form values from the Auto Trading tab */
  async getBotConfig(): Promise<{
    executionMode: string | null;
    sizingMode: string | null;
  }> {
    await this.clickTab('Auto Trading');
    await this.waitForLoadingToFinish();

    // The Auto Trading tab renders AutoTradingSettings component
    // Execution mode and sizing mode are displayed as selectable cards/buttons

    // Get the currently selected execution mode
    const executionModes = this.page.locator('text=Signal Only, text=Semi-Auto, text=Full Auto');
    let executionMode: string | null = null;

    // Check which execution mode card has the selected styling (border-blue-500)
    for (const mode of ['signal_only', 'semi_auto', 'full_auto']) {
      const label = mode === 'signal_only' ? 'Signal Only' : mode === 'semi_auto' ? 'Semi-Auto' : 'Full Auto';
      const card = this.page.locator(`text=${label}`).first();
      if (await card.isVisible({ timeout: 1000 }).catch(() => false)) {
        // Check if this card's parent has the selected border
        const parent = card.locator('..');
        const classes = await parent.getAttribute('class');
        if (classes?.includes('border-blue-500') || classes?.includes('ring-2')) {
          executionMode = mode;
        }
      }
    }

    // Similarly for sizing mode
    let sizingMode: string | null = null;
    for (const mode of ['fixed_dollar', 'pct_portfolio', 'risk_based']) {
      const label = mode === 'fixed_dollar' ? 'Fixed Dollar' : mode === 'pct_portfolio' ? '% of Portfolio' : 'Risk-Based';
      const card = this.page.locator(`text=${label}`).first();
      if (await card.isVisible({ timeout: 1000 }).catch(() => false)) {
        const parent = card.locator('..');
        const classes = await parent.getAttribute('class');
        if (classes?.includes('border-blue-500') || classes?.includes('ring-2')) {
          sizingMode = mode;
        }
      }
    }

    return { executionMode, sizingMode };
  }

  /** Select an execution mode on the Auto Trading tab */
  async setExecutionMode(mode: 'signal_only' | 'semi_auto' | 'full_auto'): Promise<void> {
    await this.clickTab('Auto Trading');
    await this.waitForLoadingToFinish();

    const labels: Record<string, string> = {
      signal_only: 'Signal Only',
      semi_auto: 'Semi-Auto',
      full_auto: 'Full Auto',
    };

    const label = labels[mode];
    await this.page.locator(`text=${label}`).first().click();
  }

  /** Select a sizing mode on the Auto Trading tab */
  async setSizingMode(mode: 'fixed_dollar' | 'pct_portfolio' | 'risk_based'): Promise<void> {
    await this.clickTab('Auto Trading');
    await this.waitForLoadingToFinish();

    const labels: Record<string, string> = {
      fixed_dollar: 'Fixed Dollar',
      pct_portfolio: '% of Portfolio',
      risk_based: 'Risk-Based',
    };

    const label = labels[mode];
    await this.page.locator(`text=${label}`).first().click();
  }

  /** Click the "Save" button (shown at the bottom of the Auto Trading tab) */
  async clickSave(): Promise<void> {
    // The AutoTradingSettings has its own save button
    const saveBtn = this.page.locator('button:has-text("Save"), button:has-text("Save Changes")').first();
    await saveBtn.click();
  }

  /** Get values from the Automation tab */
  async getAutomationConfig(): Promise<{
    autoScanEnabled: boolean;
    autoProcessEnabled: boolean;
  }> {
    await this.clickTab('Automation');
    await this.page.waitForTimeout(500);

    // Check the toggle states
    // Auto-scan toggle is in "Enable Auto-Scan" section
    const autoScanSection = this.page.locator('text=Enable Auto-Scan').locator('..');
    const autoScanToggle = autoScanSection.locator('button[class*="rounded-full"]');
    const autoScanClasses = await autoScanToggle.getAttribute('class');
    const autoScanEnabled = autoScanClasses?.includes('bg-purple-600') ?? false;

    // Auto-process toggle is in "Auto-Process Results" section
    const autoProcessSection = this.page.locator('text=Auto-Process Results').locator('..');
    const autoProcessToggle = autoProcessSection.locator('button[class*="rounded-full"]');
    const autoProcessClasses = await autoProcessToggle.getAttribute('class');
    const autoProcessEnabled = autoProcessClasses?.includes('bg-purple-600') ?? false;

    return { autoScanEnabled, autoProcessEnabled };
  }

  /** Check if the Settings page has loaded (heading visible, tabs rendered) */
  async isLoaded(): Promise<boolean> {
    return this.heading.isVisible({ timeout: 5000 }).catch(() => false);
  }

  /** Check if the "Settings saved" success message is visible */
  async hasSaveSuccess(): Promise<boolean> {
    return this.page
      .locator('text=Settings saved successfully')
      .or(this.page.locator('text=saved'))
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false);
  }
}
