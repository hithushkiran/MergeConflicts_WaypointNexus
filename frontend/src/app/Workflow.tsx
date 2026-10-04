import { Button, Panel, StatusBadge } from './ui'

export function WorkflowSteps({ steps, active, onSelect }: { steps: string[]; active: number; onSelect: (step: number) => void }) {
  return <nav className="wp-workflow-steps" aria-label="Workflow steps">{steps.map((step, index) => <Button key={step} variant="secondary" aria-current={index === active ? 'step' : undefined} onClick={() => onSelect(index)}><span>{String(index + 1).padStart(2, '0')}</span>{step}</Button>)}</nav>
}

export function WorkflowStats({ values }: { values: Record<string, string | number> }) {
  return <div className="wp-stats">{Object.entries(values).map(([label, value]) => <Panel key={label}><strong className="wp-stat-value">{value}</strong><p className="wp-muted">{label}</p></Panel>)}</div>
}

export function DriverSyncStatus({ online, pending, syncing, completed }: { online: boolean; pending: number; syncing: boolean; completed: boolean }) {
  return <Panel className={pending ? 'wp-sync-pending' : 'wp-sync-record'} title={pending ? 'Saved on Device · Pending Sync' : completed ? 'Delivery Proof Synced' : 'Connection & Local Queue'}>
    <StatusBadge status={pending ? 'PENDING_SYNC' : online ? 'CONNECTED' : 'OFFLINE'} />
    <p className="wp-muted">{pending ? `${pending} update${pending === 1 ? '' : 's'} saved locally. Unsynced proof is not yet available to the store or dispatcher.` : completed ? 'The server-confirmed delivery record is available to store receiving and operations.' : 'Assigned trips and acknowledged manifests are cached on this device while connected.'}</p>
    {syncing && <p role="status">Synchronizing saved updates…</p>}
  </Panel>
}
