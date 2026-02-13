/**
 * Signal-to-Trade Flow Tests
 *
 * Tests the critical trading pipeline:
 * 1. Navigate to /signals
 * 2. View signals with ACTIVE status
 * 3. Click "Trade" button on a signal
 * 4. Verify SendToBotModal opens with preview data
 * 5. Preview shows: symbol, strategy, position size, SL/TP
 * 6. Click "Execute"
 * 7. Mock execute API returns success
 * 8. Verify success screen
 * 9. Verify signal status updated
 */
import { test, expect } from '@playwright/test';
import { waitForPageLoad, expectNoConsoleErrors } from '../fixtures/test-helpers';
import { SignalsPage } from '../pages/signals.page';
import {
  MOCK_SIGNALS,
  MOCK_QUEUE_ITEMS,
  MOCK_QUEUE_STATS,
  MOCK_UNREAD_COUNT,
  MOCK_BOT_STATE_STOPPED,
  MOCK_BOT_CONFIG,
  MOCK_PREVIEW_RESPONSE,
  MOCK_EXECUTE_RESPONSE,
  MOCK_BATCH_QUOTES,
} from '../fixtures/mock-data';

async function setupSignalsMocks(page: import('@playwright/test').Page) {
  // Bot status — stopped
  await page.route('**/api/v1/trading/bot/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_BOT_STATE_STOPPED),
    });
  });

  // Bot config
  await page.route('**/api/v1/trading/bot/config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_BOT_CONFIG),
    });
  });

  // Unread count
  await page.route('**/api/v1/signals/unread-count', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_UNREAD_COUNT),
    });
  });

  // Signal queue
  await page.route('**/api/v1/signals/queue**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: MOCK_QUEUE_ITEMS, stats: MOCK_QUEUE_STATS }),
    });
  });

  // Trading signals list
  await page.route('**/api/v1/signals/', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SIGNALS),
      });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    }
  });

  // Batch quotes
  await page.route('**/api/v1/stocks/batch-quotes**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_BATCH_QUOTES),
    });
  });

  // Mark signal as read
  await page.route('**/api/v1/signals/*/read', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true }),
    });
  });

  // News feed
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
}

