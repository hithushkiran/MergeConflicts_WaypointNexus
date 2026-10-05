import {
  ApiError,
  arriveDriverStop,
  completeDriverStop,
  departDriverTrip,
  currentUser,
  getAccessToken,
  type DriverTrip,
} from './api'

const DATABASE_NAME = 'waypoint-driver-offline'
const DATABASE_VERSION = 1
const CACHE_SCHEMA_VERSION = 1
const MAX_RETRY_MS = 60_000
// Earlier clients stored only the API message when incorrectly blocking auth.
// Recover only the two exact identity-contract messages; preserve other conflicts.
const LEGACY_AUTH_ERRORS = new Set(['The bearer token is invalid or expired.', 'A bearer token is required.'])

export type DriverCommandInput =
  | { kind: 'DEPART'; trip_id: string }
  | { kind: 'ARRIVE'; trip_id: string; stop_id: string }
  | { kind: 'COMPLETE'; trip_id: string; stop_id: string; outcome: 'DELIVERED' | 'FAILED'; receiver_name: string; notes: string }

export type DriverCommand =
  | { kind: 'DEPART'; trip_id: string; occurred_at: string }
  | { kind: 'ARRIVE'; trip_id: string; stop_id: string; occurred_at: string }
  | { kind: 'COMPLETE'; trip_id: string; stop_id: string; outcome: 'DELIVERED' | 'FAILED'; receiver_name: string; notes: string; occurred_at: string }

export interface QueuedDriverCommand {
  id: string
  idempotency_key: string
  user_id: string
  command: DriverCommand
  created_at: number
  attempts: number
  next_attempt_at: number
  state: 'PENDING' | 'AUTH_REQUIRED' | 'CONFLICT'
  error: string | null
}

type CachedTrip = { key: string; user_id: string; schema_version: number; saved_at: number; trip: DriverTrip }

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Local offline storage could not complete this request.'))
  })
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onabort = transaction.onerror = () => reject(transaction.error ?? new Error('Local offline storage could not save this change.'))
  })
}

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === 'undefined') return Promise.reject(new Error('This browser does not support offline trip storage.'))
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains('trips')) {
        const trips = database.createObjectStore('trips', { keyPath: 'key' })
        trips.createIndex('user_id', 'user_id', { unique: false })
      }
      if (!database.objectStoreNames.contains('outbox')) {
        const outbox = database.createObjectStore('outbox', { keyPath: 'id' })
        outbox.createIndex('user_id', 'user_id', { unique: false })
        outbox.createIndex('created_at', 'created_at', { unique: false })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Offline trip storage could not be opened.'))
    request.onblocked = () => reject(new Error('Close another Waypoint Nexus tab to finish updating offline trip storage.'))
  })
}

function tripKey(userId: string, tripId: string): string {
  return `${userId}:${tripId}`
}

export async function cacheDriverTrips(userId: string, trips: DriverTrip[]): Promise<void> {
  const database = await openDatabase()
  const transaction = database.transaction('trips', 'readwrite')
  const store = transaction.objectStore('trips')
  for (const trip of trips) store.put({ key: tripKey(userId, trip.id), user_id: userId, schema_version: CACHE_SCHEMA_VERSION, saved_at: Date.now(), trip } satisfies CachedTrip)
  await transactionDone(transaction)
  database.close()
}

export async function readCachedDriverTrips(userId: string): Promise<DriverTrip[]> {
  const database = await openDatabase()
  const transaction = database.transaction('trips', 'readonly')
  const rows = await requestResult(transaction.objectStore('trips').index('user_id').getAll(userId)) as CachedTrip[]
  await transactionDone(transaction)
  database.close()
  return rows.filter((row) => row.schema_version === CACHE_SCHEMA_VERSION).map((row) => row.trip)
}

export async function readDriverOutbox(userId: string): Promise<QueuedDriverCommand[]> {
  const database = await openDatabase()
  const transaction = database.transaction('outbox', 'readonly')
  const rows = await requestResult(transaction.objectStore('outbox').index('user_id').getAll(userId)) as QueuedDriverCommand[]
  await transactionDone(transaction)
  database.close()
  return rows.sort((left, right) => left.created_at - right.created_at)
}

export async function saveDeliveryDraft(userId: string, tripId: string, stopId: string, receiverName: string, notes: string): Promise<void> {
  const database = await openDatabase()
  const transaction = database.transaction('trips', 'readwrite')
  const store = transaction.objectStore('trips')
  const key = tripKey(userId, tripId)
  const cached = await requestResult(store.get(key)) as CachedTrip | undefined
  if (cached && cached.schema_version === CACHE_SCHEMA_VERSION) {
    const stops = cached.trip.stops.map((stop) => stop.id === stopId ? { ...stop, receiver_name: receiverName, delivery_notes: notes } : stop)
    store.put({ ...cached, saved_at: Date.now(), trip: { ...cached.trip, stops } } satisfies CachedTrip)
  }
  await transactionDone(transaction)
  database.close()
}

function applyCommand(trip: DriverTrip, command: DriverCommand): DriverTrip {
  if (command.kind === 'DEPART') return { ...trip, status: 'IN_PROGRESS' }
  const stops = trip.stops.map((stop) => {
    if (stop.id !== command.stop_id) return stop
    if (command.kind === 'ARRIVE') return { ...stop, status: 'ARRIVED', arrived_at: command.occurred_at }
    return { ...stop, status: command.outcome, completed_at: command.occurred_at, receiver_name: command.receiver_name, delivery_notes: command.notes }
  })
  const completed = stops.every((stop) => stop.status === 'DELIVERED' || stop.status === 'FAILED')
  return { ...trip, stops, status: completed ? 'COMPLETED' : trip.status }
}

