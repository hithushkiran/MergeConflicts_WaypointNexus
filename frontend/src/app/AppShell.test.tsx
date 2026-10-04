import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import AppShell from './AppShell'
import { allowedPage, rolePages } from '../lib/navigation'
import type { UserProfile, UserRole } from '../lib/api'

const user: UserProfile = { id: 'store-1', email: 'store@example.test', display_name: 'Receiving Team', role: 'STORE', outlet_id: 'OUT-1', depot_code: null }
describe('shared role shell', () => {
  it('renders authenticated scope and accessible active store navigation', () => {
    const markup = renderToStaticMarkup(<AppShell user={user} page="orders" onNavigate={() => {}} onSignOut={() => {}}>Order content</AppShell>)
    expect(markup).toContain('Store Manager navigation')
    expect(markup).toContain('aria-current="page"')
    expect(markup).toContain('Outlet OUT-1')
    expect(markup).toContain('Skip to workspace')
    expect(markup).toContain('Open navigation')
    expect(markup).not.toContain('Telemetry')
    expect(markup).not.toContain('Live Sync')
    expect(markup).not.toContain('Settings')
  })
  it.each(['STORE', 'DISPATCHER', 'LOADER', 'DRIVER'] as UserRole[])('falls back to an allowed page for %s after account changes', role => {
    for (const page of ['orders', 'planning', 'loading', 'driver'] as const) {
      expect(rolePages[role].some(item => item.id === allowedPage(role, page))).toBe(true)
    }
  })
  it('preserves text meaning for receipt statuses', () => {
    const markup = renderToStaticMarkup(<AppShell user={{ ...user, role: 'DRIVER', outlet_id: null, depot_code: 'Peliyagoda' }} page="driver" onNavigate={() => {}} onSignOut={() => {}}>Offline · saved on this device</AppShell>)
    expect(markup).toContain('Driver navigation')
    expect(markup).toContain('Depot Peliyagoda')
    expect(markup).toContain('Offline · saved on this device')
    expect(markup).not.toContain('Create Order')
  })
})
