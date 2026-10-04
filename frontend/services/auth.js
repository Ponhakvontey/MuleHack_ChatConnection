import { reactive } from 'vue'

export const authState = reactive({ user: null, challenge: null, csrf: null, signingOut: false })
export const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export const backendUrl = path => new URL(path, apiBase || window.location.origin).href

export async function refreshCsrf() {
  const response = await fetch(backendUrl('/api/auth/csrf'), { credentials: 'include' })
  if (!response.ok) throw new Error('Unable to connect. Please try again.')
  authState.csrf = (await response.json()).csrf_token
}

export async function backendFetch(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (!authState.csrf) await refreshCsrf()
    headers.set('X-CSRF-Token', authState.csrf)
  }
  const response = await fetch(backendUrl(path), { ...options, headers, credentials: 'include' })
  if (response.status === 401 && !path.startsWith('/api/auth/')) {
    authState.user = null
    window.location.assign('/login')
    throw new Error('Your session has expired. Please sign in again.')
  }
  return response
}

export async function authRequest(path, body) {
  const response = await backendFetch('/api/auth/' + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'Unable to authenticate. Please try again.')
  if (data.csrf_token) authState.csrf = data.csrf_token
  if (data.user) authState.user = data.user
  return data
}

export async function refreshSession() {
  await refreshCsrf()
  const response = await backendFetch('/api/auth/me')
  const data = await response.json()
  if (!response.ok && response.status !== 401) throw new Error('Unable to check your session.')
  authState.user = data.authenticated ? data.user : null
  authState.challenge = data.challenge || null
  return authState
}

export async function logout() {
  if (authState.signingOut) return
  authState.signingOut = true
  try { await refreshCsrf(); await authRequest('logout', {}) }
  catch (error) { authState.signingOut = false; throw error }
  authState.user = null
  authState.challenge = null
  authState.csrf = null
  localStorage.removeItem('lastChatUser')
  // Reload also clears the previous chat's encryption keys, sockets and media.
  window.location.assign('/login')
}
