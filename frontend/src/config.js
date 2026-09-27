const DEFAULT_API_BASE_URL = 'http://localhost:8000/api';

export function validateApiBaseUrl(value) {
  const candidate = (value || DEFAULT_API_BASE_URL).trim();
  let parsed;
  try {
    if (candidate.startsWith('/') && !candidate.startsWith('//')) {
      const origin = typeof window === 'undefined'
        ? 'http://localhost'
        : window.location.origin;
      parsed = new URL(candidate, origin);
    } else {
      parsed = new URL(candidate);
    }
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute URL or root-relative path.');
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('VITE_API_BASE_URL must use HTTP or HTTPS.');
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error('VITE_API_BASE_URL cannot contain credentials, query, or fragment.');
  }
  parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/api';
  return parsed.toString().replace(/\/$/, '');
}

export const API_BASE_URL = validateApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
);
export const API_ORIGIN = new URL(API_BASE_URL).origin;
