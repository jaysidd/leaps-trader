/**
 * Smoke Tests — Verify every page loads without errors
 *
 * Tests that all 11 routes render main content and have no console errors.
 * All API calls are mocked to avoid needing a real backend.
 */
import { test, expect } from '@playwright/test';
import { expectNoConsoleErrors, mockAllApiRoutes, waitForPageLoad } from '../fixtures/test-helpers';
import {
  MOCK_DASHBOARD,
  MOCK_SETTINGS_SUMMARY,
  MOCK_SIGNALS,
  MOCK_QUEUE_ITEMS,
  MOCK_QUEUE_STATS,
  MOCK_UNREAD_COUNT,
  MOCK_BOT_STATE_STOPPED,
  MOCK_BOT_CONFIG,
  MOCK_PERFORMANCE,
  MOCK_TODAY_PERFORMANCE,
  MOCK_DAILY_RECORDS,
  MOCK_EXIT_REASONS,
  MOCK_BACKTEST_LIST,
  MOCK_PORTFOLIO_SUMMARY,
  MOCK_POSITIONS,
  MOCK_BROKERS_STATUS,
  MOCK_BATCH_QUOTES,
  MOCK_ACCOUNT,
} from '../fixtures/mock-data';

// Common API mocks that most pages need (bot status, unread count, quotes)
async function setupCommonMocks(page: import('@playwright/test').Page) {
  // Catch-all for any unmocked API route — returns empty/default responses
  await mockAllApiRoutes(page, {});

  // Bot status — stopped so no BotStatusBar shows
  await page.route('**/api/v1/trading/bot/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_BOT_STATE_STOPPED),
    });
  });

  // Unread signal count — used by Navigation badge
  await page.route('**/api/v1/signals/unread-count', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_UNREAD_COUNT),
    });
  });

  // Batch quotes — used by several pages
  await page.route('**/api/v1/stocks/batch-quotes**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_BATCH_QUOTES),
    });
  });

  // News feed — for the global NewsTicker
  await page.route('**/api/v1/news/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ articles: [] }),
    });
  });

  // Block WebSocket connections
  await page.route('**/ws/**', async (route) => {
    await route.abort();
  });
}

