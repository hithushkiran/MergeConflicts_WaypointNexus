import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, listDeliveryIssues, reviewDeliveryIssue, type DeliveryIssueItem } from '../lib/api'
import { receivingTime } from '../lib/receivingTime'

export default function DeliveryIssues() {
  const [items, setItems] = useState<DeliveryIssueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const attempts = useRef(new Map<string, { body: string; key: string }>())
  const refresh = useCallback(async () => {
    setError(''); setLoading(true)
    try { setItems(await listDeliveryIssues()) }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not load receiving issues.') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh() }, [refresh])

  async function review(item: DeliveryIssueItem) {
    const reason = reasons[item.id]?.trim()
    if (!reason) { setError('Enter a review or resolution reason.'); return }
    const status = item.status === 'OPEN' ? 'IN_REVIEW' : 'RESOLVED'
    const body = JSON.stringify({ status, reason })
    let attempt = attempts.current.get(item.id)
    if (attempt?.body !== body) { attempt = { body, key: crypto.randomUUID() }; attempts.current.set(item.id, attempt) }
    setBusy(true); setError('')
    try { await reviewDeliveryIssue(item.id, status, reason, attempt.key); await refresh() }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not save issue review. Retry or refresh to check the saved result.') }
    finally { setBusy(false) }
  }

  return <section className="mt-8 border-t border-slate-800 pt-6" aria-labelledby="delivery-issues-heading">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="delivery-issues-heading" className="text-xl font-bold">Store receiving issues</h2><button className="rounded-lg border border-slate-600 px-4 py-2" disabled={loading || busy} onClick={() => void refresh()}>Refresh issues</button></div>
    {error && <p role="alert" className="mt-3 text-rose-300">{error}</p>}
    {loading ? <p role="status" className="mt-4">Loading receiving issues…</p> : items.length === 0 ? <p className="mt-4 text-slate-400">No store receiving issues have been reported.</p> : <div className="mt-4 space-y-4">{items.map(item => <article key={item.id} className="rounded-lg border border-slate-700 p-4">
      <p className="font-semibold">{item.order_ref} · {item.outlet_id} · {item.status}</p><p className="mt-1 break-all text-xs text-slate-400">Case {item.id} · {receivingTime(item.created_at)}</p>
      <p className="mt-3 text-sm">{item.issue_type.replace(/_/g, ' ')} · {item.affected_quantity ?? 'Unknown'} affected units</p>
      {item.receipt && <p className="mt-2 text-sm text-slate-300">Ordered {item.receipt.ordered_quantity ?? 'unknown'} · Dispatched {item.receipt.dispatched_quantity ?? 'unknown'} · Received {item.receipt.received_quantity ?? 'unknown'} units · Receiver {item.receipt.receiver_name ?? 'unknown'}</p>}
      <p className="mt-2 whitespace-pre-wrap text-sm">{item.notes}</p>
      {item.status === 'RESOLVED' ? <p className="mt-3 text-sm text-emerald-300">Resolved: {item.resolution_notes} · {receivingTime(item.resolved_at)}</p> : <form className="mt-4 flex flex-wrap gap-3" onSubmit={event => { event.preventDefault(); void review(item) }}>
        <label className="min-w-0 flex-1 text-sm">{item.status === 'OPEN' ? 'Review reason' : 'Resolution reason'}<input required maxLength={1000} disabled={busy} className="mt-1 block w-full rounded border border-slate-600 bg-slate-950 px-3 py-2" value={reasons[item.id] ?? ''} onChange={event => setReasons(current => ({ ...current, [item.id]: event.target.value }))} /></label>
        <button className="self-end rounded-lg bg-cyan-400 px-4 py-2 font-bold text-slate-950 disabled:opacity-50" disabled={busy} type="submit">{item.status === 'OPEN' ? 'Start review' : 'Resolve recorded outcome'}</button>
      </form>}
    </article>)}</div>}
  </section>
}
