/**
 * Common test helpers for E2E tests
 * Provides utility functions for page interactions and API mocking
 */
import { Page, Route, expect } from '@playwright/test';

const API_BASE = 'http://localhost:8000';

/**
 * Wait for the page to fully load:
 * - Network is idle (no pending requests)
 * - No loading spinners visible
 */
export async function waitForPageLoad(page: Page): Promise<void> {
  // Wait for network to settle
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {
    // networkidle may not fire if polling is active, so we continue
  });

  // Wait for any "Loading..." text to disappear
  const loadingText = page.locator('text=Loading...');
  if (await loadingText.isVisible({ timeout: 500 }).catch(() => false)) {
    await loadingText.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {
      // If still showing after 10s, continue anyway
    });
  }

  // Wait for any spinning loaders to disappear
  const spinner = page.locator('.animate-spin');
  if (await spinner.first().isVisible({ timeout: 500 }).catch(() => false)) {
    await spinner.first().waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {
      // Continue if spinner persists (could be intentional animation)
    });
  }
}

/**
 * Collect console errors during a test and fail if any are found.
 * Call at the start of a test to begin collecting, then call the returned
 * function at the end to assert no errors occurred.
 *
 * Returns a check function that asserts no console errors were logged.
 * Ignores known benign errors (e.g. favicon 404, React dev warnings).
 */
export function expectNoConsoleErrors(page: Page): () => void {
  const errors: string[] = [];

  const IGNORED_PATTERNS = [
    /favicon\.ico/,
    /Failed to load resource.*404/,
    /Warning:/,          // React dev warnings
    /DevTools/,
    /manifest\.json/,
    /ResizeObserver/,    // ResizeObserver loop errors (benign)
    /Error fetching/,    // API fetch errors (expected when external APIs not configured)
    /Invalid response format/, // Backend data format issues with external providers
    /Network Error/,     // Axios network errors when backend APIs are unavailable
    /AxiosError/,        // Axios error instances
    /ERR_CONNECTION/,    // Connection refused errors
    /Request failed/,    // Generic request failures from API calls
    /CORS/,              // CORS errors in test environment
    /AbortError/,        // Aborted requests during navigation
  ];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      const isIgnored = IGNORED_PATTERNS.some((pattern) => pattern.test(text));
      if (!isIgnored) {
        errors.push(text);
      }
    }
  });

  return () => {
    if (errors.length > 0) {
      throw new Error(
        `Console errors detected:\n${errors.map((e, i) => `  ${i + 1}. ${e}`).join('\n')}`
      );
    }
  };
}

/**
 * Wait for a specific API response to complete.
 * Returns the response data.
 */
export async function waitForApiResponse(
  page: Page,
  urlPattern: string | RegExp,
  options: { timeout?: number } = {}
): Promise<unknown> {
  const timeout = options.timeout || 10000;

  const response = await page.waitForResponse(
    (resp) => {
      const url = resp.url();
      if (typeof urlPattern === 'string') {
        return url.includes(urlPattern);
      }
      return urlPattern.test(url);
    },
    { timeout }
  );

  return response.json().catch(() => null);
}

/**
 * Intercept an API route and return mock data.
 * Matches requests to the backend API base URL.
 *
 * @param page - Playwright page
 * @param path - API path (e.g., '/api/v1/signals/')
 * @param response - Mock response body
 * @param options - Optional method filter and status code
 */
export async function mockApiRoute(
  page: Page,
  path: string,
  response: unknown,
  options: {
    method?: string;
    status?: number;
    contentType?: string;
  } = {}
): Promise<void> {
  const { method, status = 200, contentType = 'application/json' } = options;
  const fullUrl = `${API_BASE}${path}`;

  await page.route(fullUrl, async (route: Route) => {
    // Filter by method if specified
    if (method && route.request().method().toUpperCase() !== method.toUpperCase()) {
      await route.continue();
      return;
    }

    await route.fulfill({
      status,
      contentType,
      body: JSON.stringify(response),
    });
  });
}

/**
 * Mock multiple API routes at once.
 * Convenient for setting up a full page's API dependencies.
 */
export async function mockApiRoutes(
  page: Page,
  routes: Array<{
    path: string;
    response: unknown;
    method?: string;
    status?: number;
  }>
): Promise<void> {
  for (const route of routes) {
    await mockApiRoute(page, route.path, route.response, {
      method: route.method,
      status: route.status,
    });
  }
}

/**
 * Mock all API routes with glob pattern.
 * Useful for catching any unmocked API calls and returning a default response.
 */
export async function mockAllApiRoutes(
  page: Page,
  defaultResponse: unknown = { detail: 'Not mocked' },
  status: number = 200
): Promise<void> {
  await page.route(`${API_BASE}/api/**`, async (route: Route) => {
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(defaultResponse),
    });
  });
}

/**
 * Wait for navigation to complete after clicking a link.
 */
export async function clickAndWaitForNavigation(
  page: Page,
  selector: string,
  options: { timeout?: number } = {}
): Promise<void> {
  const timeout = options.timeout || 10000;
  await Promise.all([
    page.waitForURL('**/*', { timeout }),
    page.click(selector),
  ]);
}

/**
 * Get the current URL path (without base URL).
 */
export function getCurrentPath(page: Page): string {
  const url = new URL(page.url());
  return url.pathname;
}

/**
 * Assert that the navigation bar has the expected active link.
 */
export async function assertActiveNavLink(
  page: Page,
  expectedText: string
): Promise<void> {
  const activeLink = page.locator('nav a.bg-gray-900');
  await expect(activeLink).toContainText(expectedText);
}

/**
 * Take a screenshot with a descriptive name for debugging.
 */
export async function takeDebugScreenshot(
  page: Page,
  name: string
): Promise<void> {
  await page.screenshot({ path: `test-results/debug-${name}.png`, fullPage: true });
}

/**
 * Mock the WebSocket connection to prevent real-time price streaming.
 * The frontend uses a WebSocket for live price updates.
 */
export async function mockWebSocket(page: Page): Promise<void> {
  // Intercept WebSocket upgrade requests
  await page.route('**/ws/**', async (route) => {
    await route.abort();
  });
}

/**
 * Wait for a specific element to appear with text content.
 */
export async function waitForText(
  page: Page,
  text: string,
  options: { timeout?: number } = {}
): Promise<void> {
  const timeout = options.timeout || 10000;
  await page.locator(`text=${text}`).first().waitFor({ state: 'visible', timeout });
}

/**
 * Dismiss any confirm dialogs that appear (e.g., delete confirmations).
 */
export function autoAcceptDialogs(page: Page): void {
  page.on('dialog', async (dialog) => {
    await dialog.accept();
  });
}

/**
 * Dismiss any confirm dialogs by declining them.
 */
export function autoDeclineDialogs(page: Page): void {
  page.on('dialog', async (dialog) => {
    await dialog.dismiss();
  });
}
