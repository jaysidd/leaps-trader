/**
 * Tests for the axios utility - cancellable requests and deduplication.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cancellableRequest, createAbortController } from '../api/axios';

// Mock axios module
vi.mock('axios', async () => {
  const actual = await vi.importActual('axios');
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    defaults: { headers: { common: {} } },
  };
  return {
    ...actual,
    default: {
      create: () => instance,
      isCancel: actual.default?.isCancel || (() => false),
    },
  };
});

describe('createAbortController', () => {
  it('returns controller and signal', () => {
    const { controller, signal } = createAbortController();
    expect(controller).toBeInstanceOf(AbortController);
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);
  });

  it('signal becomes aborted after abort()', () => {
    const { controller, signal } = createAbortController();
    controller.abort();
    expect(signal.aborted).toBe(true);
  });
});
