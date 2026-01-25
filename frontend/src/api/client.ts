import type {
  RouteExpandRequest,
  RouteExpandResponse,
  RouteRequest,
  RouteResponse,
  Segment,
} from './types'

async function fetchJson<T>(input: RequestInfo, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const response = await fetch(input, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
    signal,
  })

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : null

  if (!response.ok) {
    if (payload && typeof payload === 'object') {
      const detail = (payload as { detail?: string; error?: { message?: string } })
      const message = detail.detail ?? detail.error?.message
      if (message) {
        throw new Error(message)
      }
    }
    throw new Error(`Request failed: ${response.status}`)
  }

  return payload as T
}

export function fetchRoute(request: RouteRequest, signal?: AbortSignal): Promise<RouteResponse> {
  return fetchJson<RouteResponse>('/v1/route', {
    method: 'POST',
    body: JSON.stringify(request),
  }, signal)
}

export function expandSegments(
  segments: Segment[],
  signal?: AbortSignal,
): Promise<RouteExpandResponse> {
  const payload: RouteExpandRequest = {
    segments: segments.map((segment) => ({
      start: segment.start,
      end: segment.end,
    })),
  }
  return fetchJson<RouteExpandResponse>('/v1/route/expand', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, signal)
}
