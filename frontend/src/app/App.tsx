import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import StoreWorkspace from './StoreWorkspace'
import AppShell from './AppShell'
import { allowedPage, type WorkspacePage } from '../lib/navigation'
import { Alert, Button, Facts, PageHeading, Panel, StatusBadge } from './ui'
import { DriverSyncStatus, WorkflowStats, WorkflowSteps } from './Workflow'
import { receivingTime } from '../lib/receivingTime'
import DeliveryIssues from './DeliveryIssues'

import {
  ApiError,
  acknowledgeManifest,
  assignTripDriver,
  createDispatcherPlan,
  currentUser,
  getCachedDriverProfile,
  getDispatcherPlan,
  getAccessToken,
  listDispatcherOrders,
  listDispatcherDrivers,
  listDriverTrips,
  listDispatcherPlans,
  listLoaderTrips,
  listManifestVersions,
  listShortfalls,
  publishDispatcherPlan,
  resolveShortfall,
  signIn,
  signOut,
  submitLoadChecks,
  type DispatcherFilters,
  type DispatcherOrder,
  type DispatcherPlan,
  type DriverTrip,
  type LoaderTrip,
  type ShortfallItem,
  type UserProfile,
} from '../lib/api'
import {
  applyPendingCommands,
  cacheDriverTrips,
  enqueueDriverCommand,
  readCachedDriverTrips,
  readDriverOutbox,
  saveDeliveryDraft,
  syncDriverOutbox,
  type DriverCommandInput,
  type QueuedDriverCommand,
} from '../lib/driverOffline'

export function LoaderWorkspace() {
  const heading = useRef<HTMLElement>(null)
  const [step, setStep] = useState(0)
  useEffect(() => { heading.current?.querySelector('h1')?.focus() }, [step])
  const [loading, setLoading] = useState(true)
  const [trips, setTrips] = useState<LoaderTrip[]>([])
  const [manifestHistory, setManifestHistory] = useState<LoaderTrip['manifest'][]>([])
  const [selected, setSelected] = useState<string>('')
  const [statuses, setStatuses] = useState<Record<string, string>>({})
  const [quantities, setQuantities] = useState<Record<string, string>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [working, setWorking] = useState(false)

  async function refresh() {
    setLoading(true)
    try {
      const items = await listLoaderTrips()
      setTrips(items)
      setSelected((current) => items.some(item => item.id === current) ? current : items[0]?.id || '')
    } finally { setLoading(false) }
  }
  useEffect(() => { refresh().catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : 'Could not load trips.')) }, [])
  const trip = trips.find((item) => item.id === selected)
  const selectedTripId = trip?.id
  const selectedManifestVersion = trip?.manifest.version_number
  useEffect(() => {
    if (!selectedTripId) { setManifestHistory([]); return }
    listManifestVersions(selectedTripId).then(setManifestHistory).catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : 'Could not load manifest history.'))
  }, [selectedTripId, selectedManifestVersion])
  useEffect(() => { setStatuses({}); setQuantities({}); setNotes({}) }, [selectedTripId, selectedManifestVersion])
  const fieldClass = 'mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-50'

  async function saveChecks() {
    if (!trip) return
    setWorking(true); setError(''); setNotice('')
    try {
      await submitLoadChecks(trip.id, trip.manifest.version_number, trip.manifest.lines.map((line) => ({
        order_id: line.order_id,
        status: statuses[line.order_id] ?? (line.status === 'PENDING' ? 'LOADED' : line.status),
        quantity: Number(quantities[line.order_id] ?? line.expected_quantity),
        notes: notes[line.order_id] ?? line.notes,
      })))
      await refresh(); setNotice('Loading checks saved. Any shortage is now visible to the dispatcher.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not save checks.') }
    finally { setWorking(false) }
  }
  async function acknowledge() {
    if (!trip) return
    setWorking(true); setError('')
    try { await acknowledgeManifest(trip.manifest.id); await refresh(); setNotice('Manifest acknowledged; trip readiness has been updated.') }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not acknowledge manifest.') }
    finally { setWorking(false) }
  }

  const steps = ['Route Overview', 'Loading Checklist', 'Staging Exception', 'Revised Manifest']
  const blocked = trip?.status === 'DISPATCH_HOLD'
  return <section ref={heading} className="wp-operational wp-loader" aria-label="Loading operations">
    <PageHeading title={steps[step]} description="Verify the current manifest before acknowledging it for driver departure." actions={<Button variant="secondary" disabled={loading || working} onClick={() => { setError(''); void refresh().catch(cause => setError(cause instanceof ApiError ? cause.message : 'Could not refresh trips.')) }}>Refresh trips</Button>} />
    <WorkflowSteps steps={steps} active={step} onSelect={setStep} />
    {error && <Alert tone="error">{error}</Alert>}{notice && <Alert tone="success">{notice}</Alert>}
    {loading ? <Panel><p role="status">Loading published trips…</p></Panel> : !trip ? <Panel>No published trips are available for this depot.</Panel> : <>
      <Panel className="wp-context-strip"><label className="wp-muted">Published trip<select className={fieldClass} value={selected} onChange={event => { setSelected(event.target.value); setNotice(''); setError(''); setStep(0) }}>{trips.map(item => <option key={item.id} value={item.id}>{item.vehicle_id} · Trip {item.trip_number} · {item.status} · Plan V{item.plan_version}</option>)}</select></label>
        <Facts values={{ Vehicle: trip.vehicle_id, 'Manifest': 'V' + trip.manifest.version_number, 'Driver': trip.driver ?? 'Not supplied by loader API', 'Departure': trip.departure ? receivingTime(trip.departure) : 'Not supplied', 'Trip state': <StatusBadge status={trip.status} /> }} />
      </Panel>
      {blocked && <Alert tone="error"><strong>Departure Held — Dispatcher Decision Required</strong><p>The server blocks departure while the loading exception remains unresolved. There is no loader gate override.</p></Alert>}
      <WorkflowStats values={{ 'Shipment lines': trip.manifest.lines.length, 'Verified loaded lines': trip.manifest.lines.filter(line => line.status === 'LOADED').length, 'Manifest version': 'V' + trip.manifest.version_number, 'Acknowledgement': trip.manifest.acknowledged_at ? 'Recorded' : 'Required' }} />
      {step === 0 && <Panel title="Staged Manifest for Route"><div className="wp-shipment-list">{trip.manifest.lines.map(line => <article key={line.order_id}><div><strong>{line.load_sequence}. {line.order_ref}</strong><StatusBadge status={line.status} /></div><Facts values={{ Outlet: line.outlet_id, 'Expected': line.expected_quantity + ' units', 'Recorded loaded': line.loaded_quantity + ' units' }} /></article>)}</div><div className="wp-form-footer"><Button onClick={() => setStep(1)}>Open Loading Checklist</Button></div></Panel>}
      {step === 1 && <Panel title="Physical Manifest Verification"><p className="wp-muted">Enter actual units. Missing/damaged quantities describe affected units, not payload weight.</p><fieldset disabled={working || Boolean(trip.manifest.acknowledged_at)} className="wp-shipment-list">{trip.manifest.lines.map(line => <article key={line.order_id}>
        <div><strong>{line.load_sequence}. {line.order_ref}</strong><StatusBadge status={line.status} /></div><p className="wp-muted">{line.outlet_id} · expected {line.expected_quantity} units</p>
        <div className="wp-form-grid"><label>Result<select className={fieldClass} value={statuses[line.order_id] ?? (line.status === 'PENDING' ? 'LOADED' : line.status)} onChange={event => setStatuses(state => ({ ...state, [line.order_id]: event.target.value }))}><option>LOADED</option><option>MISSING</option><option>DAMAGED</option><option>SUBSTITUTE</option></select></label>
        <label>Quantity (loaded or affected units)<input className={fieldClass} min="0" max={line.expected_quantity} step="1" type="number" value={quantities[line.order_id] ?? line.expected_quantity} onChange={event => setQuantities(state => ({ ...state, [line.order_id]: event.target.value }))} /></label>
        <label className="wp-wide">Notes<input className={fieldClass} maxLength={1000} value={notes[line.order_id] ?? ''} onChange={event => setNotes(state => ({ ...state, [line.order_id]: event.target.value }))} /></label></div></article>)}</fieldset>
        <div className="wp-form-footer"><Button disabled={working || Boolean(trip.manifest.acknowledged_at)} onClick={() => void saveChecks()}>Save Loading Checks</Button><Button variant="secondary" onClick={() => setStep(2)}>Review Staging Exceptions</Button></div></Panel>}
      {step === 2 && <div className="wp-two-column"><Panel title="Staging Exception & Departure Hold">{trip.manifest.lines.filter(line => line.status !== 'LOADED' && line.status !== 'PENDING').map(line => <article className="wp-exception-card" key={line.order_id}><strong>{line.order_ref}</strong><Facts values={{ Expected: line.expected_quantity + ' units', 'Recorded loaded': line.loaded_quantity + ' units', Result: line.status }} /><p className="wp-muted">{line.notes ?? 'No loading note recorded.'}</p></article>)}
        {!trip.manifest.lines.some(line => line.status !== 'LOADED' && line.status !== 'PENDING') && <p className="wp-muted">No exception lines in this manifest. Trip state remains authoritative; refresh after dispatcher review.</p>}</Panel>
        <Panel title="Dispatcher Handoff"><p className="wp-muted">Exceptions are saved to the dispatch queue. After a decision creates a revised manifest, verify its quantities and acknowledge that exact version.</p><div className="wp-form-footer"><Button onClick={() => setStep(3)}>Review Revised Manifest</Button></div></Panel></div>}
      {step === 3 && <div className="wp-two-column"><Panel title={'Current Manifest · V' + trip.manifest.version_number}><div className="wp-shipment-list">{trip.manifest.lines.map(line => <article key={line.order_id}><strong>{line.order_ref}</strong><Facts values={{ 'Approved units': line.expected_quantity, 'Recorded loaded units': line.loaded_quantity, 'Status': <StatusBadge status={line.status} /> }} /></article>)}</div>
        <h3 className="wp-section-label">Version Changes</h3><ul className="wp-history">{manifestHistory.slice(1).map((version, index) => {
          const previous = manifestHistory[index]
          const changes = version.lines.flatMap(line => {
            const before = previous.lines.find(item => item.order_id === line.order_id)
            return !before ? [line.order_ref + ' added'] : before.expected_quantity !== line.expected_quantity || before.status !== line.status ? [line.order_ref + ': ' + before.expected_quantity + ' ' + before.status + ' → ' + line.expected_quantity + ' ' + line.status] : []
          })
          for (const line of previous.lines) if (!version.lines.some(item => item.order_id === line.order_id)) changes.push(line.order_ref + ' removed')
          return <li key={version.id}>V{previous.version_number} → V{version.version_number}: {changes.join('; ') || 'No line changes'}</li>
        })}</ul>{manifestHistory.length < 2 && <p className="wp-muted">No previous revision is available.</p>}</Panel>
        <Panel title="Manifest Acknowledgement"><StatusBadge status={trip.status} /><p className="wp-muted">Acknowledgement is the supported readiness action. The server requires every line to be loaded and no blocking shortfall. Physical seals, dock sensors and gate hardware are not connected.</p><div className="wp-form-footer"><Button disabled={working || blocked || Boolean(trip.manifest.acknowledged_at) || trip.manifest.lines.some(line => line.status !== 'LOADED')} onClick={() => void acknowledge()}>{trip.manifest.acknowledged_at ? 'Manifest Acknowledged' : 'Acknowledge Current Manifest'}</Button><Button variant="secondary" onClick={() => setStep(1)}>Back to Checklist</Button></div></Panel></div>}
    </>}
  </section>
}

