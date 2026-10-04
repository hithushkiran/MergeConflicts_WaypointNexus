import 'fake-indexeddb/auto'

import { describe, expect, it } from 'vitest'

import { afterEach, beforeEach, vi } from 'vitest'
import { applyPendingCommands, cacheDriverTrips, enqueueDriverCommand, readCachedDriverTrips, readDriverOutbox, saveDeliveryDraft, syncDriverOutbox, type DriverCommandInput, type QueuedDriverCommand } from './driverOffline'
import type { DriverTrip } from './api'

const trip: DriverTrip = {
  id: 'trip-1', vehicle_id: 'VH-1', vehicle_type: 'VAN', depot_code: 'Peliyagoda', driver_name: 'Test Driver',
  trip_number: 1, brand: 'Fresh', district: 'Colombo', status: 'READY', plan_version: 3, manifest_version: 2,
  manifest: { version_number: 2, lines: [{ order_id: 'order-1', order_ref: 'ORD-1', outlet_id: 'OUT-1', sequence_number: 1, expected_quantity: 2, loaded_quantity: 2, status: 'LOADED', notes: null }] },
  stops: [{ id: 'stop-1', sequence_number: 1, order_id: 'order-1', order_ref: 'ORD-1', outlet_id: 'OUT-1', brand: 'Fresh', district: 'Colombo', window_open_time: null, window_close_time: null, instructions: null, planned_arrival: null, planned_service_minutes: 5, status: 'PENDING', arrived_at: null, completed_at: null }],
}

function queued(id: string, command: DriverCommandInput): QueuedDriverCommand {
  return { id, idempotency_key: `key-${id}`, user_id: 'driver-1', command: { ...command, occurred_at: new Date(Number(id)).toISOString() } as QueuedDriverCommand['command'], created_at: Number(id), attempts: 0, next_attempt_at: 0, state: 'PENDING', error: null }
}

