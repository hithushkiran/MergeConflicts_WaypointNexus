import { useEffect, useState, type FormEvent } from 'react'

import {
  ApiError,
  createStoreOrder,
  currentUser,
  getAccessToken,
  getOrderEligibility,
  listStoreOrders,
  signIn,
  signOut,
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
          {user.role === 'STORE' ? <StoreOrders /> : (
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
