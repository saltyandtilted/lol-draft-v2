// Small fetch wrapper: turns the backend's JSON errors ({error, message}) into readable exceptions.

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message)
    this.code = code
    this.status = status
  }
}

export async function api(path, { body, ...options } = {}) {
  let response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Backend unreachable – start it with backend\\.venv\\Scripts\\python backend\\run.py', 'offline', 0)
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 502 || response.status === 504 || !data) {
      throw new ApiError('Backend unreachable – start it with backend\\.venv\\Scripts\\python backend\\run.py', 'offline', response.status)
    }
    throw new ApiError(data.message || `HTTP ${response.status}`, data.error, response.status)
  }
  return data
}
