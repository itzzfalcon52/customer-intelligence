import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, parseSse, streamPost } from './api';
afterEach(() => vi.unstubAllGlobals());

function streamOf(chunks: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe('assistant event stream', () => {
  it('keeps partial events until their terminator arrives', () => {
    const first = parseSse(
      'event: tool_start\ndata: {"type":"tool_start"}\n\ndata: {"ty',
    );
    expect(first.events).toEqual([{ type: 'tool_start' }]);
    expect(parseSse(first.rest + 'pe":"answer"}\n\n').events).toEqual([
      { type: 'answer' },
    ]);
    expect(parseSse(': keep-alive\n\n').events).toEqual([]);
  });
  it('reports steps across chunk boundaries and resolves with the answer', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(
          streamOf([
            'event: model_start\ndata: {"type":"model_start","name":"assistant"}\n\nevent: tool_',
            'start\ndata: {"type":"tool_start","name":"read_run"}\n\n: keep-alive\n\n',
            'event: answer\ndata: {"type":"answer","response":{"answer":"ok"}}\n\n',
          ]),
          { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
        ),
      );
    vi.stubGlobal('fetch', fetch);
    const seen: string[] = [];
    const final = await streamPost(
      '/api/v1/assistant/messages/stream',
      {},
      (e) => seen.push(e.type),
    );
    expect(seen).toEqual(['model_start', 'tool_start']);
    expect(final.response).toEqual({ answer: 'ok' });
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/assistant/messages/stream',
      expect.objectContaining({
        credentials: 'same-origin',
        redirect: 'error',
      }),
    );
  });
  it('turns an error event into an ApiError with the backend message', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            streamOf([
              'event: error\ndata: {"type":"error","status":404,"message":"Dataset not found."}\n\n',
            ]),
          ),
        ),
    );
    const error = await streamPost(
      '/api/v1/assistant/messages/stream',
      {},
      () => {},
    ).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).message).toBe('Dataset not found.');
  });
});
