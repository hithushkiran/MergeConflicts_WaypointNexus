import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import StoreWorkspace from './StoreWorkspace'
import { StatusBadge } from './ui'

describe('store workspace capability boundaries', () => {
  it('offers order creation and reports loading without fabricated operational values', () => {
    const markup = renderToStaticMarkup(<StoreWorkspace user={{ id: 'store', email: 'store@example.test', role: 'STORE', display_name: 'Store Team', outlet_id: 'OUT-1', depot_code: null }} />)
    expect(markup).toContain('Create Order')
    expect(markup).toContain('Loading your orders…')
    expect(markup).toContain('OUT-1')
    expect(markup).toContain('Pre-delivery ETA and vehicle assignment are not provided')
    expect(markup).not.toContain('06:40')
    expect(markup).not.toContain('VEH035')
    expect(markup).not.toContain('Live Sync')
  })
  it.each(['CONFIRMED', 'PLANNED', 'DEFERRED', 'RECEIVED', 'DISPATCH_HOLD'])('renders %s as readable text, not color alone', status => {
    expect(renderToStaticMarkup(<StatusBadge status={status} />)).toContain(status.replace(/_/g, ' '))
  })
})
