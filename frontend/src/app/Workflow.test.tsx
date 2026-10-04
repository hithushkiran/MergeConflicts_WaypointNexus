import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { DriverSyncStatus, WorkflowStats, WorkflowSteps } from './Workflow'
import { DispatcherWorkspace, LoaderWorkspace } from './App'

describe('role workflow presentation', () => {
  it('announces the active workflow step without claiming completed actions', () => {
    const markup = renderToStaticMarkup(<WorkflowSteps steps={['Route', 'Checklist', 'Exception', 'Manifest']} active={2} onSelect={() => {}} />)
    expect(markup).toContain('aria-current="step"')
    expect(markup).toContain('Exception')
    expect(markup).not.toContain('Completed')
  })
  it('renders supplied metrics without a hard-coded demo payload', () => {
    const markup = renderToStaticMarkup(<WorkflowStats values={{ Weight: '480 kg', Lines: 2 }} />)
    expect(markup).toContain('480 kg')
    expect(markup).not.toContain('500 kg')
  })
  it('makes unsynced delivery visibility explicit', () => {
    const markup = renderToStaticMarkup(<DriverSyncStatus online={false} pending={1} syncing={false} completed={false} />)
    expect(markup).toContain('Pending Sync')
    expect(markup).toContain('not yet available to the store or dispatcher')
    expect(markup).not.toContain('Delivery Proof Synced')
  })
  it('does not claim proof completion from an empty outbox alone', () => {
    const markup = renderToStaticMarkup(<DriverSyncStatus online pending={0} syncing={false} completed={false} />)
    expect(markup).toContain('Connection &amp; Local Queue')
    expect(markup).not.toContain('Delivery Proof Synced')
  })
  it('shows server-confirmed proof distinctly', () => {
    const markup = renderToStaticMarkup(<DriverSyncStatus online pending={0} syncing={false} completed />)
    expect(markup).toContain('Delivery Proof Synced')
    expect(markup).toContain('server-confirmed delivery record')
  })
  it('renders loader loading state instead of invented trips or dock sensors', () => {
    const markup = renderToStaticMarkup(<LoaderWorkspace />)
    expect(markup).toContain('Loading published trips')
    expect(markup).toContain('Revised Manifest')
    expect(markup).not.toContain('VEH035')
    expect(markup).not.toContain('Live Sync 12ms')
  })
  it('renders dispatcher stages and zero queue values before data loads', () => {
    const markup = renderToStaticMarkup(<DispatcherWorkspace />)
    expect(markup).toContain('Confirmed Orders')
    expect(markup).toContain('Deferral Review')
    expect(markup).toContain('Confirm Assignment')
    expect(markup).not.toContain('500 kg')
    expect(markup).not.toContain('OUT001')
  })
})
