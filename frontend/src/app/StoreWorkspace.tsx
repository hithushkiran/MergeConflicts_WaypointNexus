import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, createStoreOrder, getOrderEligibility, listStoreOrders, listStoreIssues, type DeliveryIssueItem, type OrderEligibility, type StoreOrder, type TemperatureRequirement, type UserProfile } from '../lib/api'
import { receivingTime } from '../lib/receivingTime'
import StoreReceipts from './StoreReceipts'
import { Alert, Button, Facts, PageHeading, Panel, StatusBadge } from './ui'

type View = 'list' | 'create' | 'submitted' | 'detail'
export default function StoreWorkspace({ user, deliveries = false }: { user: UserProfile; deliveries?: boolean }) {
  const [orders, setOrders] = useState<StoreOrder[]>([])
  const [issues, setIssues] = useState<DeliveryIssueItem[]>([])
  const [timing, setTiming] = useState<OrderEligibility | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [view, setView] = useState<View>('list')
  const [selected, setSelected] = useState<StoreOrder | null>(null)
  const [date, setDate] = useState('')
  const [temperature, setTemperature] = useState<TemperatureRequirement>('AMBIENT')
  const [units, setUnits] = useState('')
  const [weight, setWeight] = useState('')
  const [volume, setVolume] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const attempt = useRef<{ body: string; key: string } | null>(null)
  const titleRef = useRef<HTMLDivElement>(null)
  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [items, eligibility, cases] = await Promise.all([listStoreOrders(), getOrderEligibility(), listStoreIssues()])
      setIssues(cases)
      setOrders(items); setTiming(eligibility); setDate(current => current || eligibility.next_eligible_delivery_date)
      setSelected(current => current ? items.find(item => item.id === current.id) ?? current : null)
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not load your orders. Please retry.') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => { titleRef.current?.querySelector('h1')?.focus() }, [view])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setBusy(true)
    const payload = { requested_delivery_date: date, temperature_requirement: temperature, units: Number(units), weight_kg: Number(weight), volume_m3: Number(volume), notes: notes.trim() || null }
    const body = JSON.stringify(payload)
    if (attempt.current?.body !== body) attempt.current = { body, key: crypto.randomUUID() }
    try {
      const order = await createStoreOrder(payload, attempt.current.key)
      setSelected(order); setOrders(items => [order, ...items.filter(item => item.id !== order.id)])
      setView('submitted'); attempt.current = null; setNotes(''); setUnits(''); setWeight(''); setVolume('')
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : 'Could not submit. Retry uses the same request key to prevent duplicates.') }
    finally { setBusy(false) }
  }

  function go(next: View) { setError(''); setView(next) }
  const summary = selected ? { 'Order ID': <code>{selected.reference}</code>, 'Order Type': selected.temperature_requirement, 'Quantity': `${selected.units} units`, 'Payload Weight': `${selected.weight_kg} kg`, 'Volume': `${selected.volume_m3} m³`, 'Delivery Date': selected.requested_delivery_date, 'Target Outlet': selected.outlet_id, 'Submitted At': receivingTime(selected.created_at), 'Status': <StatusBadge status={selected.status} /> } : {}
  if (deliveries) return <StoreReceipts onReceived={() => { void refresh() }} />
  const pageTitle = view === 'create' ? 'Create Order' : view === 'submitted' ? 'Order Submitted' : view === 'detail' ? selected?.status === 'DEFERRED' ? 'Delivery Deferred' : 'Delivery Status' : 'Orders'
  return <div ref={titleRef} className="wp-store">
    <PageHeading title={pageTitle} description={view === 'list' ? 'Monitor submitted orders, delivery status and receiving outcomes.' : view === 'create' ? 'Submit a new delivery order for your store.' : view === 'submitted' ? 'Your order has been successfully submitted for dispatcher planning.' : 'Review the recorded status and quantities for your order.'}
      actions={view === 'list' ? <><Button variant="secondary" disabled={loading} onClick={() => void refresh()}>Refresh</Button><Button onClick={() => go('create')}><img src="/figma-assets/create.svg" alt="" />Create Order</Button></> : <Button variant="secondary" disabled={busy} onClick={() => go('list')}>{view === 'create' ? 'Cancel' : 'Back to Orders'}</Button>} />
    {error && <Alert tone="error">{error} <button className="wp-inline-link" disabled={loading || busy} onClick={() => void refresh()}>Retry loading</button></Alert>}
    {view === 'list' && <>
      <Panel className="wp-context-strip"><Facts values={{ 'Store': user.outlet_id ?? 'No outlet assigned', 'Account': user.display_name, 'Earliest eligible date': timing?.next_eligible_delivery_date ?? 'Unavailable', 'Order cutoff': timing ? `${timing.cutoff_time} Colombo` : 'Unavailable' }} /></Panel>
      <div className="wp-stats">{[
        ['Loaded Orders', orders.length, 'order-count'], ['Confirmed', orders.filter(item => item.status === 'CONFIRMED').length, 'confirmed-count'], ['Planned', orders.filter(item => item.status === 'PLANNED').length, 'planned-count'], ['Open Issues', issues.filter(item => item.status !== 'RESOLVED').length, 'issue-count'],
      ].map(([label, value, icon]) => <Panel key={label}><div className="wp-stat-label"><span>{label}</span><span className="wp-stat-icon"><img src={`/figma-assets/${icon}.svg`} alt="" /></span></div><strong className="wp-stat-value">{loading ? '—' : value}</strong><p className="wp-muted">{label === 'Open Issues' ? 'Awaiting operations review' : 'Current loaded order list'}</p></Panel>)}</div>
      <div className="wp-two-column"><Panel className="wp-table-panel"><div className="wp-table-heading"><h2>Recent Orders</h2><p>Orders submitted by your store and their current delivery status.</p></div>
        {loading ? <p className="wp-empty" role="status">Loading your orders…</p> : orders.length === 0 ? <p className="wp-empty">No orders yet. Create your first delivery request above.</p> : <><div className="wp-table-scroll" tabIndex={0} role="region" aria-label="Store orders table"><table className="wp-table"><caption className="sr-only">Recent orders for your assigned outlet</caption><thead><tr><th>Order</th><th>Type</th><th>Quantity &amp; Volume</th><th>Delivery Date</th><th>Status</th><th>Action</th></tr></thead><tbody>{orders.map(order => <tr key={order.id}><th><code>{order.reference}</code><small>{order.outlet_id}</small></th><td>{order.temperature_requirement}</td><td><strong>{order.weight_kg} kg</strong><small>{order.units} units · {order.volume_m3} m³</small></td><td>{order.requested_delivery_date}</td><td><StatusBadge status={order.status} /></td><td><Button variant="secondary" aria-label={`View order ${order.reference}`} onClick={() => { setSelected(order); go('detail') }}>View</Button></td></tr>)}</tbody></table></div><footer className="wp-table-footer">Showing {orders.length} returned orders · {orders.reduce((sum, item) => sum + item.weight_kg, 0)} kg total requested</footer></>}
      </Panel><aside className="wp-side-panels"><Panel title="Delivery Overview"><p className="wp-muted">Pre-delivery ETA and vehicle assignment are not provided by the current store API.</p><Facts values={{ 'Awaiting Receipt': orders.filter(item => item.status === 'DELIVERED').length, 'Received': orders.filter(item => item.status === 'RECEIVED').length }} /><p className="wp-muted">Open Deliveries to compare a successfully synced delivery with its acknowledged manifest.</p></Panel><Panel title="Ordering Context">{timing ? <Alert tone={timing.late_order ? 'warning' : 'info'}>{timing.explanation}</Alert> : <p className="wp-muted">Cutoff information is unavailable. Retry loading before submitting an order.</p>}<p className="wp-muted">Each request is a separate shipment line. Keep ambient and chilled requirements distinct during ordering.</p></Panel></aside></div>
    </>}
    {view === 'create' && <>
      <Panel className="wp-context-strip"><Facts values={{ 'Store': user.outlet_id ?? 'No outlet assigned', 'Delivery Date': date || 'Choose date', 'Submission Window': timing ? `${timing.cutoff_time} Colombo cutoff` : 'Loading eligibility' }} /></Panel>
      <div className="wp-two-column"><form onSubmit={submit} className="wp-panel"><fieldset disabled={busy}><legend className="wp-panel-title">Order Details</legend><p className="wp-field-heading">Order Type</p><p className="wp-muted">Select the temperature requirement for this shipment.</p><div className="wp-temperature-options">{(['AMBIENT', 'CHILLED', 'FROZEN'] as const).map(value => <label className={temperature === value ? 'is-selected' : ''} key={value}><input type="radio" name="temperature" checked={temperature === value} onChange={() => setTemperature(value)} /><span><strong>{value === 'AMBIENT' ? 'Dry Goods' : value === 'CHILLED' ? 'Chilled Goods' : 'Frozen Goods'}</strong><small>{value === 'AMBIENT' ? 'Ambient temperature cargo' : value === 'CHILLED' ? 'Refrigerated shipment' : 'Frozen shipment'}</small></span></label>)}</div>
        <h2 className="wp-field-heading">Shipment Quantities</h2><p className="wp-muted">One shipment per order; no product catalog is configured.</p><div className="wp-form-grid"><label>Units<input name="units" required type="number" min="1" step="1" value={units} onChange={event => setUnits(event.target.value)} /></label><label>Total weight (kg)<input name="weight" required type="number" min="0.01" step="0.01" value={weight} onChange={event => setWeight(event.target.value)} /></label><label>Total volume (m³)<input name="volume" required type="number" min="0.01" step="0.01" value={volume} onChange={event => setVolume(event.target.value)} /></label><label>Delivery Date<input name="delivery-date" required type="date" min={timing?.next_eligible_delivery_date} value={date} onChange={event => setDate(event.target.value)} /></label><label className="wp-wide">Notes (optional)<textarea name="order-notes" rows={3} maxLength={500} value={notes} onChange={event => setNotes(event.target.value)} /></label></div>
        {timing && <Alert tone={timing.late_order ? 'warning' : 'info'}>{timing.explanation}</Alert>}<div className="wp-form-footer"><Button variant="secondary" onClick={() => go('list')}>Cancel</Button><Button type="submit" disabled={loading || !timing || !user.outlet_id}>{busy ? 'Submitting…' : 'Submit Order'}</Button></div>
      </fieldset></form><aside className="wp-side-panels"><Panel title="Order Summary"><Facts values={{ 'Order Reference': 'Assigned after submission', 'Order Type': temperature, 'Units': units || '—', 'Total Weight': weight ? `${weight} kg` : '—', 'Total Volume': volume ? `${volume} m³` : '—', 'Outlet': user.outlet_id, 'Delivery Date': date }} /></Panel><Panel title="Planning Context"><p className="wp-muted">Vehicle, depot, capacity and route validation belong to dispatcher planning. A submission is not a vehicle assignment.</p></Panel></aside></div>
    </>}
    {view === 'submitted' && selected && <div className="wp-two-column"><div className="wp-side-panels"><Panel><div className="wp-submitted"><span><img src="/figma-assets/order-submitted.svg" alt="" /></span><div><h2>Order Submitted</h2><p>Your order has been saved and is available for dispatcher planning.</p></div><StatusBadge status={selected.status} /></div><h3 className="wp-section-label">Structured Order Summary</h3><Facts values={summary} /></Panel><Panel title="Dispatcher Handoff"><Alert>Next step: vehicle and route planning</Alert><p className="wp-muted">The dispatcher validates capacity, delivery constraints and route availability before publishing a plan.</p></Panel></div><aside className="wp-side-panels"><Panel title="What happens next?"><ol className="wp-next-steps"><li><strong>Order received</strong><p>Submission confirmed and recorded for your outlet.</p></li><li><strong>Dispatcher plans delivery</strong><p>Vehicle and delivery constraints are validated.</p></li><li><strong>Store reviews status</strong><p>Return to Orders to check the recorded status. ETA is not exposed by this API.</p></li></ol></Panel><div className="wp-info-note"><img src="/figma-assets/order-info.svg" alt="" /><p>Your order remains visible in Orders while the dispatcher completes planning.</p></div><Button onClick={() => go('detail')}>View Order</Button></aside></div>}
    {view === 'detail' && selected && <div className="wp-two-column"><div className="wp-side-panels"><Panel><div className="wp-detail-header"><h2>{selected.status === 'DEFERRED' ? 'Delivery Deferred' : selected.status === 'PLANNED' ? 'Delivery Planned' : 'Order Details'}</h2><StatusBadge status={selected.status} /></div><Facts values={summary} />{selected.notes && <p className="wp-order-note">Order note: {selected.notes}</p>}</Panel><Panel title={selected.status === 'DEFERRED' ? 'Why was this delivery deferred?' : 'Delivery Information'}><p className="wp-muted">{selected.status === 'DEFERRED' ? 'The stored status is deferred. The current store API does not provide the planner’s deferral reason or a proposed next run; no replacement ETA is implied.' : 'Pre-delivery ETA, delivery window and vehicle details are not included in the store order response. Successfully synced delivery details are available under Deliveries.'}</p></Panel></div><aside className="wp-side-panels"><Panel title="Operational Status"><Facts values={{ 'Current State': <StatusBadge status={selected.status} />, 'Requested Date': selected.requested_delivery_date, 'Submitted': receivingTime(selected.created_at) }} /><p className="wp-muted">This is the last retrieved server record, not a live route feed.</p><Button variant="secondary" disabled={loading} onClick={() => void refresh()}>Refresh order status</Button></Panel></aside></div>}
  </div>
}
