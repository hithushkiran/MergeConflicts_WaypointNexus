import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import StoreReceipts from './StoreReceipts'
import DeliveryIssues from './DeliveryIssues'

import {
  ApiError,
  AUTHENTICATION_EXPIRED_EVENT,
  acknowledgeManifest,
  assignTripDriver,
  createDispatcherPlan,
  createStoreOrder,
  currentUser,
  getCachedDriverProfile,
  getDispatcherPlan,
  getAccessToken,
  getOrderEligibility,
  listDispatcherOrders,
  listDispatcherDrivers,
  listDriverTrips,
  listDispatcherPlans,
  listLoaderTrips,
  listManifestVersions,
  listShortfalls,
  listStoreOrders,
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
  type OrderEligibility,
  type StoreOrder,
  type TemperatureRequirement,
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

function StoreOrders() {
  const [orders, setOrders] = useState<StoreOrder[]>([])
  const [eligibility, setEligibility] = useState<OrderEligibility | null>(null)
  const [deliveryDate, setDeliveryDate] = useState('')
  const [temperature, setTemperature] = useState<TemperatureRequirement>('AMBIENT')
  const [units, setUnits] = useState('1')
  const [weight, setWeight] = useState('1')
  const [volume, setVolume] = useState('0.1')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)

  async function refreshOrders() {
    setOrders(await listStoreOrders())
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    Promise.all([getOrderEligibility(), listStoreOrders()])
      .then(([timing, storeOrders]) => {
        if (!active) return
        setEligibility(timing)
        setOrders(storeOrders)
        setDeliveryDate((current) => current || timing.next_eligible_delivery_date)
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof ApiError ? cause.message : 'Could not load your orders.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [loadAttempt])

  async function handleCreateOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const order = await createStoreOrder(
        {
          requested_delivery_date: deliveryDate,
          temperature_requirement: temperature,
          units: Number(units),
          weight_kg: Number(weight),
          volume_m3: Number(volume),
          notes: notes.trim() || null,
        },
        crypto.randomUUID(),
      )
      setSuccess(`Order ${order.reference} was submitted.`)
      setNotes('')
      await refreshOrders()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not submit your order.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="mt-8 border-t border-slate-800 pt-6" aria-labelledby="store-orders-heading">
      <h2 id="store-orders-heading" className="text-xl font-bold">Store orders</h2>
      <button className="mt-3 rounded-lg border border-slate-600 px-4 py-2" type="button" disabled={loading || submitting} onClick={() => setLoadAttempt(attempt => attempt + 1)}>Refresh orders</button>
      <p className="mt-2 text-sm text-slate-400">Create a delivery request and track its current status.</p>

      {eligibility && (
        <p className={`mt-4 rounded-lg p-3 text-sm ${eligibility.late_order ? 'bg-amber-950 text-amber-200' : 'bg-slate-800 text-slate-300'}`}>
          {eligibility.explanation}
        </p>
      )}

      <form className="mt-5 grid gap-4 sm:grid-cols-2" onSubmit={handleCreateOrder}>
        <label className="text-sm text-slate-200" htmlFor="delivery-date">
          Requested delivery date
          <input
            className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-slate-50 focus:border-cyan-400 focus:outline-none"
            id="delivery-date"
            min={eligibility?.next_eligible_delivery_date}
            onChange={(event) => setDeliveryDate(event.target.value)}
            required
            type="date"
            value={deliveryDate}
          />
        </label>
        <label className="text-sm text-slate-200" htmlFor="temperature-requirement">
          Temperature
          <select
            className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-slate-50 focus:border-cyan-400 focus:outline-none"
            id="temperature-requirement"
            onChange={(event) => setTemperature(event.target.value as TemperatureRequirement)}
            value={temperature}
          >
            <option value="AMBIENT">Ambient</option>
            <option value="CHILLED">Chilled</option>
            <option value="FROZEN">Frozen</option>
          </select>
        </label>
        <label className="text-sm text-slate-200" htmlFor="units">
          Units
          <input className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-slate-50" id="units" min="1" onChange={(event) => setUnits(event.target.value)} required type="number" value={units} />
        </label>
        <label className="text-sm text-slate-200" htmlFor="weight">
          Total weight (kg)
          <input className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-slate-50" id="weight" min="0.01" onChange={(event) => setWeight(event.target.value)} required step="0.01" type="number" value={weight} />
        </label>
        <label className="text-sm text-slate-200" htmlFor="volume">
          Total volume (m³)
          <input className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-slate-50" id="volume" min="0.01" onChange={(event) => setVolume(event.target.value)} required step="0.01" type="number" value={volume} />
        </label>
        <label className="text-sm text-slate-200 sm:col-span-2" htmlFor="order-notes">
          Notes (optional)
          <textarea className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-slate-50" id="order-notes" maxLength={500} onChange={(event) => setNotes(event.target.value)} rows={2} value={notes} />
        </label>
        {error && <p role="alert" className="text-sm text-rose-300 sm:col-span-2">{error}</p>}
        {success && <p role="status" className="text-sm text-emerald-300 sm:col-span-2">{success}</p>}
        <button className="rounded-lg bg-cyan-400 px-4 py-3 font-bold text-slate-950 hover:bg-cyan-300 disabled:cursor-wait disabled:opacity-60 sm:col-span-2" disabled={submitting || loading || !eligibility} type="submit">
          {submitting ? 'Submitting order…' : 'Submit order'}
        </button>
      </form>

      <div className="mt-8">
        <h3 className="font-semibold">Recent orders</h3>
        {loading ? (
          <p role="status" className="mt-3 text-sm text-slate-400">Loading your orders…</p>
        ) : orders.length === 0 ? (
          <p className="mt-3 rounded-lg bg-slate-800/70 p-4 text-sm text-slate-300">You have no orders yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-800 rounded-lg border border-slate-800">
            {orders.map((order) => (
              <li className="flex flex-wrap items-center justify-between gap-3 p-4" key={order.id}>
                <div>
                  <p className="font-semibold">{order.reference}</p>
                  <p className="mt-1 text-sm text-slate-400">{order.units} units · {order.temperature_requirement.toLowerCase()} · {order.weight_kg} kg · {order.volume_m3} m³</p>
                </div>
                <div className="text-right text-sm">
                  <p className="font-semibold">{order.status}</p>
                  <p className="mt-1 text-slate-400">Delivery {order.requested_delivery_date}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <StoreReceipts onReceived={() => { void refreshOrders().catch(() => setError('Could not refresh order status. Refresh your workspace.')) }} />
    </section>
  )
}

function LoaderWorkspace() {
  const [trips, setTrips] = useState<LoaderTrip[]>([])
  const [manifestHistory, setManifestHistory] = useState<LoaderTrip['manifest'][]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string>('')
  const [statuses, setStatuses] = useState<Record<string, string>>({})
  const [quantities, setQuantities] = useState<Record<string, string>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [working, setWorking] = useState(false)

  async function refresh() {
    setLoading(true); setError('')
    try {
      const items = await listLoaderTrips()
      setTrips(items)
      setSelected((current) => current || items[0]?.id || '')
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

  return <section className="mt-8 border-t border-slate-800 pt-6" aria-labelledby="loader-heading">
    <h2 id="loader-heading" className="text-xl font-bold">Loading bay</h2>
    <button className="mt-3 rounded-lg border border-slate-600 px-4 py-2" type="button" disabled={loading || working} onClick={() => { void refresh().catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : 'Could not load trips.')) }}>Refresh loading bay</button>
    <p className="mt-2 text-sm text-slate-400">Check each order against the current manifest, then acknowledge the version drivers may use.</p>
    {loading ? <p role="status" className="mt-4">Loading trips…</p> : trips.length === 0 ? !error && <p className="mt-4 rounded-lg bg-slate-800 p-4 text-sm">No published trips are available for this depot.</p> : <>
      <label className="mt-4 block text-sm">Published trip<select className={fieldClass} value={selected} onChange={(event) => setSelected(event.target.value)}>{trips.map((item) => <option key={item.id} value={item.id}>{item.vehicle_id} · Trip {item.trip_number} · {item.status} · Plan V{item.plan_version}</option>)}</select></label>
      {trip && <><div className="mt-3 rounded-lg bg-slate-800 p-3 text-sm">Manifest V{trip.manifest.version_number} · {trip.status} · {trip.driver ? `Driver ${trip.driver}` : 'Driver details unavailable'}</div>
        {manifestHistory.length > 1 && <div className="mt-3 rounded-lg border border-cyan-900 p-3"><p className="text-sm font-semibold">Manifest changes</p><ul className="mt-2 space-y-1 text-xs text-slate-300">{manifestHistory.slice(1).map((version, index) => {
          const previous = manifestHistory[index]
          const oldByOrder = new Map(previous.lines.map((line) => [line.order_id, line]))
          const changes = version.lines.flatMap((line) => {
            const old = oldByOrder.get(line.order_id)
            if (!old) return [`${line.order_ref} added`]
            return old.expected_quantity !== line.expected_quantity || old.status !== line.status
              ? [`${line.order_ref}: ${old.expected_quantity} ${old.status.toLowerCase()} → ${line.expected_quantity} ${line.status.toLowerCase()}`]
              : []
          })
          for (const line of previous.lines) if (!version.lines.some((next) => next.order_id === line.order_id)) changes.push(`${line.order_ref} removed from this trip`)
          return <li key={version.id}>V{previous.version_number} → V{version.version_number}: {changes.length ? changes.join('; ') : 'no line changes'}</li>
        })}</ul></div>}
        <div className="mt-3 space-y-3">{trip.manifest.lines.map((line) => <article key={line.order_id} className="rounded-lg border border-slate-800 p-3">
          <p className="font-semibold">{line.load_sequence}. {line.order_ref} <span className="font-normal text-slate-400">· {line.outlet_id} · expected {line.expected_quantity}</span></p>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <label className="text-xs text-slate-300">Result<select className={fieldClass} value={statuses[line.order_id] ?? (line.status === 'PENDING' ? 'LOADED' : line.status)} onChange={(event) => setStatuses((state) => ({ ...state, [line.order_id]: event.target.value }))}><option>LOADED</option><option>MISSING</option><option>DAMAGED</option><option>SUBSTITUTE</option></select></label>
            <label className="text-xs text-slate-300">Quantity (loaded, or affected if missing/damaged)<input className={fieldClass} min="0" max={line.expected_quantity} type="number" value={quantities[line.order_id] ?? line.expected_quantity} onChange={(event) => setQuantities((state) => ({ ...state, [line.order_id]: event.target.value }))} /></label>
            <label className="text-xs text-slate-300">Notes<input className={fieldClass} value={notes[line.order_id] ?? ''} onChange={(event) => setNotes((state) => ({ ...state, [line.order_id]: event.target.value }))} /></label>
          </div>
        </article>)}</div>
        <div className="mt-4 flex flex-wrap gap-3"><button className="rounded-lg bg-cyan-400 px-4 py-2 font-bold text-slate-950 disabled:opacity-50" disabled={working} onClick={saveChecks}>Save loading checks</button><button className="rounded-lg border border-slate-600 px-4 py-2 disabled:opacity-50" disabled={working || Boolean(trip.manifest.acknowledged_at)} onClick={acknowledge}>Acknowledge current manifest</button></div>
      </>}
    </>}
    {error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}{notice && <p role="status" className="mt-3 text-sm text-emerald-300">{notice}</p>}
  </section>
}

function DriverWorkspace({ user }: { user: UserProfile }) {
  const [trips, setTrips] = useState<DriverTrip[]>([])
  const [receiver, setReceiver] = useState<Record<string, string>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [online, setOnline] = useState(() => typeof navigator === 'undefined' || navigator.onLine)
  const [serverConnected, setServerConnected] = useState(true)
  const [outbox, setOutbox] = useState<QueuedDriverCommand[]>([])
  const [syncing, setSyncing] = useState(false)
  const retryTimer = useRef<number | null>(null)
  const mounted = useRef(false)
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
    else if (queued.some((entry) => entry.state === 'AUTH_REQUIRED')) setError('Sign in again with the same driver account to sync saved updates.')
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
      if (result.next_attempt_at && navigator.onLine && mounted.current) {
        if (retryTimer.current !== null) window.clearTimeout(retryTimer.current)
        retryTimer.current = window.setTimeout(() => { void sync() }, Math.max(500, result.next_attempt_at - Date.now()))
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Offline updates could not be saved.')
    } finally { setSyncing(false) }
  }, [refresh, userId])

  useEffect(() => {
    mounted.current = true
    void refresh().then(() => { if (navigator.onLine) void sync() }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not open saved trips.'))
    const update = () => {
      setOnline(navigator.onLine)
      if (navigator.onLine) void sync()
    }
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      mounted.current = false
      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current)
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [refresh, sync, userId])

  async function queue(command: DriverCommandInput) {
    if (!userId) { setError('Sign in while connected once to enable offline delivery work.'); return }
    setWorking(true); setError('')
    try {
      await enqueueDriverCommand(userId, command)
      await refresh()
      if (navigator.onLine) void sync()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save the delivery update offline.') }
    finally { setWorking(false) }
  }
  const field = 'mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-2 text-slate-50'
  return <section className="mt-8 border-t border-slate-800 pt-6" aria-labelledby="driver-heading">
    <h2 id="driver-heading" className="text-xl font-bold">My delivery trips</h2>
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm"><span className={online && serverConnected ? 'text-emerald-300' : 'text-amber-200'}>{online && serverConnected ? 'Connected' : 'Offline · saved on this device'} · {outbox.length} update{outbox.length === 1 ? '' : 's'} waiting{syncing ? ' · syncing…' : ''}</span><button className="rounded border border-slate-600 px-3 py-1.5 disabled:opacity-50" disabled={!online || syncing || outbox.length === 0} onClick={() => void sync()} type="button">Sync now</button></div>
    <p className="mt-2 text-sm text-slate-400">Trips and acknowledged manifest details are saved on this device while connected.</p>
    {trips.length === 0 ? <p className="mt-4 rounded-lg bg-slate-800 p-4 text-sm">No ready or active trips are assigned to you.</p> : <div className="mt-4 space-y-4">{trips.map((trip) => <article key={trip.id} className="rounded-xl border border-slate-700 p-4">
      <h3 className="font-semibold">{trip.vehicle_id} · Trip {trip.trip_number} · {trip.brand} / {trip.district}</h3>
      <p className="mt-1 text-xs text-slate-400">{trip.depot_code} · Plan V{trip.plan_version} · Acknowledged manifest V{trip.manifest_version} · {trip.status}</p>
      {trip.manifest && <details className="mt-2 text-xs text-slate-300"><summary>Manifest V{trip.manifest.version_number} · {trip.manifest.lines.length} orders</summary><ul className="mt-2 space-y-1">{trip.manifest.lines.map((line) => <li key={line.order_id}>{line.sequence_number}. {line.order_ref} · {line.outlet_id} · {line.loaded_quantity}/{line.expected_quantity} · {line.status}</li>)}</ul></details>}
      {trip.status === 'READY' && <button className="mt-3 rounded-lg bg-cyan-400 px-4 py-2 font-bold text-slate-950 disabled:opacity-50" disabled={working} onClick={() => void queue({ kind: 'DEPART', trip_id: trip.id })}>Start trip</button>}
      <ol className="mt-4 space-y-3">{trip.stops.map((stop, stopIndex) => {
        const previousStopsDone = trip.stops.slice(0, stopIndex).every((previous) => previous.status === 'DELIVERED' || previous.status === 'FAILED')
        const localPending = outbox.some((entry) => entry.command.trip_id === trip.id && 'stop_id' in entry.command && entry.command.stop_id === stop.id)
        const savedReceiver = receiver[stop.id] ?? stop.receiver_name ?? ''
        const savedNotes = notes[stop.id] ?? stop.delivery_notes ?? ''
        return <li key={stop.id} className="rounded-lg bg-slate-950 p-3">
        <p className="font-semibold">{stop.sequence_number}. {stop.order_ref} · {stop.outlet_id}</p>
        <p className="mt-1 text-sm text-slate-300">{stop.district}{stop.window_open_time && stop.window_close_time ? ` · ${stop.window_open_time}–${stop.window_close_time}` : ''}{stop.planned_arrival ? ` · ETA ${new Date(stop.planned_arrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Colombo' })}` : ''}</p>
        {stop.instructions && <p className="mt-1 text-sm text-amber-200">Instructions: {stop.instructions}</p>}
        <p className="mt-1 text-xs text-slate-400">Status: {stop.status}{localPending ? ' · waiting to sync' : ''}</p>
        {trip.status === 'IN_PROGRESS' && stop.status === 'PENDING' && previousStopsDone && <button className="mt-2 rounded border border-cyan-700 px-3 py-2 text-sm" disabled={working} onClick={() => void queue({ kind: 'ARRIVE', trip_id: trip.id, stop_id: stop.id })}>Arrived</button>}
        {trip.status === 'IN_PROGRESS' && stop.status === 'ARRIVED' && <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-slate-300">Receiver name<input className={field} value={receiver[stop.id] ?? stop.receiver_name ?? ''} onChange={(event) => { const value = event.target.value; setReceiver((state) => ({ ...state, [stop.id]: value })); if (userId) void saveDeliveryDraft(userId, trip.id, stop.id, value, notes[stop.id] ?? stop.delivery_notes ?? '') }} /></label>
          <label className="text-xs text-slate-300">Delivery notes or failure reason<input className={field} value={notes[stop.id] ?? stop.delivery_notes ?? ''} onChange={(event) => { const value = event.target.value; setNotes((state) => ({ ...state, [stop.id]: value })); if (userId) void saveDeliveryDraft(userId, trip.id, stop.id, receiver[stop.id] ?? stop.receiver_name ?? '', value) }} /></label>
          <div className="flex gap-2 sm:col-span-2"><button className="rounded bg-emerald-400 px-3 py-2 font-semibold text-slate-950" disabled={working || !savedReceiver.trim()} onClick={() => void queue({ kind: 'COMPLETE', trip_id: trip.id, stop_id: stop.id, outcome: 'DELIVERED', receiver_name: savedReceiver, notes: savedNotes })}>Delivered</button><button className="rounded border border-rose-700 px-3 py-2" disabled={working || !savedNotes.trim()} onClick={() => void queue({ kind: 'COMPLETE', trip_id: trip.id, stop_id: stop.id, outcome: 'FAILED', receiver_name: savedReceiver, notes: savedNotes })}>Failed delivery</button></div>
        </div>}
      </li>})}</ol>
    </article>)}</div>}
    {error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}
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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [working, setWorking] = useState(false)
  async function refresh() {
    setLoading(true); setError('')
    try {
    const [shortfalls, plans] = await Promise.all([listShortfalls(), listDispatcherPlans()])
    setItems(shortfalls)
    setPublishedTrips(plans.filter((plan) => plan.status === 'PUBLISHED').flatMap((plan) => plan.trips.map((trip) => ({
      id: trip.id, vehicle_id: trip.vehicle_id, trip_number: trip.trip_number, brand: trip.brand, district: trip.district,
    }))))
    } finally { setLoading(false) }
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
  const fieldClass = 'mt-2 rounded border border-slate-700 bg-slate-950 px-3 py-2 text-slate-50'
  return <section className="mt-8 border-t border-slate-800 pt-6" aria-labelledby="shortfall-heading"><h2 id="shortfall-heading" className="text-xl font-bold">Loading exceptions</h2>
    <button className="mt-3 rounded-lg border border-slate-600 px-4 py-2" type="button" disabled={loading || working} onClick={() => { void refresh().catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : 'Could not load shortfalls.')) }}>Refresh exceptions</button>
    {loading && <p role="status" className="mt-3">Loading exceptions…</p>}
    {items.length === 0 ? !loading && !error && <p className="mt-3 text-sm text-slate-400">No open loading exceptions.</p> : <ul className="mt-3 space-y-3">{items.map((item) => <li key={item.id} className="rounded-lg border border-amber-900 bg-amber-950/30 p-4">
      <p className="font-semibold">{item.order_ref} · {item.reason.toLowerCase()} · {item.quantity} units · {item.blocking ? 'dispatch hold' : 'nonblocking'}</p>
      {item.status === 'RESOLUTION_PENDING' ? <button className="mt-3 rounded-lg border border-cyan-700 px-3 py-2 text-sm" disabled={working} onClick={() => openReallocationPlan(item)}>Review replacement plan</button> : <div className="mt-3 flex flex-wrap gap-2"><select aria-label={`Resolution action for ${item.order_ref}`} className={fieldClass} value={actions[item.id] ?? 'RELOAD_FOUND'} onChange={(event) => setActions((state) => ({ ...state, [item.id]: event.target.value }))}><option value="RELOAD_FOUND">Reload found</option><option value="PARTIAL_FULFILLMENT">Accept partial quantity</option><option value="SUBSTITUTE">Substitute</option><option value="DEFER">Defer order</option><option value="REALLOCATION">Move order to another trip</option></select>{actions[item.id] === 'REALLOCATION' && <select aria-label={`Target trip for ${item.order_ref}`} className={fieldClass} value={targetTrips[item.id] ?? ''} onChange={(event) => setTargetTrips((state) => ({ ...state, [item.id]: event.target.value }))}><option value="">Choose compatible trip</option>{publishedTrips.filter((trip) => trip.id !== item.trip_id).map((trip) => <option key={trip.id} value={trip.id}>{trip.vehicle_id} · Trip {trip.trip_number} · {trip.brand} / {trip.district}</option>)}</select>}{actions[item.id] === 'PARTIAL_FULFILLMENT' && <input aria-label={`Accepted quantity for ${item.order_ref}`} className={fieldClass} min="0" max={item.quantity} type="number" placeholder="Accepted units" value={resolutionQuantities[item.id] ?? ''} onChange={(event) => setResolutionQuantities((state) => ({ ...state, [item.id]: event.target.value }))} />}{actions[item.id] === 'SUBSTITUTE' && <input aria-label={`Substitute for ${item.order_ref}`} className={fieldClass} placeholder="Substitute reference" value={substitutes[item.id] ?? ''} onChange={(event) => setSubstitutes((state) => ({ ...state, [item.id]: event.target.value }))} />}<input aria-label={`Resolution reason for ${item.order_ref}`} className={`${fieldClass} min-w-56 flex-1`} placeholder="Required reason" value={reasons[item.id] ?? ''} onChange={(event) => setReasons((state) => ({ ...state, [item.id]: event.target.value }))} /><button className="rounded-lg bg-cyan-400 px-4 py-2 font-bold text-slate-950 disabled:opacity-50" disabled={working || !(reasons[item.id] ?? '').trim() || (actions[item.id] === 'REALLOCATION' && !targetTrips[item.id])} onClick={() => resolve(item)}>{actions[item.id] === 'REALLOCATION' ? 'Build replacement plan' : 'Resolve and create V2'}</button></div>}
    </li>)}</ul>}{candidatePlan && <section className="mt-5 rounded-xl border border-cyan-800 bg-slate-950 p-4" aria-label="Replacement plan review"><h3 className="font-bold">Replacement plan V{candidatePlan.version_number} · {candidatePlan.status}</h3><p className="mt-1 text-sm text-slate-400">The planner checked vehicle capacity, fuel, route grouping, and delivery windows. Review the updated trips before publishing.</p><div className="mt-3 space-y-2">{candidatePlan.trips.map((trip) => <article className="rounded-lg border border-slate-800 p-3 text-sm" key={trip.id}><p className="font-semibold">{trip.vehicle_id} · Trip {trip.trip_number} · {trip.brand} / {trip.district}</p><p className="mt-1 text-xs text-slate-400">{trip.metrics.weight_kg} kg · {trip.metrics.volume_m3} m³ · {trip.metrics.fuel_liters} L · {trip.metrics.duration_minutes} min</p><ol className="mt-2 list-inside list-decimal">{trip.stops.map((stop) => <li key={stop.order_id}>{stop.order_ref} · {stop.outlet_id}</li>)}</ol></article>)}</div><div className="mt-4 flex gap-2"><button className="rounded-lg bg-emerald-400 px-4 py-2 font-bold text-slate-950 disabled:opacity-50" disabled={working || candidatePlan.status !== 'DRAFT' || candidatePlan.trips.some((trip) => trip.metrics.time_windows_valid !== true)} onClick={publishReallocation}>{working ? 'Publishing…' : 'Publish replacement plan'}</button><button className="rounded-lg border border-slate-700 px-4 py-2" disabled={working} onClick={() => setCandidatePlan(null)}>Close review</button></div></section>}{error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}{notice && <p role="status" className="mt-3 text-sm text-emerald-300">{notice}</p>}</section>
}

function DispatcherWorkspace() {
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
  const filterClass = 'mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-50'
  const inputClass = 'rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-50'

  return (
    <section className="mt-8 border-t border-slate-800 pt-6" aria-labelledby="dispatcher-heading">
      <h2 id="dispatcher-heading" className="text-xl font-bold">Dispatcher plan review</h2>
      <p className="mt-2 text-sm text-slate-400">Filter confirmed orders, generate a draft candidate, review its trips and deferrals, then publish a version.</p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="text-sm text-slate-200">Delivery date
          <select className={filterClass} onChange={(event) => updateFilter('planning_date', event.target.value)} value={filters.planning_date ?? ''}>
            <option value="">All dates</option>
            {dateOptions.map((date) => <option key={date} value={date}>{date}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-200">Depot
          <select className={filterClass} onChange={(event) => updateFilter('depot', event.target.value)} value={filters.depot ?? ''}>
            <option value="">All depots</option><option>Peliyagoda</option><option>Kandy</option>
          </select>
        </label>
        <label className="text-sm text-slate-200">Brand
          <select className={filterClass} onChange={(event) => updateFilter('brand', event.target.value)} value={filters.brand ?? ''}>
            <option value="">All brands</option><option>Fresh</option><option>Style</option><option>Tech</option>
          </select>
        </label>
        <label className="text-sm text-slate-200">District
          <input className={filterClass} onChange={(event) => updateFilter('district', event.target.value)} placeholder="Any district" value={filters.district ?? ''} />
        </label>
        <label className="text-sm text-slate-200">Temperature
          <select className={filterClass} onChange={(event) => updateFilter('temperature', event.target.value as DispatcherFilters['temperature'])} value={filters.temperature ?? ''}>
            <option value="">Any temperature</option><option value="AMBIENT">Ambient</option><option value="CHILLED">Chilled</option><option value="FROZEN">Frozen</option>
          </select>
        </label>
        <label className="text-sm text-slate-200">Access rule
          <select className={filterClass} onChange={(event) => updateFilter('access', event.target.value)} value={filters.access ?? ''}>
            <option value="">Any access rule</option><option value="VAN_ONLY">Van only</option><option value="NONE">No restriction</option>
          </select>
        </label>
        <label className="text-sm text-slate-200">Delivery window
          <select className={filterClass} onChange={(event) => updateFilter('delivery_window', event.target.value as DispatcherFilters['delivery_window'])} value={filters.delivery_window ?? ''}>
            <option value="">Any window</option><option value="restricted">Has receiving window</option><option value="none">No receiving window</option>
          </select>
        </label>
        <label className="text-sm text-slate-200">Prior deferral
          <select className={filterClass} onChange={(event) => updateFilter('prior_deferral', event.target.value as DispatcherFilters['prior_deferral'])} value={filters.prior_deferral ?? ''}>
            <option value="">Any</option><option value="true">Previously deferred</option><option value="false">Not deferred before</option>
          </select>
        </label>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
        <p className="text-sm text-slate-300">{loading ? 'Loading orders…' : `${orders.length} confirmed order${orders.length === 1 ? '' : 's'} in this queue`}</p>
        <button className="rounded-lg bg-cyan-400 px-4 py-2.5 font-bold text-slate-950 disabled:opacity-50" disabled={working || loading || !filters.planning_date || orders.length === 0} onClick={makeCandidate} type="button">
          {working && !plan ? 'Building candidate…' : 'Generate candidate plan'}
        </button>
      </div>

      {savedPlans.length > 0 && <div className="mt-5">
        <h3 className="font-semibold">Saved plan versions</h3>
        <ul className="mt-2 flex flex-wrap gap-2">{savedPlans.map((saved) => <li key={saved.id}>
          <button className="rounded-lg border border-slate-700 px-3 py-2 text-left text-sm hover:border-cyan-500" onClick={() => { setError(''); getDispatcherPlan(saved.id).then(setPlan).catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : 'Could not open this plan version.')) }} type="button">
            V{saved.version_number} · {saved.status} · {new Date(saved.created_at).toLocaleString()}
          </button>
        </li>)}</ul>
      </div>}

      {!loading && orders.length === 0 && <p className="mt-4 rounded-lg bg-slate-800/70 p-4 text-sm text-slate-300">No confirmed orders match these filters.</p>}
      {orders.length > 0 && <ul className="mt-4 divide-y divide-slate-800 rounded-lg border border-slate-800">
        {orders.map((order) => <li className="flex flex-wrap justify-between gap-2 p-3 text-sm" key={order.id}>
          <span><strong>{order.reference}</strong> · {order.outlet_id} · {order.brand} / {order.district}{order.window_open_time && order.window_close_time ? ` · ${order.window_open_time}–${order.window_close_time}` : ''}</span>
          <span className="text-slate-400">{order.requested_delivery_date} · {order.temperature_requirement.toLowerCase()} · {order.weight_kg} kg / {order.volume_m3} m³</span>
        </li>)}
      </ul>}

      {plan && <section className="mt-8 rounded-xl border border-cyan-900 bg-slate-950/60 p-5" aria-labelledby="candidate-heading">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase tracking-widest text-cyan-300">Plan V{plan.version_number} · {plan.status}</p><h3 id="candidate-heading" className="mt-1 text-xl font-bold">Candidate review · {plan.planning_date}</h3></div>
          <div className="flex gap-4 text-sm"><span>{plan.orders.filter((item) => item.decision === 'served').length} served</span><span>{plan.orders.filter((item) => item.decision === 'deferred').length} deferred</span><span>{plan.trips.length} trips</span></div>
        </div>
        {plan.diagnostics.length > 0 && <ul className="mt-4 list-disc pl-5 text-sm text-amber-200">{plan.diagnostics.map((item) => <li key={item}>{item.replace(/_/g, ' ')}</li>)}</ul>}
        <div className="mt-5 space-y-4">
          {plan.trips.map((trip) => <article className="rounded-lg border border-slate-800 p-4" key={trip.id}>
            <h4 className="font-semibold">{trip.brand} · {trip.district} · {trip.vehicle_id} · Trip {trip.trip_number}</h4>
            <p className="mt-1 text-xs text-slate-400">{trip.metrics.weight_kg} kg ({trip.metrics.weight_utilization_pct}% capacity) · {trip.metrics.volume_m3} m³ ({trip.metrics.volume_utilization_pct}% capacity) · {trip.metrics.distance_km} km · {trip.metrics.fuel_liters} L · {trip.metrics.duration_minutes} min</p>
            {plan.status === 'PUBLISHED' && <div className="mt-3 flex flex-wrap items-end gap-2"><label className="text-xs text-slate-300">Driver for {trip.depot_code}<select className={`${inputClass} mt-1 block`} value={driverSelections[trip.id] ?? trip.assigned_driver_id ?? ''} onChange={(event) => setDriverSelections((state) => ({ ...state, [trip.id]: event.target.value }))}><option value="">Choose driver</option>{drivers.filter((driver) => driver.depot_code === trip.depot_code).map((driver) => <option key={driver.id} value={driver.id}>{driver.display_name}</option>)}</select></label><button className="rounded-lg border border-cyan-700 px-3 py-2 text-sm disabled:opacity-50" disabled={working || !(driverSelections[trip.id] ?? trip.assigned_driver_id)} onClick={() => assignDriver(trip.id, driverSelections[trip.id] ?? trip.assigned_driver_id ?? '')}>{trip.assigned_driver_name ? `Assigned: ${trip.assigned_driver_name} · change` : 'Assign driver'}</button></div>}
            <ol className="mt-3 space-y-2 border-l border-slate-700 pl-4 text-sm">{trip.stops.map((stop) => <li key={stop.order_id}><strong>{stop.sequence_number}. {stop.order_ref}</strong> · {stop.outlet_id} · ETA {stop.planned_arrival ? new Date(stop.planned_arrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Colombo' }) : 'not set'} · {stop.planned_service_minutes} min service</li>)}</ol>
          </article>)}
        </div>
        <div className="mt-5 rounded-lg bg-slate-900 p-4">
          <h4 className="font-semibold">Order decisions</h4>
          <ul className="mt-2 space-y-2 text-sm">{plan.orders.map((item) => <li key={item.order_id} className="flex flex-wrap justify-between gap-2">
            <span>{item.order_ref} · {item.outlet_id ?? '—'}</span>
            <span className={item.decision === 'deferred' ? 'text-amber-200' : 'text-emerald-200'}>{item.decision}{item.vehicle_id ? ` · ${item.vehicle_id} / trip ${item.trip_number}` : ''}{item.reason ? ` · ${item.reason.replace(/_/g, ' ')}` : ''}</span>
          </li>)}</ul>
        </div>
        {plan.status === 'DRAFT' && <div className="mt-5 flex flex-wrap items-end gap-3">
          <label className="min-w-64 flex-1 text-sm text-slate-200">Publication note (optional)
            <input className={`${inputClass} mt-2 block w-full`} maxLength={500} onChange={(event) => setReason(event.target.value)} value={reason} />
          </label>
          <button className="rounded-lg bg-emerald-400 px-5 py-2.5 font-bold text-slate-950 disabled:opacity-50" disabled={working || plan.trips.some((trip) => trip.metrics.time_windows_valid !== true)} onClick={publishPlan} type="button">{working ? 'Publishing…' : 'Publish plan'}</button>
        </div>}
        {plan.status === 'PUBLISHED' && <p className="mt-5 rounded-lg bg-emerald-950 p-3 text-sm text-emerald-200">Published {plan.published_at ? new Date(plan.published_at).toLocaleString() : ''}. The published version is locked.</p>}
      </section>}

      {error && <p role="alert" className="mt-4 text-sm text-rose-300">{error}</p>}
      {notice && <p role="status" className="mt-4 text-sm text-emerald-300">{notice}</p>}
    </section>
  )
}

const roleNavigation: Record<UserProfile['role'], Array<{ label: string; href: string }>> = {
  STORE: [
    { label: 'Orders', href: '#store-orders-heading' },
    { label: 'Deliveries & receipts', href: '#receipts-heading' },
  ],
  DISPATCHER: [
    { label: 'Plan review', href: '#dispatcher-heading' },
    { label: 'Exceptions', href: '#shortfall-heading' },
    { label: 'Receiving issues', href: '#delivery-issues-heading' },
  ],
  LOADER: [{ label: 'Loading bay', href: '#loader-heading' }],
  DRIVER: [{ label: 'Route & delivery', href: '#driver-heading' }],
}

function AppShell({
  user,
  scope,
  onSignOut,
  children,
}: {
  user: UserProfile
  scope: string
  onSignOut: () => void
  children: ReactNode
}) {
  const navigation = roleNavigation[user.role]
  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace-content">Skip to workspace</a>
      <header className="app-header">
        <div className="app-header__inner">
          <a className="brand" href="#workspace-content" aria-label="Waypoint Nexus workspace">
            <span className="brand__mark" aria-hidden="true">W</span>
            <span><strong>Waypoint</strong><span className="brand__muted"> Nexus</span></span>
          </a>
          <div className="account-bar">
            <div className="account-context">
              <span className="account-context__name">{user.display_name}</span>
              <span className="account-context__scope">{scope}</span>
            </div>
            <span className="role-badge">{user.role}</span>
            <button className="header-action" onClick={onSignOut} type="button">Sign out</button>
          </div>
        </div>
      </header>
      <nav className="role-nav" aria-label={`${user.role.toLowerCase()} workspace navigation`}>
        <div className="role-nav__inner">
          {navigation.map((item) => <a key={item.href} href={item.href}>{item.label}</a>)}
        </div>
      </nav>
      <main id="workspace-content" className="workspace-main" tabIndex={-1}>
        <div className="workspace-intro">
          <div>
            <p className="eyebrow">{user.role} workspace</p>
            <h1>{user.role === 'STORE' ? 'Manage your deliveries' : user.role === 'DISPATCHER' ? 'Coordinate today’s network' : user.role === 'LOADER' ? 'Prepare the outbound route' : 'Complete your delivery route'}</h1>
          </div>
          <p className="workspace-intro__hint">Server status updates on refresh. Offline driver changes wait for sync.</p>
        </div>
        <div className="workspace-content">{children}</div>
      </main>
    </div>
  )
}

function App() {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [checkingSession, setCheckingSession] = useState(() => Boolean(getAccessToken()))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const expired = () => {
      setUser(null)
      setPassword('')
      setError('Your session expired. Sign in again with the same account. Saved driver updates remain on this device.')
    }
    window.addEventListener(AUTHENTICATION_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(AUTHENTICATION_EXPIRED_EVENT, expired)
  }, [])

  useEffect(() => {
    if (!getAccessToken()) {
      if (!navigator.onLine) setUser(getCachedDriverProfile())
      return
    }

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
  }

  if (checkingSession) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-50">
        <p role="status" className="text-slate-300">Restoring your session…</p>
      </main>
    )
  }

  if (user) {
    const scope = user.outlet_id ? `Outlet ${user.outlet_id}` : user.depot_code ? `Depot ${user.depot_code}` : 'All operations'
    return (
      <AppShell user={user} scope={scope} onSignOut={() => void handleSignOut()}>
          {user.role === 'STORE' ? <StoreOrders /> : user.role === 'DISPATCHER' ? <><DispatcherWorkspace /><ShortfallWorkspace /><DeliveryIssues /></> : user.role === 'LOADER' ? <LoaderWorkspace /> : <DriverWorkspace key={user.id} user={user} />}
          {error && <p role="alert" className="mt-4 text-sm text-rose-300">{error}</p>}
      </AppShell>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 py-10 text-slate-50">
      <section className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-xl">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">Waypoint Nexus</p>
        <h1 className="mt-3 text-3xl font-bold">Sign in</h1>
        <p className="mt-2 text-sm text-slate-400">Use your account to open your delivery workspace.</p>
        <form className="mt-8 space-y-5" onSubmit={handleSignIn}>
          <label className="block text-sm font-medium text-slate-200" htmlFor="email">
            Email
            <input
              autoComplete="username"
              className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-base text-slate-50 outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/30"
              id="email"
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>
          <label className="block text-sm font-medium text-slate-200" htmlFor="password">
            Password
            <input
              autoComplete="current-password"
              className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-base text-slate-50 outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/30"
              id="password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
          {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
          <button
            className="w-full rounded-lg bg-cyan-400 px-4 py-3 font-bold text-slate-950 hover:bg-cyan-300 focus:outline-none focus:ring-2 focus:ring-cyan-100 disabled:cursor-wait disabled:opacity-60"
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
