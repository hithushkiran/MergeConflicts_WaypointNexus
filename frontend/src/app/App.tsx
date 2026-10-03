import { useEffect, useState, type FormEvent } from 'react'

import { ApiError, currentUser, getAccessToken, signIn, signOut, type UserProfile } from '../lib/api'

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
          <p className="mt-8 rounded-lg bg-slate-800/70 p-4 text-sm text-slate-300">
            You are signed in. Available workflows will appear here as they are implemented for your role.
          </p>
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
