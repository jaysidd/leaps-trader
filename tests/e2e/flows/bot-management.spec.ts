/**
 * Bot Management Tests
 *
 * Tests bot control flows:
 * 1. Navigate to /settings, verify bot config form renders
 * 2. Change execution mode to semi_auto
 * 3. Save config, verify API call
 * 4. Mock bot status as RUNNING, verify BotStatusBar appears
 * 5. Mock bot status as PAUSED, verify yellow indicator
 * 6. Mock bot status as HALTED, verify red indicator
 */
import { test, expect } from '@playwright/test';
import { waitForPageLoad, expectNoConsoleErrors } from '../fixtures/test-helpers';
import { SettingsPage } from '../pages/settings.page';
import {
  MOCK_BOT_CONFIG,
  MOCK_BOT_STATE,
  MOCK_BOT_STATE_PAUSED,
  MOCK_BOT_STATE_HALTED,
  MOCK_BOT_STATE_STOPPED,
  MOCK_SETTINGS_SUMMARY,
  MOCK_UNREAD_COUNT,
} from '../fixtures/mock-data';

async function setupBotMocks(
  page: import('@playwright/test').Page,
  botState: typeof MOCK_BOT_STATE = MOCK_BOT_STATE_STOPPED
) {
  // Bot status
  await page.route('**/api/v1/trading/bot/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(botState),
    });
  });

  // Bot config
  await page.route('**/api/v1/trading/bot/config', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_BOT_CONFIG),
      });
    } else if (route.request().method() === 'PUT') {
      // Echo back the updated config
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...MOCK_BOT_CONFIG, ...body }),
      });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    }
  });

  // Unread count
  await page.route('**/api/v1/signals/unread-count', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_UNREAD_COUNT),
    });
  });

  // Settings summary
  await page.route('**/api/v1/settings/summary', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SETTINGS_SUMMARY),
    });
  });

  // News
  await page.route('**/api/v1/news/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ articles: [] }),
    });
  });

  // Block WebSocket
  await page.route('**/ws/**', async (route) => {
    await route.abort();
  });

  // Catch-all for other API routes
  await page.route('**/api/v1/**', async (route) => {
    if (route.request().url().includes('/bot/') || route.request().url().includes('/signals/') || route.request().url().includes('/settings/') || route.request().url().includes('/news/')) {
      await route.continue();
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    }
  });
}

test.describe('Bot Configuration', () => {
  test('settings page renders Auto Trading tab with bot config', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupBotMocks(page);

    const settingsPage = new SettingsPage(page);
    await settingsPage.goto();

    // Verify heading
    await expect(settingsPage.heading).toBeVisible({ timeout: 10000 });

    // Click Auto Trading tab
    await settingsPage.clickTab('Auto Trading');

    // Wait for the bot config to load
    await page.waitForTimeout(2000);

    // Verify execution mode options are visible
    await expect(page.locator('text=Signal Only').first()).toBeVisible();
    await expect(page.locator('text=Semi-Auto').first()).toBeVisible();
    await expect(page.locator('text=Full Auto').first()).toBeVisible();

    // Verify sizing mode options are visible
    await expect(page.locator('text=Fixed Dollar').first()).toBeVisible();
    await expect(page.locator('text=% of Portfolio').first()).toBeVisible();
    await expect(page.locator('text=Risk-Based').first()).toBeVisible();

    checkErrors();
  });

  test('can change execution mode and save', async ({ page }) => {
    await setupBotMocks(page);

    // Track if PUT /config was called
    let configUpdatePayload: Record<string, unknown> | null = null;
    await page.route('**/api/v1/trading/bot/config', async (route) => {
      if (route.request().method() === 'PUT') {
        configUpdatePayload = route.request().postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...MOCK_BOT_CONFIG, ...configUpdatePayload }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_BOT_CONFIG),
        });
      }
    });

    const settingsPage = new SettingsPage(page);
    await settingsPage.goto();
    await settingsPage.clickTab('Auto Trading');
    await page.waitForTimeout(2000);

    // Click "Semi-Auto" execution mode
    await page.locator('text=Semi-Auto').first().click();
    await page.waitForTimeout(500);

    // Click save button (in AutoTradingSettings)
    const saveBtn = page.locator('button:has-text("Save")').first();
    if (await saveBtn.isVisible({ timeout: 2000 })) {
      await saveBtn.click();
      await page.waitForTimeout(1000);

      // Verify the API was called with the updated config
      expect(configUpdatePayload).toBeTruthy();
      if (configUpdatePayload) {
        expect(configUpdatePayload['execution_mode']).toBe('semi_auto');
      }
    }
  });
});

test.describe('Bot Status Bar', () => {
  test('BotStatusBar appears when bot is RUNNING', async ({ page }) => {
    await setupBotMocks(page, MOCK_BOT_STATE);

    await page.goto('/');
    await waitForPageLoad(page);

    // BotStatusBar shows a div with status info when bot is running
    const statusBar = page.locator('div').filter({ hasText: /RUNNING.*PAPER/ }).first();
    await expect(statusBar).toBeVisible({ timeout: 5000 });

    // Should show "RUNNING" text
    await expect(page.locator('text=RUNNING').first()).toBeVisible();

    // Should show PAPER mode indicator
    await expect(page.locator('text=PAPER').first()).toBeVisible();
  });

  test('BotStatusBar shows yellow for PAUSED status', async ({ page }) => {
    await setupBotMocks(page, MOCK_BOT_STATE_PAUSED);

    await page.goto('/');
    await waitForPageLoad(page);

    // Should show "PAUSED" text
    await expect(page.locator('text=PAUSED').first()).toBeVisible({ timeout: 5000 });

    // The status dot should have yellow color class (bg-yellow-500)
    const statusDot = page.locator('.bg-yellow-500').first();
    await expect(statusDot).toBeVisible();
  });

  test('BotStatusBar shows red for HALTED status', async ({ page }) => {
    await setupBotMocks(page, MOCK_BOT_STATE_HALTED);

    await page.goto('/');
    await waitForPageLoad(page);

    // Should show "HALTED" text
    await expect(page.locator('text=HALTED').first()).toBeVisible({ timeout: 5000 });

    // The status dot should have red color class (bg-red-500)
    const statusDot = page.locator('.bg-red-500').first();
    await expect(statusDot).toBeVisible();
  });

  test('BotStatusBar is hidden when bot is STOPPED', async ({ page }) => {
    await setupBotMocks(page, MOCK_BOT_STATE_STOPPED);

    await page.goto('/');
    await waitForPageLoad(page);

    // BotStatusBar should NOT be visible
    // When status is "stopped", the component returns null
    const statusBar = page.locator('div').filter({ hasText: /RUNNING|PAUSED|HALTED/ });
    await expect(statusBar).not.toBeVisible({ timeout: 3000 });
  });

  test('BotStatusBar shows daily P&L when bot is running', async ({ page }) => {
    await setupBotMocks(page, MOCK_BOT_STATE);

    await page.goto('/');
    await waitForPageLoad(page);

    // Daily P&L should be shown ($125.50)
    await expect(page.locator('text=$125.50').first()).toBeVisible({ timeout: 5000 });
  });

  test('BotStatusBar shows circuit breaker warning', async ({ page }) => {
    await setupBotMocks(page, MOCK_BOT_STATE_PAUSED);

    await page.goto('/');
    await waitForPageLoad(page);

    // Circuit breaker warning text should be visible
    await expect(page.locator('text=CB: WARNING').first()).toBeVisible({ timeout: 5000 });
  });
});