export function DriverWorkspace() {
  const heading = useRef<HTMLElement>(null)
  const [view, setView] = useState<'route' | 'stop' | 'proof' | 'sync'>('route')
  useEffect(() => { heading.current?.querySelector('h1')?.focus() }, [view])
  const [selectedStop, setSelectedStop] = useState('')
  const [user] = useState<UserProfile | null>(() => getCachedDriverProfile())
  const [trips, setTrips] = useState<DriverTrip[]>([])
  const [receiver, setReceiver] = useState<Record<string, string>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [online, setOnline] = useState(() => typeof navigator === 'undefined' || navigator.onLine)
  const [serverConnected, setServerConnected] = useState(true)
  const [outbox, setOutbox] = useState<QueuedDriverCommand[]>([])
  const [syncing, setSyncing] = useState(false)
  const userId = user?.id

  const refresh = useCallback(async () => {
    if (!userId) return
    let freshTrips: DriverTrip[] = []
    let hadNetworkError = false
    try {
      freshTrips = await listDriverTrips()
      setServerConnected(true)
      await cacheDriverTrips(userId, freshTrips)
    } catch {
      setServerConnected(false)
      hadNetworkError = true
      freshTrips = await readCachedDriverTrips(userId)
    }
    const queued = await readDriverOutbox(userId)
    setOutbox(queued)
    setTrips(applyPendingCommands(freshTrips, queued))
    const conflict = queued.find((entry) => entry.state === 'CONFLICT')
    const transientFailure = queued.find((entry) => entry.state === 'PENDING' && entry.error)
    if (conflict) setError(`A delivery update needs attention: ${conflict.error ?? 'the server could not accept the change.'}`)
    else if (transientFailure) setError(`A connection issue delayed sync. The update will retry automatically: ${transientFailure.error}`)
    else if (hadNetworkError && freshTrips.length === 0) setError('No saved trips are available offline. Open your assigned trips while connected to save them for offline use.')
    else if (!hadNetworkError) setError('')
  }, [userId])

  const sync = useCallback(async () => {
    if (!userId) return
    setSyncing(true)
    try {
      const result = await syncDriverOutbox(userId)
      setOutbox(result.pending)
      if (result.pending.some((entry) => entry.state === 'CONFLICT')) {
        const conflict = result.pending.find((entry) => entry.state === 'CONFLICT')
        setError(`A delivery update needs attention: ${conflict?.error ?? 'the server could not accept the change.'}`)
      } else if (result.pending.length === 0) setError('')
      await refresh()
      if (result.next_attempt_at && navigator.onLine) {
        window.setTimeout(() => { void sync() }, Math.max(500, result.next_attempt_at - Date.now()))
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Offline updates could not be saved.')
    } finally { setSyncing(false) }
  }, [refresh, userId])

  useEffect(() => {
    void refresh().then(() => { if (navigator.onLine) void sync() }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not open saved trips.'))
    const update = () => {
      setOnline(navigator.onLine)
      if (navigator.onLine) void sync()
    }
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update) }
  }, [refresh, sync, userId])

  async function queue(command: DriverCommandInput) {
    if (!userId) { setError('Sign in while connected once to enable offline delivery work.'); return }
    setWorking(true); setError('')
    try {
      await enqueueDriverCommand(userId, command)
      await refresh()
      if (navigator.onLine) void sync()
      return true
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save the delivery update offline.'); return false }
    finally { setWorking(false) }
  }
  const field = 'wp-input'
  const connected = online && serverConnected
  const selectedTrip = trips.find(trip => trip.stops.some(stop => stop.id === selectedStop))
  const stop = selectedTrip?.stops.find(item => item.id === selectedStop)
  const pendingProof = outbox.some(entry => entry.command.kind === 'COMPLETE' && 'stop_id' in entry.command && entry.command.stop_id === selectedStop)
  const completed = stop?.status === 'DELIVERED' && Boolean(stop.completed_at) && !pendingProof
  return <section ref={heading} className="wp-operational wp-driver" aria-label="Driver delivery workflow">
    <PageHeading title={view === 'route' ? 'Manifest & Route' : view === 'proof' ? 'Delivery Proof' : view === 'sync' ? 'Saved Updates & Sync' : 'Stop Detail'} description="Your assigned route and latest acknowledged manifest." actions={view !== 'route' && <Button variant="secondary" onClick={() => setView('route')}>Back to Route</Button>} />
    {error && <Alert tone="error">{error}</Alert>}
    {(view === 'route' || view === 'sync') && <><DriverSyncStatus online={connected} pending={outbox.length} syncing={syncing} completed={completed} /><div className="wp-driver-sync-action"><Button variant="secondary" disabled={!online || syncing} onClick={() => void sync()}>{syncing ? 'Syncing…' : 'Sync Now'}</Button>{view !== 'sync' && <Button variant="secondary" onClick={() => setView('sync')}>View Saved Updates</Button>}</div></>}
    {view === 'sync' && <><Panel title="Local Queue Monitor">{outbox.length === 0 ? <p className="wp-muted">No pending local updates. This alone does not confirm that a particular delivery has completed.</p> : <ul className="wp-history">{outbox.map(entry => <li key={entry.id}><strong>{entry.command.kind.replace(/_/g, ' ')}</strong> · <StatusBadge status={entry.state} /><p className="wp-muted">Command {entry.id}</p>{entry.error && <p>{entry.error}</p>}</li>)}</ul>}</Panel>{stop && <Panel title="Delivery Record"><Facts values={{ Order: stop.order_ref, Outlet: stop.outlet_id, Status: stop.status, 'Completion time': stop.completed_at ? new Date(stop.completed_at).toLocaleString('en-GB', { timeZone: 'Asia/Colombo' }) + ' Colombo' : 'Not yet recorded' }} /></Panel>}</>}
    {view === 'route' && (trips.length === 0 ? <Panel>No ready or active trips are assigned to you.</Panel> : trips.map(trip => <Panel key={trip.id} title={trip.vehicle_id + ' · Trip ' + trip.trip_number}>
      <StatusBadge status={trip.status} /><Facts values={{ Origin: trip.depot_code ?? 'Not supplied', Destination: trip.district, Brand: trip.brand, 'Plan': 'V' + trip.plan_version, 'Approved manifest': 'V' + trip.manifest_version }} />
      {trip.manifest && <><h3 className="wp-section-label">Approved Delivery Lines</h3><div className="wp-shipment-list">{trip.manifest.lines.map(line => <article key={line.order_id}><strong>{line.order_ref}</strong><Facts values={{ Outlet: line.outlet_id, 'Approved': line.expected_quantity + ' units', 'Loaded': line.loaded_quantity + ' units', Status: line.status }} />{line.notes && <p className="wp-muted">{line.notes}</p>}</article>)}</div></>}
      {trip.status === 'READY' && <div className="wp-form-footer"><Button disabled={working} onClick={() => void queue({ kind: 'DEPART', trip_id: trip.id })}>Start Trip</Button></div>}
      <h3 className="wp-section-label">Route Stops · Planned ETAs</h3><ol className="wp-driver-stops">{trip.stops.map(item => <li key={item.id}><div><strong>{item.sequence_number}. {item.outlet_id}</strong><StatusBadge status={item.status} /></div><p className="wp-muted">{item.order_ref} · {item.district}</p><Button variant="secondary" onClick={() => { setSelectedStop(item.id); setView('stop') }}>View Stop</Button></li>)}</ol>
    </Panel>))}
    {(view === 'stop' || view === 'proof') && stop && selectedTrip && <>
      <Panel title={stop.outlet_id}><StatusBadge status={stop.status} /><p className="wp-muted">{stop.order_ref} · {selectedTrip.vehicle_id}</p><Facts values={{ 'Planned arrival': stop.planned_arrival ? new Date(stop.planned_arrival).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Colombo' }) + ' Colombo' : 'Not supplied', 'Receiving window': stop.window_open_time && stop.window_close_time ? stop.window_open_time + '–' + stop.window_close_time : 'Not supplied', Origin: selectedTrip.depot_code ?? 'Not supplied' }} />{stop.instructions && <Alert tone="warning">{stop.instructions}</Alert>}</Panel>
      <Panel title="Approved Handover Quantity">{selectedTrip.manifest?.lines.filter(line => line.order_id === stop.order_id).map(line => <div key={line.order_id}><Facts values={{ Order: line.order_ref, 'Expected': line.expected_quantity + ' units', 'Loaded': line.loaded_quantity + ' units' }} />{line.notes && <Alert tone="warning">{line.notes}</Alert>}</div>)}<p className="wp-muted">Quantities are shipment units. Store receiving records the actual intake; no product weights or signature capture are supplied by this driver API.</p></Panel>
      {view === 'stop' && <Panel title="Stop Actions">
        {selectedTrip.status === 'IN_PROGRESS' && stop.status === 'PENDING' && selectedTrip.stops.filter(item => item.sequence_number < stop.sequence_number).every(item => item.status === 'DELIVERED' || item.status === 'FAILED') ? <Button disabled={working} onClick={() => void queue({ kind: 'ARRIVE', trip_id: selectedTrip.id, stop_id: stop.id })}>Arrived at Stop</Button> : stop.status === 'PENDING' && <p className="wp-muted">Start the trip and complete earlier stops before recording arrival.</p>}
        {stop.status === 'ARRIVED' && <Button onClick={() => setView('proof')}>Record Delivery</Button>}
        {(stop.status === 'DELIVERED' || stop.status === 'FAILED') && <><p className="wp-muted">{pendingProof ? 'Saved locally; awaiting server synchronization.' : 'Server-confirmed ' + stop.status.toLowerCase() + ' outcome.'}</p><Button onClick={() => setView('sync')}>View Proof & Sync Status</Button></>}
      </Panel>}
      {view === 'proof' && stop.status === 'ARRIVED' && <Panel title="Recipient & Delivery Evidence"><div className="wp-form-grid">
        <label>Receiver name<input className={field} required maxLength={120} value={receiver[stop.id] ?? stop.receiver_name ?? ''} onChange={event => { const value = event.target.value; setReceiver(state => ({ ...state, [stop.id]: value })); if (userId) void saveDeliveryDraft(userId, selectedTrip.id, stop.id, value, notes[stop.id] ?? stop.delivery_notes ?? '') }} /></label>
        <label className="wp-wide">Delivery notes or failure reason<textarea className={field} maxLength={1000} rows={3} value={notes[stop.id] ?? stop.delivery_notes ?? ''} onChange={event => { const value = event.target.value; setNotes(state => ({ ...state, [stop.id]: value })); if (userId) void saveDeliveryDraft(userId, selectedTrip.id, stop.id, receiver[stop.id] ?? stop.receiver_name ?? '', value) }} /></label>
        </div><Alert>Proof is saved on this device first, then synchronized with the server. Photo/signature uploads are not supported.</Alert><div className="wp-form-footer"><Button disabled={working || !(receiver[stop.id] ?? stop.receiver_name ?? '').trim()} onClick={() => { void queue({ kind: 'COMPLETE', trip_id: selectedTrip.id, stop_id: stop.id, outcome: 'DELIVERED', receiver_name: (receiver[stop.id] ?? stop.receiver_name ?? '').trim(), notes: notes[stop.id] ?? stop.delivery_notes ?? '' }).then(saved => { if (saved) setView('sync') }) }}>Save Delivered Proof</Button><Button variant="secondary" disabled={working || !(notes[stop.id] ?? stop.delivery_notes ?? '').trim()} onClick={() => { void queue({ kind: 'COMPLETE', trip_id: selectedTrip.id, stop_id: stop.id, outcome: 'FAILED', receiver_name: (receiver[stop.id] ?? stop.receiver_name ?? '').trim(), notes: notes[stop.id] ?? stop.delivery_notes ?? '' }).then(saved => { if (saved) setView('sync') }) }}>Record Failed Delivery</Button></div></Panel>}
    </>}
  </section>
}

function ShortfallWorkspace() {
  const [items, setItems] = useState<ShortfallItem[]>([])
  const [publishedTrips, setPublishedTrips] = useState<Array<{ id: string; vehicle_id: string; trip_number: number; brand: string; district: string }>>([])
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [actions, setActions] = useState<Record<string, string>>({})
  const [resolutionQuantities, setResolutionQuantities] = useState<Record<string, string>>({})
  const [substitutes, setSubstitutes] = useState<Record<string, string>>({})
  const [targetTrips, setTargetTrips] = useState<Record<string, string>>({})
  const [candidatePlan, setCandidatePlan] = useState<DispatcherPlan | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [working, setWorking] = useState(false)
  async function refresh() {
    const [shortfalls, plans] = await Promise.all([listShortfalls(), listDispatcherPlans()])
    setItems(shortfalls)
    setPublishedTrips(plans.filter((plan) => plan.status === 'PUBLISHED').flatMap((plan) => plan.trips.map((trip) => ({
      id: trip.id, vehicle_id: trip.vehicle_id, trip_number: trip.trip_number, brand: trip.brand, district: trip.district,
    }))))
  }
  useEffect(() => { refresh().catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : 'Could not load shortfalls.')) }, [])
  async function resolve(item: ShortfallItem) {
    setWorking(true); setError(''); setNotice('')
    try {
      const action = actions[item.id] ?? 'RELOAD_FOUND'
      const result = await resolveShortfall(item.id, action, reasons[item.id] ?? '', action === 'PARTIAL_FULFILLMENT' ? Number(resolutionQuantities[item.id] ?? 0) : undefined, substitutes[item.id], targetTrips[item.id])
      if (result.candidate_plan_id) {
        setCandidatePlan(await getDispatcherPlan(result.candidate_plan_id))
        await refresh()
        setNotice('Review the capacity checked replacement plan below, then publish it to finish the reallocation.')
      } else {
        await refresh()
        setNotice(`${item.order_ref} resolved; revised manifest created.`)
      }
    }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not resolve this shortfall.') }
    finally { setWorking(false) }
  }
  async function openReallocationPlan(item: ShortfallItem) {
    if (!item.resolution_plan_version_id) return
    setWorking(true); setError('')
    try { setCandidatePlan(await getDispatcherPlan(item.resolution_plan_version_id)) }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not open the replacement plan.') }
    finally { setWorking(false) }
  }
  async function publishReallocation() {
    if (!candidatePlan) return
    setWorking(true); setError('')
    try {
      await publishDispatcherPlan(candidatePlan.id, crypto.randomUUID(), 'Dispatcher approved capacity checked reallocation')
      setCandidatePlan(null); await refresh(); setNotice(`Replacement plan V${candidatePlan.version_number} published. Loader manifests are revised and require acknowledgement.`)
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not publish the replacement plan.') }
    finally { setWorking(false) }
  }
  const fieldClass = 'mt-2 rounded border border-[#e5ebf2] bg-white px-3 py-2 text-[#10253d]'
  return <section className="wp-operational" aria-label="Shortfall decisions"><PageHeading title="Shortfall Exception Resolution" description="Review loading discrepancies and record an authorized operational decision." />
    {items.length === 0 ? <p className="mt-3 text-sm text-[#526477]">No open loading exceptions.</p> : <ul className="mt-3 space-y-3">{items.map((item) => <li key={item.id} className="rounded-lg border border-[#fde68a] bg-[#fffbeb] p-4">
      <p className="font-semibold">{item.order_ref} · {item.reason.toLowerCase()} · {item.quantity} units · {item.blocking ? 'dispatch hold' : 'nonblocking'}</p>
      {item.status === 'RESOLUTION_PENDING' ? <button className="mt-3 rounded-lg border border-[#d0e2ff] px-3 py-2 text-sm" disabled={working} onClick={() => openReallocationPlan(item)}>Review replacement plan</button> : <div className="mt-3 flex flex-wrap gap-2"><select aria-label={`Resolution for ${item.order_ref}`} className={fieldClass} value={actions[item.id] ?? 'RELOAD_FOUND'} onChange={(event) => setActions((state) => ({ ...state, [item.id]: event.target.value }))}><option value="RELOAD_FOUND">Reload found</option><option value="PARTIAL_FULFILLMENT">Accept partial quantity</option><option value="SUBSTITUTE">Substitute</option><option value="DEFER">Defer order</option><option value="REALLOCATION">Move order to another trip</option></select>{actions[item.id] === 'REALLOCATION' && <select aria-label={`Target trip for ${item.order_ref}`} className={fieldClass} value={targetTrips[item.id] ?? ''} onChange={(event) => setTargetTrips((state) => ({ ...state, [item.id]: event.target.value }))}><option value="">Choose compatible trip</option>{publishedTrips.filter((trip) => trip.id !== item.trip_id).map((trip) => <option key={trip.id} value={trip.id}>{trip.vehicle_id} · Trip {trip.trip_number} · {trip.brand} / {trip.district}</option>)}</select>}{actions[item.id] === 'PARTIAL_FULFILLMENT' && <input aria-label={`Accepted quantity for ${item.order_ref}`} className={fieldClass} min="0" max={item.quantity} type="number" placeholder="Accepted units" value={resolutionQuantities[item.id] ?? ''} onChange={(event) => setResolutionQuantities((state) => ({ ...state, [item.id]: event.target.value }))} />}{actions[item.id] === 'SUBSTITUTE' && <input aria-label={`Substitute for ${item.order_ref}`} className={fieldClass} placeholder="Substitute reference" value={substitutes[item.id] ?? ''} onChange={(event) => setSubstitutes((state) => ({ ...state, [item.id]: event.target.value }))} />}<input aria-label={`Resolution reason for ${item.order_ref}`} className={`${fieldClass} min-w-56 flex-1`} placeholder="Required reason" value={reasons[item.id] ?? ''} onChange={(event) => setReasons((state) => ({ ...state, [item.id]: event.target.value }))} /><button className="rounded-lg bg-[#1765c1] text-white px-4 py-2 font-bold  disabled:opacity-50" disabled={working || !(reasons[item.id] ?? '').trim() || (actions[item.id] === 'REALLOCATION' && !targetTrips[item.id])} onClick={() => resolve(item)}>{actions[item.id] === 'REALLOCATION' ? 'Build replacement plan' : 'Resolve and create V2'}</button></div>}
    </li>)}</ul>}{candidatePlan && <section className="mt-5 rounded-xl border border-[#d0e2ff] bg-white p-4" aria-label="Replacement plan review"><h3 className="font-bold">Replacement plan V{candidatePlan.version_number} · {candidatePlan.status}</h3><p className="mt-1 text-sm text-[#526477]">The planner checked vehicle capacity, fuel, route grouping, and delivery windows. Review the updated trips before publishing.</p><div className="mt-3 space-y-2">{candidatePlan.trips.map((trip) => <article className="rounded-lg border border-[#e5ebf2] p-3 text-sm" key={trip.id}><p className="font-semibold">{trip.vehicle_id} · Trip {trip.trip_number} · {trip.brand} / {trip.district}</p><p className="mt-1 text-xs text-[#526477]">{trip.metrics.weight_kg} kg · {trip.metrics.volume_m3} m³ · {trip.metrics.fuel_liters} L · {trip.metrics.duration_minutes} min</p><ol className="mt-2 list-inside list-decimal">{trip.stops.map((stop) => <li key={stop.order_id}>{stop.order_ref} · {stop.outlet_id}</li>)}</ol></article>)}</div><div className="mt-4 flex gap-2"><button className="rounded-lg bg-[#1765c1] text-white px-4 py-2 font-bold  disabled:opacity-50" disabled={working || candidatePlan.status !== 'DRAFT' || candidatePlan.trips.some((trip) => trip.metrics.time_windows_valid !== true)} onClick={publishReallocation}>{working ? 'Publishing…' : 'Publish replacement plan'}</button><button className="rounded-lg border border-[#e5ebf2] px-4 py-2" disabled={working} onClick={() => setCandidatePlan(null)}>Close review</button></div></section>}{error && <p role="alert" className="mt-3 text-sm text-[#9f1239]">{error}</p>}{notice && <p role="status" className="mt-3 text-sm text-[#147d64]">{notice}</p>}</section>
}

export function DispatcherWorkspace() {
  const heading = useRef<HTMLElement>(null)
  const [stage, setStage] = useState(0)
  useEffect(() => { heading.current?.querySelector('h1')?.focus() }, [stage])
  const steps = ['Confirmed Orders', 'Planning & Allocation', 'Deferral Review', 'Confirm Assignment']
  const [drivers, setDrivers] = useState<Array<{ id: string; display_name: string; email: string; depot_code: string | null }>>([])
  const [driverSelections, setDriverSelections] = useState<Record<string, string>>({})
  const [filters, setFilters] = useState<DispatcherFilters>({})
  const [orders, setOrders] = useState<DispatcherOrder[]>([])
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [savedPlans, setSavedPlans] = useState<DispatcherPlan[]>([])
  const [plan, setPlan] = useState<DispatcherPlan | null>(null)
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => { listDispatcherDrivers().then(setDrivers).catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : 'Could not load drivers.')) }, [])
  useEffect(() => {
    let active = true
    listDispatcherPlans().then(items => {
      if (active) setAvailableDates(current => [...new Set([...current, ...items.map(item => item.planning_date)])].sort())
    }).catch((cause: unknown) => { if (active) setError(cause instanceof ApiError ? cause.message : 'Could not load plan dates.') })
    return () => { active = false }
  }, [])

  async function assignDriver(tripId: string, driverId: string) {
    if (!driverId) return
    setWorking(true); setError(''); setNotice('')
    try {
      await assignTripDriver(tripId, driverId)
      if (plan) setPlan(await getDispatcherPlan(plan.id))
      setNotice('Driver assigned to the trip.')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not assign the driver.') }
    finally { setWorking(false) }
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    listDispatcherOrders(filters)
      .then((items) => {
        if (!active) return
        setOrders(items)
        if (!filters.planning_date && availableDates.length === 0) {
          setAvailableDates([...new Set(items.map((order) => order.requested_delivery_date))].sort())
        }
        if (!filters.planning_date && items.length > 0) {
          setFilters((current) => current.planning_date ? current : { ...current, planning_date: items[0].requested_delivery_date })
        }
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof ApiError ? cause.message : 'Could not load the dispatcher order queue.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [filters, availableDates.length])

  useEffect(() => {
    let active = true
    listDispatcherPlans(filters.planning_date)
      .then((items) => { if (active) setSavedPlans(items) })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof ApiError ? cause.message : 'Could not load saved plan versions.')
      })
    return () => { active = false }
  }, [filters.planning_date])

  function updateFilter<K extends keyof DispatcherFilters>(key: K, value: DispatcherFilters[K]) {
    setPlan(null)
    setError('')
    setNotice('')
    setFilters((current) => ({ ...current, [key]: value }))
  }

  async function makeCandidate() {
    if (!filters.planning_date) return
    setWorking(true)
    setError('')
    setNotice('')
    try {
      const candidate = await createDispatcherPlan(filters.planning_date, crypto.randomUUID())
      setPlan(candidate)
      setStage(1)
      setSavedPlans((current) => [candidate, ...current.filter((item) => item.id !== candidate.id)])
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not generate a plan candidate.')
    } finally {
      setWorking(false)
    }
  }

  async function publishPlan() {
    if (!plan) return
    setWorking(true)
    setError('')
    try {
      await publishDispatcherPlan(plan.id, crypto.randomUUID(), reason)
      const updated = await getDispatcherPlan(plan.id)
      setPlan(updated)
      setSavedPlans((current) => current.map((item) => item.id === updated.id ? updated : item))
      setNotice(`Plan V${plan.version_number} was published. Served and deferred orders are now recorded.`)
      setOrders(await listDispatcherOrders(filters))
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not publish this plan.')
    } finally {
      setWorking(false)
    }
  }

  const dateOptions = [...new Set([
    ...availableDates,
    ...savedPlans.map((saved) => saved.planning_date),
  ])].sort()
  const filterClass = 'mt-2 block w-full rounded-lg border border-[#e5ebf2] bg-white px-3 py-2 text-[#10253d]'
  const inputClass = 'rounded-lg border border-[#e5ebf2] bg-white px-3 py-2 text-[#10253d]'

  return (
    <section ref={heading} className="wp-operational wp-dispatcher" aria-label="Dispatcher planning">
      <PageHeading title={steps[stage]} description="Review eligible orders, generate a compliant plan, then publish its manifest." />
      <WorkflowSteps steps={steps} active={stage} onSelect={setStage} />
      <WorkflowStats values={{ 'Confirmed orders': orders.length, 'Combined weight': orders.reduce((sum, order) => sum + order.weight_kg, 0).toFixed(1) + ' kg', 'Combined volume': orders.reduce((sum, order) => sum + order.volume_m3, 0).toFixed(2) + ' m³', 'Van-only outlets': new Set(orders.filter(order => order.parking_constraint === 'VAN_ONLY').map(order => order.outlet_id)).size }} />
      <details className="wp-panel wp-filter-panel" open={stage === 0}><summary>Order Queue Filters</summary>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="text-sm text-[#10253d]">Delivery date
          <select className={filterClass} onChange={(event) => updateFilter('planning_date', event.target.value)} value={filters.planning_date ?? ''}>
            <option value="">All dates</option>
            {dateOptions.map((date) => <option key={date} value={date}>{date}</option>)}
          </select>
        </label>
        <label className="text-sm text-[#10253d]">Depot
          <select className={filterClass} onChange={(event) => updateFilter('depot', event.target.value)} value={filters.depot ?? ''}>
            <option value="">All depots</option><option>Peliyagoda</option><option>Kandy</option>
          </select>
        </label>
        <label className="text-sm text-[#10253d]">Brand
          <select className={filterClass} onChange={(event) => updateFilter('brand', event.target.value)} value={filters.brand ?? ''}>
            <option value="">All brands</option><option>Fresh</option><option>Style</option><option>Tech</option>
          </select>
        </label>
        <label className="text-sm text-[#10253d]">District
          <input className={filterClass} onChange={(event) => updateFilter('district', event.target.value)} placeholder="Any district" value={filters.district ?? ''} />
        </label>
        <label className="text-sm text-[#10253d]">Temperature
          <select className={filterClass} onChange={(event) => updateFilter('temperature', event.target.value as DispatcherFilters['temperature'])} value={filters.temperature ?? ''}>
            <option value="">Any temperature</option><option value="AMBIENT">Ambient</option><option value="CHILLED">Chilled</option><option value="FROZEN">Frozen</option>
          </select>
        </label>
        <label className="text-sm text-[#10253d]">Access rule
          <select className={filterClass} onChange={(event) => updateFilter('access', event.target.value)} value={filters.access ?? ''}>
            <option value="">Any access rule</option><option value="VAN_ONLY">Van only</option><option value="NONE">No restriction</option>
          </select>
        </label>
        <label className="text-sm text-[#10253d]">Delivery window
          <select className={filterClass} onChange={(event) => updateFilter('delivery_window', event.target.value as DispatcherFilters['delivery_window'])} value={filters.delivery_window ?? ''}>
            <option value="">Any window</option><option value="restricted">Has receiving window</option><option value="none">No receiving window</option>
          </select>
        </label>
        <label className="text-sm text-[#10253d]">Prior deferral
          <select className={filterClass} onChange={(event) => updateFilter('prior_deferral', event.target.value as DispatcherFilters['prior_deferral'])} value={filters.prior_deferral ?? ''}>
            <option value="">Any</option><option value="true">Previously deferred</option><option value="false">Not deferred before</option>
          </select>
        </label>
      </div>

      </details>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#e5ebf2] bg-[#f8fafc] p-4">
        <p className="text-sm text-[#526477]">{loading ? 'Loading orders…' : `${orders.length} confirmed order${orders.length === 1 ? '' : 's'} in this queue`}</p>
        <button className="rounded-lg bg-[#1765c1] text-white px-4 py-2.5 font-bold  disabled:opacity-50" disabled={working || loading || !filters.planning_date || orders.length === 0} onClick={makeCandidate} type="button">
          {working && !plan ? 'Building candidate…' : 'Generate candidate plan'}
        </button>
      </div>

      {savedPlans.length > 0 && <div className="mt-5">
        <h3 className="font-semibold">Saved plan versions</h3>
        <ul className="mt-2 flex flex-wrap gap-2">{savedPlans.map((saved) => <li key={saved.id}>
          <button className="rounded-lg border border-[#e5ebf2] px-3 py-2 text-left text-sm hover:border-cyan-500" onClick={() => { setError(''); getDispatcherPlan(saved.id).then(item => { setPlan(item); setStage(1) }).catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : 'Could not open this plan version.')) }} type="button">
            V{saved.version_number} · {saved.status} · {new Date(saved.created_at).toLocaleString()}
          </button>
        </li>)}</ul>
      </div>}

      {!loading && orders.length === 0 && <p className="mt-4 rounded-lg bg-[#f8fafc] p-4 text-sm text-[#526477]">No confirmed orders match these filters.</p>}
      {orders.length > 0 && stage === 0 && <Panel className="wp-table-panel"><div className="wp-table-heading"><h2>Orders Ready for Planning</h2><p>Keep temperature requirements separate; server eligibility rules remain authoritative.</p></div><div className="wp-table-scroll" role="region" aria-label="Confirmed orders table" tabIndex={0}><table className="wp-table"><caption className="sr-only">Confirmed orders ready for planning</caption><thead><tr><th scope="col">Order</th><th scope="col">Outlet</th><th scope="col">Temperature</th><th scope="col">Load</th><th scope="col">Window</th><th scope="col">Status</th></tr></thead><tbody>{orders.map(order => <tr key={order.id}><th scope="row"><code>{order.reference}</code></th><td>{order.outlet_id}<small>{order.brand} · {order.district}</small></td><td>{order.temperature_requirement}</td><td>{order.weight_kg} kg<small>{order.volume_m3} m³ · {order.units} units</small></td><td>{order.window_open_time && order.window_close_time ? order.window_open_time + '–' + order.window_close_time : 'No restricted window'}</td><td><StatusBadge status={order.status} /></td></tr>)}</tbody></table></div></Panel>}
      {stage > 0 && !plan && <Alert>Select a saved plan or generate a candidate to review this step.</Alert>}
      {stage === 2 && plan && <div className="wp-two-column"><Panel title="Authoritative Deferral Decisions"><p className="wp-muted">Reasons below are recorded by the planner. Manual deferral drafts and notification delivery are not supported by the current API.</p><div className="wp-shipment-list">{plan.orders.filter(item => item.decision === 'deferred').map(item => <article key={item.order_id}><strong>{item.order_ref}</strong><Facts values={{ Outlet: item.outlet_id ?? 'Not supplied', Reason: item.reason?.replace(/_/g, ' ') ?? 'Not supplied' }} />{item.notes && <p>{item.notes}</p>}</article>)}</div>{!plan.orders.some(item => item.decision === 'deferred') && <p className="wp-muted">No deferred orders in this candidate.</p>}</Panel><Panel title="Customer Impact & Recovery"><p className="wp-muted">No stock forecast, next delivery promise or messaging transmission is provided by the current plan API. Publish records the served/deferred decisions against each order.</p><div className="wp-form-footer"><Button onClick={() => setStage(3)}>Review Assignment</Button></div></Panel></div>}

      {plan && stage !== 0 && stage !== 2 && <section className="mt-8 rounded-xl border border-[#d0e2ff] bg-white p-5" aria-labelledby="candidate-heading">
        {plan.status === 'PUBLISHED' && <Alert>Metrics describe this original published allocation, not later loading revisions. Check Loading Decisions and the loader's current manifest for revised quantities.</Alert>}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase tracking-widest text-[#1765c1]">Plan V{plan.version_number} · {plan.status}</p><h3 id="candidate-heading" className="mt-1 text-xl font-bold">{stage === 3 ? 'Confirm Assignment & Release Manifest' : 'Planning and Allocation'} · {plan.planning_date}</h3></div>
          <div className="flex gap-4 text-sm"><span>{plan.orders.filter((item) => item.decision === 'served').length} served</span><span>{plan.orders.filter((item) => item.decision === 'deferred').length} deferred</span><span>{plan.trips.length} trips</span></div>
        </div>
        {plan.diagnostics.length > 0 && <ul className="mt-4 list-disc pl-5 text-sm text-[#92400e]">{plan.diagnostics.map((item) => <li key={item}>{item.replace(/_/g, ' ')}</li>)}</ul>}
        <div className="mt-5 space-y-4">
          {plan.trips.map((trip) => <article className="rounded-lg border border-[#e5ebf2] p-4" key={trip.id}>
            <h4 className="font-semibold">{trip.brand} · {trip.district} · {trip.vehicle_id} · Trip {trip.trip_number}</h4>
            <p className="mt-1 text-xs text-[#526477]">{trip.metrics.weight_kg} kg ({trip.metrics.weight_utilization_pct}% capacity) · {trip.metrics.volume_m3} m³ ({trip.metrics.volume_utilization_pct}% capacity) · {trip.metrics.distance_km} km · {trip.metrics.fuel_liters} L · {trip.metrics.duration_minutes} min</p>
            {plan.status === 'PUBLISHED' && <div className="mt-3 flex flex-wrap items-end gap-2"><label className="text-xs text-[#526477]">Driver for {trip.depot_code}<select className={`${inputClass} mt-1 block`} value={driverSelections[trip.id] ?? trip.assigned_driver_id ?? ''} onChange={(event) => setDriverSelections((state) => ({ ...state, [trip.id]: event.target.value }))}><option value="">Choose driver</option>{drivers.filter((driver) => driver.depot_code === trip.depot_code).map((driver) => <option key={driver.id} value={driver.id}>{driver.display_name}</option>)}</select></label><button className="rounded-lg border border-[#d0e2ff] px-3 py-2 text-sm disabled:opacity-50" disabled={working || !(driverSelections[trip.id] ?? trip.assigned_driver_id)} onClick={() => assignDriver(trip.id, driverSelections[trip.id] ?? trip.assigned_driver_id ?? '')}>{trip.assigned_driver_name ? `Assigned: ${trip.assigned_driver_name} · change` : 'Assign driver'}</button></div>}
            <div className="wp-utilization"><label>Weight utilization · {trip.metrics.weight_utilization_pct}%<progress max={100} value={Number(trip.metrics.weight_utilization_pct)} /></label><label>Volume utilization · {trip.metrics.volume_utilization_pct}%<progress max={100} value={Number(trip.metrics.volume_utilization_pct)} /></label></div>
            <ol className="mt-3 space-y-2 border-l border-[#e5ebf2] pl-4 text-sm">{trip.stops.map((stop) => <li key={stop.order_id}><strong>{stop.sequence_number}. {stop.order_ref}</strong> · {stop.outlet_id} · ETA {stop.planned_arrival ? new Date(stop.planned_arrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Colombo' }) : 'not set'} · {stop.planned_service_minutes} min service</li>)}</ol>
          </article>)}
        </div>
        <div className="mt-5 rounded-lg bg-[#f8fafc] p-4">
          <h4 className="font-semibold">Order decisions</h4>
          <ul className="mt-2 space-y-2 text-sm">{plan.orders.map((item) => <li key={item.order_id} className="flex flex-wrap justify-between gap-2">
            <span>{item.order_ref} · {item.outlet_id ?? '—'}</span>
            <span className={item.decision === 'deferred' ? 'text-[#92400e]' : 'text-[#147d64]'}>{item.decision}{item.vehicle_id ? ` · ${item.vehicle_id} / trip ${item.trip_number}` : ''}{item.reason ? ` · ${item.reason.replace(/_/g, ' ')}` : ''}</span>
          </li>)}</ul>
        </div>
        {plan.status === 'DRAFT' && stage === 3 && <div className="mt-5 flex flex-wrap items-end gap-3">
          <label className="min-w-64 flex-1 text-sm text-[#10253d]">Publication note (optional)
            <input className={`${inputClass} mt-2 block w-full`} maxLength={500} onChange={(event) => setReason(event.target.value)} value={reason} />
          </label>
          <button className="rounded-lg bg-[#1765c1] text-white px-5 py-2.5 font-bold  disabled:opacity-50" disabled={working || plan.trips.some((trip) => trip.metrics.time_windows_valid !== true)} onClick={publishPlan} type="button">{working ? 'Publishing…' : 'Confirm & Publish Manifest'}</button>
        </div>}
        {plan.status === 'DRAFT' && stage === 1 && <div className="wp-form-footer"><Button variant="secondary" onClick={() => setStage(2)}>Review Deferrals</Button><Button onClick={() => setStage(3)}>Continue to Assignment Review</Button></div>}
        {plan.status === 'PUBLISHED' && <p className="mt-5 rounded-lg bg-[#ebf8f4] p-3 text-sm text-[#147d64]">Published {plan.published_at ? new Date(plan.published_at).toLocaleString() : ''}. The published version is locked.</p>}
      </section>}

      {error && <p role="alert" className="mt-4 text-sm text-[#9f1239]">{error}</p>}
      {notice && <p role="status" className="mt-4 text-sm text-[#147d64]">{notice}</p>}
    </section>
  )
}

function App() {
  const [page, setPage] = useState<WorkspacePage>('orders')
  const [user, setUser] = useState<UserProfile | null>(null)
  const [checkingSession, setCheckingSession] = useState(() => Boolean(getAccessToken()))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!getAccessToken()) return

    let active = true
      currentUser()
      .then((profile) => {
        if (active) setUser(profile)
      })
      .catch((cause: unknown) => {
        const cachedProfile = getCachedDriverProfile()
        if (active && cachedProfile && (!(cause instanceof ApiError) || cause.status >= 500)) setUser(cachedProfile)
        else if (active) setError(cause instanceof ApiError ? cause.message : 'Could not restore your session.')
      })
      .finally(() => {
        if (active) setCheckingSession(false)
      })

    return () => {
      active = false
    }
  }, [])

  async function handleSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      setUser(await signIn(email, password))
      setPassword('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to connect to Waypoint Nexus.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSignOut() {
    setError('')
    try {
      await signOut()
    } catch {
      // The local credential is always cleared; a network outage should not retain the signed-in view.
    }
    setUser(null)
    setPage('orders')
  }

  if (checkingSession) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f3f7fb] px-6 text-[#10253d]">
        <p role="status" className="text-[#526477]">Restoring your session…</p>
      </main>
    )
  }

  if (user) {
    const currentPage = allowedPage(user.role, page)
    return <AppShell user={user} page={currentPage} onNavigate={setPage} onSignOut={() => { void handleSignOut() }}>
      {currentPage === 'orders' ? <StoreWorkspace key={user.id} user={user} /> :
        currentPage === 'deliveries' ? <StoreWorkspace key={user.id + '-deliveries'} user={user} deliveries /> :
        currentPage === 'account' ? <><PageHeading title="Store Account" description="Your authenticated outlet scope. Profile editing and preferences are not supported yet." /><Panel title="Account Context"><Facts values={{ 'Name': user.display_name, 'Email': user.email, 'Role': user.role, 'Outlet': user.outlet_id ?? 'Not assigned' }} /></Panel></> :
        <div className="wp-operational-root">{currentPage === 'planning' ? <DispatcherWorkspace /> : currentPage === 'exceptions' ? <ShortfallWorkspace /> : currentPage === 'issues' ? <DeliveryIssues /> : currentPage === 'loading' ? <LoaderWorkspace /> : <DriverWorkspace />}</div>}
      {error && <Alert tone="error">{error}</Alert>}
    </AppShell>
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f3f7fb] px-6 py-10 text-[#10253d]">
      <section className="w-full max-w-md rounded-2xl border border-[#e5ebf2] bg-white p-8 shadow-xl">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[#1765c1]">Waypoint Nexus</p>
        <h1 className="mt-3 text-3xl font-bold">Sign in</h1>
        <p className="mt-2 text-sm text-[#526477]">Use your account to open your delivery workspace.</p>
        <form className="mt-8 space-y-5" onSubmit={handleSignIn}>
          <label className="block text-sm font-medium text-[#10253d]" htmlFor="email">
            Email
            <input
              autoComplete="username"
              className="mt-2 block w-full rounded-lg border border-[#e5ebf2] bg-[#f3f7fb] px-3 py-2.5 text-base text-[#10253d] outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/30"
              id="email"
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>
          <label className="block text-sm font-medium text-[#10253d]" htmlFor="password">
            Password
            <input
              autoComplete="current-password"
              className="mt-2 block w-full rounded-lg border border-[#e5ebf2] bg-[#f3f7fb] px-3 py-2.5 text-base text-[#10253d] outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/30"
              id="password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
          {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
          <button
            className="w-full rounded-lg bg-[#1765c1] text-white px-4 py-3 font-bold hover:bg-[#1558aa] focus:outline-none focus:ring-2 focus:ring-cyan-100 disabled:cursor-wait disabled:opacity-60"
            disabled={submitting}
            type="submit"
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </section>
    </main>
  )
}

export default App
