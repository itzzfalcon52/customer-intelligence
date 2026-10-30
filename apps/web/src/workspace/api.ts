export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export function safePath(path: string) {
  if (
    !/^\/api\/(v1|backend)\//.test(path) ||
    /(?:\.\.|\\|%2e|%2f|%5c)/i.test(path)
  )
    throw new Error('Invalid API path.');
  return path;
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(safePath(path), {
      ...options,
      credentials: 'same-origin',
      redirect: 'error',
      cache: 'no-store',
    });
  } catch {
    throw new ApiError(
      503,
      'The service could not be reached. Check that the API and account backend are running.',
    );
  }
  if (!response.ok) throw await failure(response);
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      502,
      'The service returned an unexpected response. Check that pnpm dev is running and try again.',
    );
  }
}
async function failure(response: Response) {
  const body = await response.json().catch(() => null);
  const detail = body?.message ?? body?.detail;
  return new ApiError(
    response.status,
    typeof detail === 'string'
      ? detail
      : `Request failed (${response.status}). Check your input and try again.`,
  );
}
export interface StreamEvent {
  type: string;
  [key: string]: unknown;
}
/** Split server-sent events; returns complete events and the unfinished remainder. */
export function parseSse(buffer: string) {
  const blocks = buffer.split('\n\n');
  const rest = blocks.pop() ?? '';
  const events: StreamEvent[] = [];
  for (const block of blocks) {
    const data = block
      .split('\n')
      .filter((line) => line.startsWith('data: '))
      .map((line) => line.slice(6))
      .join('\n');
    if (data) events.push(JSON.parse(data) as StreamEvent);
  }
  return { events, rest };
}
/** POST that consumes a server-sent event stream; resolves with the final answer event. */
export async function streamPost(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<StreamEvent> {
  let response: Response;
  try {
    response = await fetch(safePath(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'same-origin',
      redirect: 'error',
      cache: 'no-store',
      signal,
    });
  } catch {
    throw new ApiError(
      503,
      'The service could not be reached. Check that the API and account backend are running.',
    );
  }
  if (!response.ok || !response.body) throw await failure(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const parsed = parseSse(done ? buffer + '\n\n' : buffer);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      if (event.type === 'error')
        throw new ApiError(
          Number(event.status) || 502,
          String(event.message || 'The assistant failed.'),
        );
      if (event.type === 'answer') return event;
      onEvent(event);
    }
    if (done) break;
  }
  throw new ApiError(502, 'The assistant stream ended without an answer.');
}
export const post = <T>(path: string, body: unknown, signal?: AbortSignal) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
export async function download(path: string, filename: string) {
  const response = await fetch(safePath(path), {
    credentials: 'same-origin',
    redirect: 'error',
  });
  if (!response.ok)
    throw new ApiError(response.status, 'Download failed. Please try again.');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
/** Upload limits reported by the API (`/api/v1/capabilities`); these are its defaults. */
export interface UploadLimits {
  upload_mib: number;
  excel_mib: number;
  rows: number;
}
export const DEFAULT_LIMITS: UploadLimits = {
  upload_mib: 200,
  excel_mib: 50,
  rows: 1_000_000,
};
export function validateFile(
  file: File,
  limits: UploadLimits = DEFAULT_LIMITS,
) {
  if (!/\.(csv|xlsx)$/i.test(file.name))
    throw new Error('Choose a CSV or Excel (.xlsx) file.');
  const excel = /\.xlsx$/i.test(file.name);
  const mb = excel ? limits.excel_mib : limits.upload_mib;
  if (file.size > mb * 1024 * 1024)
    throw new Error(
      `${excel ? 'Excel files' : 'CSV files'} must be ${mb} MB or smaller.`,
    );
  if (!file.size) throw new Error('This file is empty.');
}
export const jobKey = () => crypto.randomUUID();
