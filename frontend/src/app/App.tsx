import { useEffect, useState, type FormEvent } from 'react'

import {
  ApiError,
  createDispatcherPlan,
  createStoreOrder,
  currentUser,
  getDispatcherPlan,
  getAccessToken,
  getOrderEligibility,
  listDispatcherOrders,
  listDispatcherPlans,
  listStoreOrders,
  publishDispatcherPlan,
  signIn,
  signOut,
  type DispatcherFilters,
  type DispatcherOrder,
  type DispatcherPlan,
  type OrderEligibility,
  type StoreOrder,
  type TemperatureRequirement,
  type UserProfile,
} from '../lib/api'

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

  async function refreshOrders() {
    setOrders(await listStoreOrders())
  }

  useEffect(() => {
    let active = true
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
  }, [])

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
    </section>
  )
}

function DispatcherWorkspace() {
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

function App() {
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
        if (active) setError(cause instanceof ApiError ? cause.message : 'Could not restore your session.')
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
      <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-50">
        <section className="mx-auto max-w-3xl rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-xl">
          <header className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">Waypoint Nexus</p>
              <h1 className="mt-3 text-3xl font-bold">Welcome, {user.display_name}</h1>
            </div>
            <button
              className="rounded-lg border border-slate-600 px-4 py-2 text-sm font-semibold hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-cyan-300"
              onClick={handleSignOut}
              type="button"
            >
              Sign out
            </button>
          </header>
          <dl className="mt-8 grid gap-5 border-t border-slate-800 pt-6 sm:grid-cols-2">
            <div>
              <dt className="text-sm text-slate-400">Role</dt>
              <dd className="mt-1 font-semibold">{user.role}</dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">Access scope</dt>
              <dd className="mt-1 font-semibold">{scope}</dd>
            </div>
          </dl>
          {user.role === 'STORE' ? <StoreOrders /> : user.role === 'DISPATCHER' ? <DispatcherWorkspace /> : (
            <p className="mt-8 rounded-lg bg-slate-800/70 p-4 text-sm text-slate-300">
              You are signed in. Available workflows will appear here as they are implemented for your role.
            </p>
          )}
          {error && <p role="alert" className="mt-4 text-sm text-rose-300">{error}</p>}
        </section>
      </main>
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
