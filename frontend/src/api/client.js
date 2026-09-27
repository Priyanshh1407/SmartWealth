import { API_BASE_URL, API_ORIGIN } from '../config';

export class ApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

async function responsePayload(response) {
  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json();
  const text = await response.text();
  return text ? { detail: text } : null;
}

async function checkedResponse(response) {
  const payload = await responsePayload(response);
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === 'string'
      ? detail
      : `Request failed with status ${response.status}.`;
    throw new ApiError(message, response.status, detail || payload);
  }
  return payload;
}

export async function apiRequest(
  path,
  { method = 'GET', body, headers = {}, signal } = {},
) {
  const requestHeaders = {
    Accept: 'application/json',
    ...headers,
  };
  const options = { method, headers: requestHeaders, signal };
  if (body !== undefined) {
    requestHeaders['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  return checkedResponse(response);
}

export async function healthCheck({ signal } = {}) {
  const response = await fetch(`${API_ORIGIN}/`, {
    headers: { Accept: 'application/json' },
    signal,
  });
  if (!response.ok) throw new ApiError('Backend health check failed.', response.status);
  return response.json();
}

export function parseSseFrame(frame) {
  const result = { event: 'message', id: null, data: null };
  const dataLines = [];
  for (const line of frame.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    const value = separator === -1
      ? ''
      : line.slice(separator + 1).replace(/^ /, '');
    if (field === 'event') result.event = value;
    if (field === 'id') result.id = value;
    if (field === 'data') dataLines.push(value);
  }
  if (dataLines.length) result.data = JSON.parse(dataLines.join('\n'));
  return result;
}

export async function consumeSseStream(response, onEvent) {
  if (!response.body) throw new ApiError('Streaming response body is unavailable.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replace(/\r\n/g, '\n');
    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseSseFrame(frame);
      if (parsed.data !== null) onEvent(parsed);
      boundary = buffer.indexOf('\n\n');
    }
    if (done) break;
  }
}

export async function streamRun(runId, { onEvent, signal }) {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/events`, {
    headers: {
      Accept: 'text/event-stream',
    },
    signal,
  });
  if (!response.ok) await checkedResponse(response);
  await consumeSseStream(response, onEvent);
}
