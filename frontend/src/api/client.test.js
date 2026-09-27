import { describe, expect, it } from 'vitest';
import { consumeSseStream, parseSseFrame } from './client';
import { validateApiBaseUrl } from '../config';

describe('API configuration and SSE parsing', () => {
  it('normalizes safe API URLs and rejects credential-bearing URLs', () => {
    expect(validateApiBaseUrl('https://api.example.com/api/')).toBe('https://api.example.com/api');
    expect(() => validateApiBaseUrl('https://user:pass@example.com/api')).toThrow(/credentials/i);
    expect(validateApiBaseUrl('/api')).toMatch(/\/api$/);
    expect(() => validateApiBaseUrl('api')).toThrow(/absolute URL or root-relative/i);
    expect(() => validateApiBaseUrl('//evil.example/api')).toThrow();
  });

  it('parses named event frames', () => {
    expect(parseSseFrame('id: 2\nevent: delta\ndata: {"status":"running"}')).toEqual({
      event: 'delta',
      id: '2',
      data: { status: 'running' },
    });
  });

  it('handles event frames split across network chunks', async () => {
    const encoder = new TextEncoder();
    const response = new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: snap'));
        controller.enqueue(encoder.encode('shot\ndata: {"status":"queued"}\n\n'));
        controller.close();
      },
    }));
    const events = [];

    await consumeSseStream(response, (event) => events.push(event));

    expect(events).toEqual([{
      event: 'snapshot',
      id: null,
      data: { status: 'queued' },
    }]);
  });
});
