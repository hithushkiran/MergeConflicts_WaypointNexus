import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { QuantityComparison, ReceiptOutcome } from './StoreReceipts'
import type { StoreDelivery, StoreReceipt } from '../lib/api'

const delivery: StoreDelivery = {
  order_id: 'order-1', order_ref: 'ORD-1', order_status: 'DELIVERED', outlet_id: 'OUT-1',
  brand: 'Fresh', district: 'Colombo', depot_code: 'Peliyagoda', temperature_requirement: 'CHILLED',
  ordered_quantity: 18, ordered_weight_kg: 180, dispatched_quantity: 16,
  trip_stop_id: 'stop-1', manifest_version_id: 'manifest-2', manifest_version: 2,
  vehicle_id: 'vehicle-1', vehicle_type: 'VAN', driver_name: 'Driver',
  delivered_at: '2026-10-04T12:00:00Z', pod_receiver_name: 'Dock team', pod_notes: null,
  receipt: null, issue: null,
}
const receipt: StoreReceipt = {
  id: 'receipt-1', order_id: 'order-1', trip_stop_id: 'stop-1', status: 'PARTIAL',
  receiver_name: 'Store receiver', received_quantity: 16, ordered_quantity: 18, dispatched_quantity: 16,
  confirmed_by_id: 'store-1', confirmed_at: '2026-10-04T12:00:00Z', notes: null, manifest_version_id: 'manifest-2',
}

describe('store receiving presentation', () => {
  it('compares original, dispatched and counted units without relabeling units as kg', () => {
    const markup = renderToStaticMarkup(<QuantityComparison delivery={delivery} counted={16} />)
    expect(markup).toContain('2 units short')
    expect(markup).toContain('160.0 kg (proportional estimate)')
    expect(markup).toContain('Dispatched')
  })
  it('does not fabricate zero quantities or matching facts for legacy receipts', () => {
    const markup = renderToStaticMarkup(<QuantityComparison delivery={delivery} counted={null} />)
    expect(markup).toContain('Unknown')
    expect(markup).not.toContain('units short')
    expect(markup).not.toContain('>Match<')
  })
  it('shows stored receiver, reference and Colombo timestamp for confirmation', () => {
    const markup = renderToStaticMarkup(<ReceiptOutcome result={{ receipt, issue: null, order_status: 'RECEIVED' }} />)
    expect(markup).toContain('Receipt Confirmed')
    expect(markup).toContain('receipt-1')
    expect(markup).toContain('Store receiver')
    expect(markup).toContain('17:30 Colombo')
    expect(markup).not.toContain('Operations Review')
  })
  it('keeps a resolved case traceable without promising a replacement', () => {
    const markup = renderToStaticMarkup(<ReceiptOutcome result={{ receipt, order_status: 'RECEIVED', issue: {
      id: 'case-1', receipt_id: receipt.id, order_id: receipt.order_id, issue_type: 'MISSING_QUANTITY',
      status: 'RESOLVED', affected_quantity: 2, notes: 'Approved shortfall', created_at: '2026-10-04T12:00:00Z',
      reported_by_id: 'store-1', resolution_notes: 'Accepted partial intake',
      resolved_at: '2026-10-04T12:30:00Z', resolved_by_id: 'dispatcher-1',
    } }} />)
    expect(markup).toContain('case-1')
    expect(markup).toContain('RESOLVED')
    expect(markup).toContain('Accepted partial intake')
    expect(markup).toContain('Recorded outcome accepted; order received.')
    expect(markup).not.toContain('replacement')
  })
})