test.describe('Smoke Tests — All Pages Load', () => {
  test('/ (Command Center) loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    // Mock Command Center specific endpoints
    await page.route('**/api/v1/command-center/dashboard**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DASHBOARD),
      });
    });

    await page.route('**/api/v1/command-center/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    });

    await page.goto('/');
    await waitForPageLoad(page);

    // The Command Center should be accessible at /
    await expect(page).toHaveURL(/\/(command-center)?$/);
    checkErrors();
  });

  test('/command-center loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.route('**/api/v1/command-center/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    });

    await page.goto('/command-center');
    await waitForPageLoad(page);

    checkErrors();
  });

  test('/screener loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.goto('/screener');
    await waitForPageLoad(page);

    // Screener should show a heading or content
    const content = page.locator('h1, h2, text=Screener').first();
    await expect(content).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/signals loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    // Mock signals-specific endpoints
    await page.route('**/api/v1/signals/queue**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: MOCK_QUEUE_ITEMS, stats: MOCK_QUEUE_STATS }),
      });
    });

    await page.route('**/api/v1/signals/', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_SIGNALS),
        });
      } else {
        await route.continue();
      }
    });

    await page.goto('/signals');
    await waitForPageLoad(page);

    await expect(page.locator('h1:has-text("Signal Processing")')).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/saved-scans loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.route('**/api/v1/saved-scans/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ scans: [] }),
      });
    });

    await page.goto('/saved-scans');
    await waitForPageLoad(page);

    const content = page.locator('h1, h2').first();
    await expect(content).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/portfolio loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    // Mock portfolio-specific endpoints
    await page.route('**/api/v1/portfolio/brokers/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_BROKERS_STATUS),
      });
    });

    await page.route('**/api/v1/portfolio/connections', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/portfolio/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PORTFOLIO_SUMMARY),
      });
    });

    await page.route('**/api/v1/portfolio/positions', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_POSITIONS),
      });
    });

    await page.route('**/api/v1/screener/batch-scores**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ scores: {} }),
      });
    });

    await page.goto('/portfolio');
    await waitForPageLoad(page);

    await expect(page.locator('h1:has-text("Portfolio")')).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/macro-intelligence loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.route('**/api/v1/macro/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    });

    await page.goto('/macro-intelligence');
    await waitForPageLoad(page);

    const content = page.locator('h1, h2').first();
    await expect(content).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/heatmap loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.goto('/heatmap');
    await waitForPageLoad(page);

    const content = page.locator('h1, h2').first();
    await expect(content).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/trade-journal loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.route('**/api/v1/trading/bot/trades**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/trade-journal');
    await waitForPageLoad(page);

    const content = page.locator('h1, h2').first();
    await expect(content).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/bot-performance loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.route('**/api/v1/trading/bot/performance', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PERFORMANCE),
      });
    });

    await page.route('**/api/v1/trading/bot/performance/daily**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DAILY_RECORDS),
      });
    });

    await page.route('**/api/v1/trading/bot/performance/exit-reasons**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_EXIT_REASONS),
      });
    });

    await page.route('**/api/v1/trading/bot/performance/today', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TODAY_PERFORMANCE),
      });
    });

    await page.goto('/bot-performance');
    await waitForPageLoad(page);

    await expect(page.locator('h1:has-text("Bot Performance")')).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/backtesting loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.route('**/api/v1/backtesting/list**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_BACKTEST_LIST),
      });
    });

    await page.goto('/backtesting');
    await waitForPageLoad(page);

    await expect(page.locator('h1:has-text("Backtesting")')).toBeVisible({ timeout: 10000 });
    checkErrors();
  });

  test('/settings loads without errors', async ({ page }) => {
    const checkErrors = expectNoConsoleErrors(page);
    await setupCommonMocks(page);

    await page.route('**/api/v1/settings/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SETTINGS_SUMMARY),
      });
    });

    await page.goto('/settings');
    await waitForPageLoad(page);

    await expect(page.locator('h1:has-text("Settings")')).toBeVisible({ timeout: 10000 });
    checkErrors();
  });
});

test.describe('Navigation', () => {
  test('navigation bar renders all expected links', async ({ page }) => {
    await setupCommonMocks(page);
    await page.goto('/');
    await waitForPageLoad(page);

    const nav = page.locator('nav');
    await expect(nav).toBeVisible();

    // Verify all expected nav links are present
    const expectedLinks = [
      'Command Center',
      'Screener',
      'Saved Scans',
      'Signals',
      'Portfolio',
      'Macro Intel',
      'Heat Map',
      'Journal',
      'Bot Stats',
      'Backtest',
      'Settings',
    ];

    for (const link of expectedLinks) {
      await expect(nav.locator(`a:has-text("${link}")`)).toBeVisible();
    }
  });

  test('clicking nav links navigates to correct pages', async ({ page }) => {
    await setupCommonMocks(page);

    // Mock all page-specific endpoints to prevent errors
    await page.route('**/api/v1/signals/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(route.request().url().includes('queue') ? { items: [], stats: { active: 0, paused: 0, total: 0 } } : []),
      });
    });

    await page.route('**/api/v1/settings/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SETTINGS_SUMMARY),
      });
    });

    await page.route('**/api/v1/backtesting/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/');
    await waitForPageLoad(page);

    // Navigate to Signals
    await page.locator('nav a:has-text("Signals")').click();
    await waitForPageLoad(page);
    await expect(page).toHaveURL(/\/signals/);

    // Navigate to Settings
    await page.locator('nav a:has-text("Settings")').click();
    await waitForPageLoad(page);
    await expect(page).toHaveURL(/\/settings/);

    // Navigate to Backtest
    await page.locator('nav a:has-text("Backtest")').click();
    await waitForPageLoad(page);
    await expect(page).toHaveURL(/\/backtesting/);
  });
});
