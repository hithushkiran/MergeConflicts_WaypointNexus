import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { receivingTime } from '../lib/receivingTime'
import {
  ApiError, listStoreDeliveries, reportDeliveryIssue, submitStoreReceipt,
  type DeliveryIssueType, type IssueInput, type ReceivingInput, type ReceivingResult, type StoreDelivery,
} from '../lib/api'

const card = 'rounded-xl border border-[#e5ebf2] bg-white p-6 shadow-sm'
const field = 'mt-1 block w-full rounded-lg border border-[#e5ebf2] bg-white px-3 py-2.5 text-[#10253d] focus:outline-none focus:ring-2 focus:ring-[#1765c1]'
const primary = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-[#1765c1] px-6 py-3 text-sm font-semibold text-white hover:bg-[#1558aa] disabled:opacity-50'
const secondary = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-[#e5ebf2] bg-white px-5 py-3 text-sm font-medium text-[#526477] hover:bg-slate-50 disabled:opacity-50'

export function QuantityComparison({ delivery, counted }: { delivery: StoreDelivery; counted: number | null }) {
  const difference = counted === null ? null : delivery.ordered_quantity - counted
  return <div className="overflow-x-auto rounded-lg border border-[#e5ebf2]">
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Original order, dispatched and received quantities in units</caption>
      <thead className="bg-[#f8fafc] text-xs uppercase tracking-wide text-[#526477]"><tr>
        <th className="p-4">Shipment</th><th className="p-4">Ordered</th><th className="p-4">Dispatched</th><th className="p-4">Counted</th><th className="p-4">Difference</th>
      </tr></thead>
      <tbody><tr className="border-t border-[#e5ebf2]">
        <th className="p-4 font-medium">{delivery.temperature_requirement.toLowerCase()}<span className="mt-1 block font-mono text-xs text-[#526477]">{delivery.order_ref}</span></th>
        <td className="p-4 font-mono">{delivery.ordered_quantity}</td><td className="p-4 font-mono">{delivery.dispatched_quantity}</td><td className="p-4 font-mono font-bold">{counted ?? 'Unknown'}</td>
        <td className={`p-4 ${difference ? 'font-semibold text-rose-700' : 'text-[#147d64]'}`}>
          {difference === null ? 'Unknown' : difference ? `${difference} units short` : <span className="inline-flex items-center gap-1"><img src="/receipt-assets/match.svg" alt="" width={12} height={12} />Match</span>}
        </td>
      </tr></tbody>
    </table>
    <p className="border-t border-[#e5ebf2] bg-[#f8fafc] px-4 py-3 text-xs text-[#526477]">
      Original weight {delivery.ordered_weight_kg} kg · Counted weight equivalent {counted === null ? 'unknown' : `≈ ${(delivery.ordered_weight_kg * counted / delivery.ordered_quantity).toFixed(1)} kg (proportional estimate)`}
    </p>
  </div>
}

export function ReceiptOutcome({ result }: { result: ReceivingResult }) {
  const issue = result.issue
  return <div className="space-y-5">
    <div role="status" className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-5">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#147d64]"><img src="/receipt-assets/submitted.svg" alt="" width={20} height={20} /></span>
      <div><h3 className="font-bold">{issue ? 'Delivery Issue Submitted' : 'Receipt Confirmed'}</h3>
        <p className="mt-1 text-sm text-[#526477]">{issue ? 'The delivery discrepancy has been recorded for operations review.' : 'Your received quantities have been saved.'}</p></div>
    </div>
    <div className={card}><h3 className="font-bold">{issue ? 'Reported Issue' : 'Receiving Record'}</h3>
      <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
        <div><dt className="text-[#526477]">Receipt reference</dt><dd className="break-all font-mono">{result.receipt.id}</dd></div>
        <div><dt className="text-[#526477]">Received</dt><dd>{result.receipt.received_quantity ?? 'Unknown'} units · {result.receipt.status}</dd></div>
        <div><dt className="text-[#526477]">Receiver</dt><dd>{result.receipt.receiver_name ?? 'Not recorded'}</dd></div>
        <div><dt className="text-[#526477]">Recorded at</dt><dd>{receivingTime(result.receipt.confirmed_at)}</dd></div>
        {issue && <><div><dt className="text-[#526477]">Case reference</dt><dd className="break-all font-mono">{issue.id}</dd></div>
          <div><dt className="text-[#526477]">Issue status</dt><dd>{issue.status} · {issue.affected_quantity ?? 'Unknown'} affected units</dd></div></>}
      </dl>
      {result.receipt.notes && <p className="mt-4 rounded-lg bg-[#f8fafc] p-3 text-sm">{result.receipt.notes}</p>}
      {issue?.resolution_notes && <p className="mt-3 text-sm">Resolution: {issue.resolution_notes} · {receivingTime(issue.resolved_at)}</p>}
    </div>
    {issue && <div className={card}><h3 className="font-bold">What happens next?</h3>
      <ol className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <li className="rounded-lg border border-[#e5ebf2] bg-[#f8fafc] p-4"><p className="font-semibold">1. Issue Recorded</p><p className="mt-2 text-[#526477]">Saved against the order.</p></li>
        <li className="rounded-lg border border-blue-200 bg-blue-50 p-4"><p className="font-semibold">2. Operations Review</p><p className="mt-2 text-[#526477]">{issue.status === 'OPEN' ? 'Waiting for dispatcher review.' : 'Review started by operations.'}</p></li>
        <li className="rounded-lg border border-[#e5ebf2] bg-[#f8fafc] p-4"><p className="font-semibold">3. Resolution</p><p className="mt-2 text-[#526477]">{issue.status === 'RESOLVED' ? 'Recorded outcome accepted; order received.' : 'Receipt remains pending issue review.'}</p></li>
      </ol>
    </div>}
  </div>
}

function ReceivingForm({ delivery, onSaved }: { delivery: StoreDelivery; onSaved: (result: ReceivingResult) => void }) {
  const [mode, setMode] = useState<'confirm' | 'issue'>('confirm')
  const [receiver, setReceiver] = useState('')
  const [quantity, setQuantity] = useState(String(delivery.dispatched_quantity))
  const [notes, setNotes] = useState('')
  const [issueType, setIssueType] = useState<DeliveryIssueType>('MISSING_QUANTITY')
  const [affected, setAffected] = useState('1')
  const [accepted, setAccepted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // Retain the same key after a lost response; edits produce a different command/key.
  const attempt = useRef<{ body: string; key: string } | null>(null)
  const counted = Number(quantity)
  const missing = delivery.ordered_quantity - counted

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true); setError('')
    const receipt: ReceivingInput = { receiver_name: receiver.trim(), received_quantity: counted, notes: notes.trim() || null }
    const payload: IssueInput = { ...receipt, issue_type: issueType, affected_quantity: issueType === 'MISSING_QUANTITY' ? missing : Number(affected) }
    const body = JSON.stringify({ mode, payload: mode === 'issue' ? payload : receipt })
    if (attempt.current?.body !== body) attempt.current = { body, key: crypto.randomUUID() }
    try {
      const result = mode === 'issue' ? await reportDeliveryIssue(delivery.order_id, payload, attempt.current.key) : await submitStoreReceipt(delivery.order_id, receipt, attempt.current.key)
      onSaved(result)
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not save receiving. Retry with the same details or refresh deliveries to check the saved result.') }
    finally { setBusy(false) }
  }

  return <>
    <article className={card}><h3 className="font-bold">Delivery Details</h3><p className="mb-5 mt-1 text-sm text-[#526477]">Compare the original request and acknowledged manifest with your physical count.</p><QuantityComparison delivery={delivery} counted={Number.isFinite(counted) ? counted : 0} /></article>
    <form onSubmit={submit} className={card}>
      <h3 className="font-bold">{mode === 'issue' ? 'Report Delivery Issue' : 'Confirm Receipt'}</h3>
      <p className="mt-1 text-sm text-[#526477]">{mode === 'issue' ? 'Specify the discrepancy so the operations team can review it.' : 'Acknowledge your counted quantities, including any approved partial fulfillment.'}</p>
      <fieldset disabled={busy} className="mt-5 space-y-4 disabled:opacity-60">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">Receiver name<input className={field} required maxLength={120} value={receiver} onChange={event => setReceiver(event.target.value)} /></label>
          <label className="text-sm font-medium">Received quantity (units)<input className={field} type="number" min={0} max={delivery.dispatched_quantity} step={1} required value={quantity} onChange={event => { setQuantity(event.target.value); setAccepted(false) }} /></label>
        </div>
        {mode === 'issue' && <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">Issue type<select className={field} value={issueType} onChange={event => setIssueType(event.target.value as DeliveryIssueType)}>
            <option value="MISSING_QUANTITY">Missing Quantity</option><option value="DAMAGED">Damaged</option><option value="WRONG_ITEM">Wrong Item</option><option value="OTHER">Other</option>
          </select></label>
          <label className="text-sm font-medium">Affected quantity (units)<input className={field} type="number" min={1} max={issueType === 'MISSING_QUANTITY' ? delivery.ordered_quantity : delivery.dispatched_quantity} step={1} required readOnly={issueType === 'MISSING_QUANTITY'} value={issueType === 'MISSING_QUANTITY' ? missing : affected} onChange={event => setAffected(event.target.value)} /></label>
        </div>}
        <label className="block text-sm font-medium">{mode === 'issue' ? 'Issue details' : 'Receiving notes'}<textarea className={field} rows={3} maxLength={1000} required={mode === 'issue' || counted < delivery.dispatched_quantity} value={notes} onChange={event => setNotes(event.target.value)} /></label>
        {mode === 'confirm' && <label className="flex items-start gap-3 rounded-lg border border-blue-100 bg-[#f8fafc] p-4 text-sm"><input className="mt-1" type="checkbox" required checked={accepted} onChange={event => setAccepted(event.target.checked)} /><span>I confirm the delivery was received and the quantities entered above are correct.<span className="mt-1 block text-xs text-[#526477]">Once confirmed, the receipt is recorded and the order status is updated.</span></span></label>}
        {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
        <div className="flex flex-wrap gap-3">
          <button className={primary} disabled={busy || (mode === 'confirm' && !accepted) || (mode === 'issue' && issueType === 'MISSING_QUANTITY' && missing <= 0)} type="submit"><img src="/receipt-assets/confirm.svg" alt="" width={16} height={16} />{busy ? 'Saving…' : mode === 'issue' ? 'Submit Issue' : 'Confirm Receipt'}</button>
          <button className={secondary} type="button" onClick={() => { setMode(mode === 'confirm' ? 'issue' : 'confirm'); setError('') }}>{mode === 'confirm' && <img src="/receipt-assets/report.svg" alt="" width={16} height={16} />}{mode === 'issue' ? 'Cancel' : 'Report an Issue'}</button>
        </div>
      </fieldset>
    </form>
  </>
}

export default function StoreReceipts({ onReceived }: { onReceived: () => void }) {
  const [deliveries, setDeliveries] = useState<StoreDelivery[]>([])
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    try { const items = await listStoreDeliveries(); setDeliveries(items); setSelected(current => current || items[0]?.order_id || '') }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not load deliveries.') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  const delivery = deliveries.find(item => item.order_id === selected)

  function saved(result: ReceivingResult) {
    setDeliveries(items => items.map(item => item.order_id === selected ? { ...item, ...result } : item))
    onReceived()
  }

  return <section className="mt-8 rounded-xl bg-[#f3f7fb] p-4 text-[#10253d] sm:p-6" aria-labelledby="receipts-heading">
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-[#526477]">Store Operations / Deliveries</p><h2 id="receipts-heading" className="mt-1 text-2xl font-bold">{delivery?.issue ? 'Issue Submitted' : 'Confirm Delivery'}</h2><p className="mt-1 text-sm text-[#526477]">Review the delivered quantities before confirming receipt.</p></div><button className={secondary} disabled={loading} onClick={() => void refresh()}>Refresh deliveries</button></div>
    {error && <p role="alert" className="mb-4 text-sm text-rose-700">{error}</p>}
    {loading ? <p role="status">Loading deliveries…</p> : deliveries.length === 0 ? <p className={card}>No successfully synced deliveries are available for receipt yet.</p> : <>
      <label className="mb-5 block text-sm font-medium">Delivered order<select className={field} value={selected} onChange={event => setSelected(event.target.value)}>{deliveries.map(item => <option key={item.order_id} value={item.order_id}>{item.order_ref} · {item.receipt?.status ?? 'Awaiting receipt'}</option>)}</select></label>
      {delivery && <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(250px,1fr)]">
        <div className="min-w-0 space-y-6">
          <article className={card}><div className="flex flex-wrap justify-between gap-2"><h3 className="font-bold">Delivery Completed</h3><span className="rounded-full bg-[#e8f5ee] px-3 py-1 text-xs font-semibold text-[#147d64]">Delivered</span></div><p className="mt-2 text-sm text-[#526477]">{delivery.order_ref} · {delivery.brand} · {delivery.district} ({delivery.outlet_id})</p><p className="mt-4 text-sm">Actual delivery: {receivingTime(delivery.delivered_at)}</p></article>
          {delivery.receipt ? <><article className={card}><h3 className="mb-4 font-bold">Recorded quantity comparison</h3><QuantityComparison delivery={delivery} counted={delivery.receipt.received_quantity} /></article><ReceiptOutcome result={{ receipt: delivery.receipt, issue: delivery.issue, order_status: delivery.order_status }} /></> : <ReceivingForm key={delivery.order_id} delivery={delivery} onSaved={saved} />}
        </div>
        <aside className={card}><h3 className="font-bold">Order &amp; Manifest Reference</h3><dl className="mt-4 divide-y divide-[#e5ebf2] text-sm">
          {Object.entries({ 'Order reference': delivery.order_ref, 'Manifest version': `V${delivery.manifest_version}`, 'Vehicle': delivery.vehicle_id, 'Dispatch depot': delivery.depot_code, 'Driver': delivery.driver_name ?? 'Not recorded', 'POD receiver': delivery.pod_receiver_name ?? 'Not recorded', 'Order status': delivery.order_status }).map(([label, value]) => <div className="flex flex-wrap justify-between gap-2 py-3" key={label}><dt className="text-[#526477]">{label}</dt><dd className="break-all font-medium">{value}</dd></div>)}
        </dl>{delivery.pod_notes && <p className="mt-3 rounded-lg bg-[#f8fafc] p-3 text-sm">Driver note: {delivery.pod_notes}</p>}</aside>
      </div>}
    </>}
  </section>
}
