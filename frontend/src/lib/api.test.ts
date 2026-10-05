import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AUTHENTICATION_EXPIRED_EVENT, currentUser, getAccessToken, signIn } from './api'

function storage() {
  const values = new Map<string, string>()
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) }
}

describe('authentication recovery', () => {
  beforeEach(() => {
    const target = new EventTarget()
    vi.stubGlobal('window', Object.assign(target, { sessionStorage: storage(), localStorage: storage() }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('clears an expired credential and requests re-authentication without clearing saved driver identity', async () => {
    window.sessionStorage.setItem('waypoint.access-token', 'expired')
    window.localStorage.setItem('waypoint.driver-profile', '{"id":"driver-1","role":"DRIVER"}')
    const expired = vi.fn()
    window.addEventListener(AUTHENTICATION_EXPIRED_EVENT, expired)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: { code: 'INVALID_TOKEN' } }), { status: 401 })))
    await expect(currentUser()).rejects.toMatchObject({ status: 401 })
    expect(getAccessToken()).toBeNull()
    expect(expired).toHaveBeenCalledOnce()
    expect(window.localStorage.getItem('waypoint.driver-profile')).toContain('driver-1')
  })

  it('does not clear a newer login when an older request returns 401', async () => {
    window.sessionStorage.setItem('waypoint.access-token', 'old')
    vi.stubGlobal('fetch', vi.fn(async () => {
      window.sessionStorage.setItem('waypoint.access-token', 'new')
      return new Response(JSON.stringify({ detail: { code: 'INVALID_TOKEN' } }), { status: 401 })
    }))
    const expired = vi.fn()
    window.addEventListener(AUTHENTICATION_EXPIRED_EVENT, expired)
    await expect(currentUser()).rejects.toMatchObject({ status: 401 })
    expect(getAccessToken()).toBe('new')
    expect(expired).not.toHaveBeenCalled()
  })

  it('keeps invalid login separate from session expiry', async () => {
    const expired = vi.fn()
    window.addEventListener(AUTHENTICATION_EXPIRED_EVENT, expired)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: { code: 'INVALID_CREDENTIALS' } }), { status: 401 })))
    await expect(signIn('driver@example.test', 'wrong')).rejects.toMatchObject({ code: 'INVALID_CREDENTIALS' })
    expect(expired).not.toHaveBeenCalled()
  })
})
