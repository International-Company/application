/** عميل الـ API: جلسة بكعكة، ورمز CSRF لكل طلب كتابة. */

export class ApiError extends Error {
  code: string
  status: number
  constructor(message: string, code: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

function readCookie(name: string): string {
  const match = document.cookie.match(new RegExp('(^|;\s*)' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[2]) : ''
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  if (method !== 'GET' && method !== 'HEAD') {
    headers['X-CSRFToken'] = readCookie('csrftoken')
  }

  const response = await fetch(`/api/v1${path}`, {
    ...init,
    method,
    headers,
    credentials: 'same-origin',
  })

  if (response.status === 204) return undefined as T

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (!response.ok) {
    const payload = body as { error?: { code?: string; message?: string }; detail?: string } | null
    throw new ApiError(
      payload?.error?.message ?? payload?.detail ?? 'request failed',
      payload?.error?.code ?? 'http_error',
      response.status,
    )
  }
  return body as T
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, data?: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(data ?? {}) }),
  patch: <T,>(path: string, data: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(data) }),
  del: <T,>(path: string) => request<T>(path, { method: 'DELETE' }),
  /** يضع كعكة CSRF قبل أول طلب كتابة. */
  ensureCsrf: () => request<{ csrf_token: string }>('/admin/auth/csrf'),
}
