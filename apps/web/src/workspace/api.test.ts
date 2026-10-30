import { describe, expect, it, vi, afterEach } from 'vitest';
import { request, safePath, validateFile } from './api';
afterEach(() => vi.unstubAllGlobals());
describe('workspace access and upload boundaries', () => {
  it('never fetches external URLs or auth endpoints', () => {
    for (const path of [
      'https://outside.example/api/v1/data',
      '/api/auth/token',
      '/api/v1/../auth/token',
      '/api/v1/%2e%2e/file',
    ])
      expect(() => safePath(path)).toThrow();
    expect(safePath('/api/backend/organizations/o1/members')).toBe(
      '/api/backend/organizations/o1/members',
    );
  });
  it('uses same-origin cookies and refuses redirecting private data', async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response('[]', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetch);
    await request('/api/v1/datasets');
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/datasets',
      expect.objectContaining({
        credentials: 'same-origin',
        redirect: 'error',
        cache: 'no-store',
      }),
    );
  });
  it('preserves a backend ownership failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: 'Sign in to continue.' }), {
          status: 401,
        }),
      ),
    );
    await expect(request('/api/v1/datasets')).rejects.toMatchObject({
      status: 401,
      message: 'Sign in to continue.',
    });
  });
  it('rejects arbitrary binaries and oversized files before upload', () => {
    expect(() => validateFile(new File(['x'], 'model.joblib'))).toThrow();
    expect(() =>
      validateFile(
        new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'customers.csv'),
        { upload_mib: 2, excel_mib: 1, rows: 100 },
      ),
    ).toThrow();
    expect(() =>
      validateFile(new File([new Uint8Array(20 * 1024 * 1024)], 'kaggle.csv')),
    ).not.toThrow();
  });
});