describe('offline driver command overlay', () => {
  it('restores an ordered delivery draft after reload from the persistent outbox', () => {
    const restored = applyPendingCommands([trip], [
      queued('1', { kind: 'DEPART', trip_id: 'trip-1' }),
      queued('2', { kind: 'ARRIVE', trip_id: 'trip-1', stop_id: 'stop-1' }),
      queued('3', { kind: 'COMPLETE', trip_id: 'trip-1', stop_id: 'stop-1', outcome: 'DELIVERED', receiver_name: 'Receiving team', notes: 'Signed at bay' }),
    ])

    expect(restored[0].status).toBe('COMPLETED')
    expect(restored[0].stops[0]).toMatchObject({ status: 'DELIVERED', receiver_name: 'Receiving team', delivery_notes: 'Signed at bay' })
    expect(restored[0].manifest?.version_number).toBe(2)
  })

  beforeEach(async () => {
    await new Promise<void>((resolve, reject) => {
      const deletion = indexedDB.deleteDatabase('waypoint-driver-offline')
      deletion.onsuccess = () => resolve()
      deletion.onerror = () => reject(deletion.error)
    })
    vi.stubGlobal('navigator', { onLine: true })
  })

  afterEach(() => vi.unstubAllGlobals())

  it('persists trips, drafts, and commands and syncs each command once with stable IDs', async () => {
    await cacheDriverTrips('driver-1', [trip])
    await saveDeliveryDraft('driver-1', trip.id, 'stop-1', 'Receiving team', 'Drafted offline')
    await enqueueDriverCommand('driver-1', { kind: 'DEPART', trip_id: trip.id })
    await enqueueDriverCommand('driver-1', { kind: 'ARRIVE', trip_id: trip.id, stop_id: 'stop-1' })
    await enqueueDriverCommand('driver-1', { kind: 'COMPLETE', trip_id: trip.id, stop_id: 'stop-1', outcome: 'DELIVERED', receiver_name: 'Receiving team', notes: 'Drafted offline' })

    const restoredTrips = await readCachedDriverTrips('driver-1')
    expect(restoredTrips[0].stops[0]).toMatchObject({ receiver_name: 'Receiving team', delivery_notes: 'Drafted offline' })
    const pending = await readDriverOutbox('driver-1')
    expect(applyPendingCommands(restoredTrips, pending)[0]).toMatchObject({ status: 'COMPLETED' })

    const observedHeaders: Headers[] = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (input) observedHeaders.push(new Headers(init?.headers))
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock)
    const result = await syncDriverOutbox('driver-1')
    expect(result.pending).toEqual([])
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const headers = observedHeaders
    expect(headers.map((item) => item.get('X-Command-Id'))).toEqual(pending.map((entry) => entry.id))
    expect(headers.map((item) => item.get('Idempotency-Key'))).toEqual(pending.map((entry) => entry.idempotency_key))

    await syncDriverOutbox('driver-1')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(await readDriverOutbox('driver-1')).toEqual([])
  })

  it('retries a lost response after backoff with the same command and idempotency keys', async () => {
    await cacheDriverTrips('driver-1', [trip])
    const entry = await enqueueDriverCommand('driver-1', { kind: 'DEPART', trip_id: trip.id })
    const requestBodies: string[] = []
    const fetchMock = vi.fn()
      .mockImplementationOnce(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (input) requestBodies.push(String(init?.body))
        throw new TypeError('connection lost after request')
      })
      .mockImplementationOnce(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (input) requestBodies.push(String(init?.body))
        return new Response(JSON.stringify({ status: 'IN_PROGRESS', replayed: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      })
    vi.stubGlobal('fetch', fetchMock)

    const failed = await syncDriverOutbox('driver-1')
    expect(failed.pending[0]).toMatchObject({ id: entry.id, idempotency_key: entry.idempotency_key, attempts: 1, state: 'PENDING' })
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const opening = indexedDB.open('waypoint-driver-offline', 1)
      opening.onsuccess = () => resolve(opening.result)
      opening.onerror = () => reject(opening.error)
    })
    const transaction = database.transaction('outbox', 'readwrite')
    const request = transaction.objectStore('outbox').get(entry.id)
    await new Promise<void>((resolve, reject) => {
      request.onsuccess = () => { transaction.objectStore('outbox').put({ ...request.result, next_attempt_at: 0 }); resolve() }
      request.onerror = () => reject(request.error)
    })
    await new Promise<void>((resolve, reject) => { transaction.oncomplete = () => resolve(); transaction.onerror = () => reject(transaction.error) })
    database.close()

    const retried = await syncDriverOutbox('driver-1')
    expect(retried.pending).toEqual([])
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const firstHeaders = new Headers(fetchMock.mock.calls[0][1]?.headers)
    const retryHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers)
    expect(retryHeaders.get('X-Command-Id')).toBe(firstHeaders.get('X-Command-Id'))
    expect(retryHeaders.get('Idempotency-Key')).toBe(firstHeaders.get('Idempotency-Key'))
    expect(requestBodies[0]).toBe(requestBodies[1])
    expect(JSON.parse(requestBodies[1]).occurred_at).toBe(entry.command.occurred_at)
  })

  it('holds later commands when the server reports a state conflict', async () => {
    await cacheDriverTrips('driver-1', [trip])
    await enqueueDriverCommand('driver-1', { kind: 'DEPART', trip_id: trip.id })
    await enqueueDriverCommand('driver-1', { kind: 'ARRIVE', trip_id: trip.id, stop_id: 'stop-1' })
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: { code: 'TRIP_NOT_READY', message: 'The trip is no longer ready.' } }), { status: 409, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await syncDriverOutbox('driver-1')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result.pending.map((entry) => entry.state)).toEqual(['CONFLICT', 'PENDING'])
    expect(result.next_attempt_at).toBeNull()
  })
})