export async function enqueueDriverCommand(userId: string, command: DriverCommandInput): Promise<QueuedDriverCommand> {
  const database = await openDatabase()
  const transaction = database.transaction(['trips', 'outbox'], 'readwrite')
  const key = tripKey(userId, command.trip_id)
  const tripStore = transaction.objectStore('trips')
  const cached = await requestResult(tripStore.get(key)) as CachedTrip | undefined
  if (!cached || cached.schema_version !== CACHE_SCHEMA_VERSION) {
    transaction.abort()
    database.close()
    throw new Error('This trip is not saved for offline use. Open it while connected before recording offline work.')
  }
  const existing = await requestResult(transaction.objectStore('outbox').index('user_id').getAll(userId)) as QueuedDriverCommand[]
  const now = Date.now()
  // IndexedDB returns equal timestamps in UUID-key order. Allocate a persisted,
  // monotonic queue position inside this transaction, even if the clock moves back.
  const createdAt = existing.reduce((position, entry) => Math.max(position, entry.created_at + 1), now)
  const queued: QueuedDriverCommand = {
    id: crypto.randomUUID(), idempotency_key: crypto.randomUUID(), user_id: userId,
    command: { ...command, occurred_at: new Date(now).toISOString() } as DriverCommand, created_at: createdAt, attempts: 0, next_attempt_at: now, state: 'PENDING', error: null,
  }
  tripStore.put({ ...cached, saved_at: now, trip: applyCommand(cached.trip, queued.command) } satisfies CachedTrip)
  transaction.objectStore('outbox').add(queued)
  await transactionDone(transaction)
  database.close()
  return queued
}

export function applyPendingCommands(trips: DriverTrip[], commands: QueuedDriverCommand[]): DriverTrip[] {
  const byId = new Map(trips.map((trip) => [trip.id, trip]))
  for (const entry of commands) {
    const trip = byId.get(entry.command.trip_id)
    if (trip) byId.set(trip.id, applyCommand(trip, entry.command))
  }
  return [...byId.values()]
}

async function execute(command: QueuedDriverCommand): Promise<void> {
  const { command: item, idempotency_key: key } = command
  if (item.kind === 'DEPART') await departDriverTrip(item.trip_id, key, command.id, item.occurred_at)
  else if (item.kind === 'ARRIVE') await arriveDriverStop(item.stop_id, key, command.id, item.occurred_at)
  else await completeDriverStop(item.stop_id, { outcome: item.outcome, receiver_name: item.receiver_name, notes: item.notes, occurred_at: item.occurred_at }, key, command.id)
}

async function updateOutbox(entry: QueuedDriverCommand): Promise<void> {
  const database = await openDatabase()
  const transaction = database.transaction('outbox', 'readwrite')
  transaction.objectStore('outbox').put(entry)
  await transactionDone(transaction)
  database.close()
}

async function deleteOutbox(id: string): Promise<void> {
  const database = await openDatabase()
  const transaction = database.transaction('outbox', 'readwrite')
  transaction.objectStore('outbox').delete(id)
  await transactionDone(transaction)
  database.close()
}

type SyncResult = { pending: QueuedDriverCommand[]; next_attempt_at: number | null; authentication_required: boolean }
const activeSync = new Map<string, Promise<SyncResult>>()

export function syncDriverOutbox(userId: string): Promise<SyncResult> {
  const running = activeSync.get(userId)
  if (running) return running
  const syncing = (async () => {
    let queue = await readDriverOutbox(userId)
    for (const entry of queue) {
      if (entry.state === 'CONFLICT' && entry.error && LEGACY_AUTH_ERRORS.has(entry.error)) {
        entry.state = 'AUTH_REQUIRED'
        await updateOutbox(entry)
      }
    }
    let authenticationRequired = false
    const token = getAccessToken()
    for (const entry of queue) {
      if (entry.state === 'CONFLICT') break
      if (!navigator.onLine) break
      if (entry.next_attempt_at > Date.now()) break
      try {
        // A cached profile is never authority to replay another driver's work.
        const profile = await currentUser()
        if (profile.id !== userId || profile.role !== 'DRIVER' || getAccessToken() !== token) {
          authenticationRequired = true
          break
        }
        await execute(entry)
        await deleteOutbox(entry.id)
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          await updateOutbox({ ...entry, state: 'AUTH_REQUIRED', error: 'Sign in again with the same driver account to sync saved updates.' })
          authenticationRequired = true
          break
        }
        const transient = !(error instanceof ApiError) || error.status >= 500
        if (transient) {
          const attempts = entry.attempts + 1
          const delay = Math.min(1000 * (2 ** Math.min(attempts, 6)), MAX_RETRY_MS)
          await updateOutbox({ ...entry, state: 'PENDING', attempts, next_attempt_at: Date.now() + delay, error: error instanceof Error ? error.message : 'The delivery update will retry.' })
        } else {
          await updateOutbox({ ...entry, state: 'CONFLICT', error: error.message })
        }
        break
      }
    }
    queue = await readDriverOutbox(userId)
    const pending = queue.filter((entry) => entry.state === 'PENDING')
    const hasConflict = queue.some((entry) => entry.state === 'CONFLICT')
    return { pending: queue, authentication_required: authenticationRequired, next_attempt_at: !authenticationRequired && !hasConflict && pending.length ? Math.min(...pending.map((entry) => entry.next_attempt_at)) : null }
  })().finally(() => { activeSync.delete(userId) })
  activeSync.set(userId, syncing)
  return syncing
}