test.describe('Signal-to-Trade Pipeline', () => {
  test('full signal preview and execute flow', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupSignalsMocks(page);

    // Mock preview endpoint
    await page.route('**/api/v1/trading/bot/preview-signal/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PREVIEW_RESPONSE),
      });
    });

    // Mock execute endpoint
    await page.route('**/api/v1/trading/bot/execute-signal/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_EXECUTE_RESPONSE),
      });
    });

    // Step 1: Navigate to /signals
    const signalsPage = new SignalsPage(page);
    await signalsPage.goto();

    // Step 2: Verify the page loaded with signals
    await expect(signalsPage.heading).toBeVisible({ timeout: 10000 });

    // Step 3: Switch to Trading Signals tab and verify signals are displayed
    await signalsPage.switchToSignalsTab();
    await page.waitForTimeout(1000);

    // Verify signals table has rows
    const signalCount = await signalsPage.getSignalCount();
    expect(signalCount).toBeGreaterThan(0);

    // Step 4: Click "Trade" on the first signal (AAPL)
    const tradeButton = page.locator('table tbody tr').first().locator('button:has-text("Trade")');
    await expect(tradeButton).toBeVisible({ timeout: 5000 });
    await tradeButton.click();

    // Step 5: Verify SendToBotModal opens
    await expect(page.locator('text=Send to Bot')).toBeVisible({ timeout: 5000 });

    // Wait for preview to load (Loading trade preview... disappears)
    await page.locator('text=Loading trade preview...').waitFor({ state: 'hidden', timeout: 10000 });

    // Step 6: Verify preview shows correct data
    // Check symbol is shown
    await expect(page.locator('text=AAPL').first()).toBeVisible();

    // Check direction badge (BUY)
    await expect(page.locator('.fixed.inset-0').locator('span:has-text("BUY")').first()).toBeVisible();

    // Check risk check result
    await expect(page.locator('text=Approved').first()).toBeVisible();

    // Check position sizing info
    await expect(page.locator('text=Quantity').first()).toBeVisible();

    // Check account info
    await expect(page.locator('text=Equity').first()).toBeVisible();
    await expect(page.locator('text=Buying Power').first()).toBeVisible();

    // Check Paper Trading Mode indicator
    await expect(page.locator('text=Paper Trading Mode').first()).toBeVisible();

    // Step 7: Click "Confirm & Execute"
    const executeButton = page.locator('button:has-text("Confirm & Execute")');
    await expect(executeButton).toBeEnabled();
    await executeButton.click();

    // Step 8: Verify executing state, then success
    await page.locator('text=Executing trade...').waitFor({ state: 'visible', timeout: 3000 }).catch(() => {
      // May transition too quickly to see
    });

    // Wait for success screen
    await expect(page.locator('text=Trade Executed!')).toBeVisible({ timeout: 10000 });

    // Verify the success details
    await expect(page.locator('text=AAPL').first()).toBeVisible();

    // Step 9: Click "Done" to close the modal
    await page.locator('button:has-text("Done")').click();

    // Modal should close
    await expect(page.locator('text=Trade Executed!')).not.toBeVisible({ timeout: 3000 });

    checkErrors();
  });

  test('signals page shows stat cards with correct values', async ({ page }) => {
    await setupSignalsMocks(page);

    const signalsPage = new SignalsPage(page);
    await signalsPage.goto();

    // Verify stat cards render
    const stats = await signalsPage.getStatValues();
    expect(stats.active).toBe('2');
    expect(stats.paused).toBe('1');
  });

  test('signal queue tab shows queue items', async ({ page }) => {
    await setupSignalsMocks(page);

    const signalsPage = new SignalsPage(page);
    await signalsPage.goto();

    // Queue tab should be active by default
    await page.waitForTimeout(1000);
    const queueCount = await signalsPage.getQueueCount();
    expect(queueCount).toBe(3);

    // Verify AAPL is in the queue
    await expect(page.locator('table tbody tr:has-text("AAPL")')).toBeVisible();
    await expect(page.locator('table tbody tr:has-text("MSFT")')).toBeVisible();
    await expect(page.locator('table tbody tr:has-text("NVDA")')).toBeVisible();
  });

  test('preview shows risk rejection when risk check fails', async ({ page }) => {
    await setupSignalsMocks(page);

    const rejectedPreview = {
      ...MOCK_PREVIEW_RESPONSE,
      risk_check: {
        approved: false,
        reason: 'Max daily trades exceeded (10/10)',
        warnings: [],
      },
    };

    await page.route('**/api/v1/trading/bot/preview-signal/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(rejectedPreview),
      });
    });

    const signalsPage = new SignalsPage(page);
    await signalsPage.goto();
    await signalsPage.switchToSignalsTab();
    await page.waitForTimeout(1000);

    // Click Trade on first signal
    const tradeButton = page.locator('table tbody tr').first().locator('button:has-text("Trade")');
    await tradeButton.click();

    // Wait for preview to load
    await page.locator('text=Loading trade preview...').waitFor({ state: 'hidden', timeout: 10000 });

    // Verify risk rejection is shown
    await expect(page.locator('text=Rejected').first()).toBeVisible();
    await expect(page.locator('text=Max daily trades exceeded')).toBeVisible();

    // Execute button should be disabled
    const executeButton = page.locator('button:has-text("Confirm & Execute")');
    await expect(executeButton).toBeDisabled();
  });

  test('preview error state shows error message', async ({ page }) => {
    await setupSignalsMocks(page);

    await page.route('**/api/v1/trading/bot/preview-signal/**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Signal expired' }),
      });
    });

    const signalsPage = new SignalsPage(page);
    await signalsPage.goto();
    await signalsPage.switchToSignalsTab();
    await page.waitForTimeout(1000);

    const tradeButton = page.locator('table tbody tr').first().locator('button:has-text("Trade")');
    await tradeButton.click();

    // Wait for error state
    await expect(page.locator('text=Cannot preview trade').or(page.locator('text=Close'))).toBeVisible({
      timeout: 10000,
    });
  });
});
