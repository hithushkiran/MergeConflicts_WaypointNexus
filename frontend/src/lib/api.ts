const configuredApiUrl = import.meta.env.VITE_API_URL

/** Base URL for the versioned backend API. */
export const API_BASE_URL = configuredApiUrl?.replace(/\/$/, '') ?? 'http://localhost:8000'

const TOKEN_KEY = 'waypoint.access-token'
const PROFILE_KEY = 'waypoint.driver-profile'

export type UserRole = 'STORE' | 'DISPATCHER' | 'LOADER' | 'DRIVER'

export interface UserProfile {
  id: string
  email: string
  display_name: string
  role: UserRole
  outlet_id: string | null
  depot_code: string | null
}

interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  user: UserProfile
}

export type TemperatureRequirement = 'AMBIENT' | 'CHILLED' | 'FROZEN'

export interface StoreOrder {
  id: string
  reference: string
  outlet_id: string
  requested_delivery_date: string
  temperature_requirement: TemperatureRequirement
  units: number
  weight_kg: number
  volume_m3: number
  status: string
  notes: string | null
  cutoff_at: string | null
  created_at: string
}

export interface OrderEligibility {
  cutoff_at: string
  cutoff_time: string
  next_eligible_delivery_date: string
  late_order: boolean
  explanation: string
}

export interface CreateStoreOrder {
  requested_delivery_date: string
  temperature_requirement: TemperatureRequirement
  units: number
  weight_kg: number
  volume_m3: number
  notes: string | null
}

export interface DispatcherOrder {
  id: string
  reference: string
  outlet_id: string
  brand: string
  district: string
  depot_code: string
  dock_type: string
  parking_constraint: string
  window_open_time: string | null
  window_close_time: string | null
  requested_delivery_date: string
  temperature_requirement: TemperatureRequirement
  units: number
  weight_kg: number
  volume_m3: number
  status: string
  prior_day_deferral: boolean
}

export interface DispatcherFilters {
  planning_date?: string
  depot?: string
  brand?: string
  district?: string
  temperature?: TemperatureRequirement | ''
  access?: string
  delivery_window?: 'restricted' | 'none' | ''
  prior_deferral?: 'true' | 'false' | ''
}

export interface PlanStop {
  sequence_number: number
  order_id: string
  order_ref: string
  outlet_id: string
  planned_arrival: string | null
  planned_service_minutes: number | null
}

export interface PlanTrip {
  id: string
  vehicle_id: string
  depot_code: string
  assigned_driver_id: string | null
  assigned_driver_name: string | null
  trip_number: number
  brand: string
  district: string
  status: string
  metrics: Record<string, number | boolean>
  stops: PlanStop[]
}

export interface DriverTrip {
  id: string; vehicle_id: string; vehicle_type: string | null; depot_code: string | null
  driver_name: string | null; trip_number: number; brand: string; district: string; status: string
  plan_version: number | null; manifest_version: number | null
  manifest: { version_number: number; lines: Array<{ order_id: string; order_ref: string; outlet_id: string; sequence_number: number; expected_quantity: number; loaded_quantity: number; status: string; notes: string | null }> } | null
  stops: Array<{ id: string; sequence_number: number; order_id: string; order_ref: string; outlet_id: string; brand: string; district: string; window_open_time: string | null; window_close_time: string | null; instructions: string | null; planned_arrival: string | null; planned_service_minutes: number | null; status: string; arrived_at: string | null; completed_at: string | null; receiver_name?: string; delivery_notes?: string }>
}

export interface PlanDecision {
  order_id: string
  order_ref: string
  decision: string
  vehicle_id: string | null
  trip_number: number | null
  outlet_id?: string
  district?: string
  brand?: string
  reason?: string
  notes?: string | null
}

export interface DispatcherPlan {
  id: string
  planning_run_id: string
  planning_date: string
  version_number: number
  status: string
  created_at: string
  published_at: string | null
  orders: PlanDecision[]
  trips: PlanTrip[]
  diagnostics: string[]
}

export interface ManifestLine {
  order_id: string
  order_ref: string
  outlet_id: string
  load_sequence: number
  expected_quantity: number
  loaded_quantity: number
  status: string
  notes: string | null
}

export interface LoaderTrip {
  id: string
  vehicle_id: string
  driver: string | null
  departure: string | null
  plan_version: number
  trip_number: number
  status: string
  manifest: { id: string; version_number: number; status: string; acknowledged_at: string | null; lines: ManifestLine[] }
}

export interface ShortfallItem {
  id: string
  trip_id: string | null
  order_id: string
  order_ref: string
  quantity: number
  reason: string
  blocking: boolean
  status: string
  resolution_plan_version_id: string | null
}

export async function listLoaderTrips(): Promise<LoaderTrip[]> {
  return (await request<{ items: LoaderTrip[] }>('/api/v1/loader/trips')).items
}

export async function listDispatcherDrivers(): Promise<Array<{ id: string; display_name: string; email: string; depot_code: string | null }>> {
  return (await request<{ items: Array<{ id: string; display_name: string; email: string; depot_code: string | null }> }>('/api/v1/dispatcher/drivers')).items
}

export function assignTripDriver(tripId: string, driverId: string): Promise<{ trip_id: string; driver_id: string; driver_name: string }> {
  return request(`/api/v1/dispatcher/trips/${tripId}/assign`, { method: 'POST', body: JSON.stringify({ driver_id: driverId }) })
}

export async function listDriverTrips(): Promise<DriverTrip[]> {
  return (await request<{ items: DriverTrip[] }>('/api/v1/driver/trips')).items
}

export function departDriverTrip(tripId: string, idempotencyKey: string = crypto.randomUUID(), commandId?: string, occurredAt?: string): Promise<{ trip_id: string; status: string }> {
  return request(`/api/v1/driver/trips/${tripId}/depart`, { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey, ...(commandId ? { 'X-Command-Id': commandId } : {}) }, ...(occurredAt ? { body: JSON.stringify({ occurred_at: occurredAt }) } : {}) })
}

export function arriveDriverStop(stopId: string, idempotencyKey: string = crypto.randomUUID(), commandId?: string, occurredAt?: string): Promise<{ stop_id: string; status: string }> {
  return request(`/api/v1/driver/stops/${stopId}/arrive`, { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey, ...(commandId ? { 'X-Command-Id': commandId } : {}) }, ...(occurredAt ? { body: JSON.stringify({ occurred_at: occurredAt }) } : {}) })
}

export function completeDriverStop(stopId: string, payload: { outcome: 'DELIVERED' | 'FAILED'; receiver_name: string; notes: string; occurred_at?: string }, idempotencyKey: string = crypto.randomUUID(), commandId?: string): Promise<{ stop_id: string; status: string; trip_status: string }> {
  return request(`/api/v1/driver/stops/${stopId}/complete`, { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey, ...(commandId ? { 'X-Command-Id': commandId } : {}) }, body: JSON.stringify(payload) })
}

export async function listManifestVersions(tripId: string): Promise<LoaderTrip['manifest'][]> {
  return (await request<{ items: LoaderTrip['manifest'][] }>(`/api/v1/loader/trips/${tripId}/manifests`)).items
}

export function submitLoadChecks(tripId: string, version: number, lines: Array<{ order_id: string; status: string; quantity: number; notes: string | null }>): Promise<{ manifest: LoaderTrip['manifest']; trip_status: string }> {
  return request(`/api/v1/loader/trips/${tripId}/checks`, { method: 'POST', body: JSON.stringify({ manifest_version: version, lines }) })
}

export function acknowledgeManifest(manifestId: string): Promise<{ trip_status: string }> {
  return request(`/api/v1/loader/manifests/${manifestId}/acknowledge`, { method: 'POST' })
}

export async function listShortfalls(): Promise<ShortfallItem[]> {
  return (await request<{ items: ShortfallItem[] }>('/api/v1/dispatcher/shortfalls')).items
}

export function resolveShortfall(id: string, action: string, reason: string, quantity?: number, substitute_reference?: string, target_trip_id?: string): Promise<{ candidate_plan_id?: string }> {
  return request(`/api/v1/dispatcher/shortfalls/${id}/resolve`, { method: 'POST', body: JSON.stringify({ action, reason, quantity, substitute_reference, target_trip_id }) })
}

interface ApiErrorBody {
  detail?: {
    code?: string
    message?: string
    fields?: Array<{ field: string; message: string }>
  }
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly fields: Array<{ field: string; message: string }>

  constructor(status: number, body: ApiErrorBody) {
    super(body.detail?.message ?? 'The request could not be completed.')
    this.name = 'ApiError'
    this.status = status
    this.code = body.detail?.code ?? 'HTTP_ERROR'
    this.fields = body.detail?.fields ?? []
  }
}

export function getAccessToken(): string | null {
  return typeof window === 'undefined' ? null : window.sessionStorage.getItem(TOKEN_KEY)
}

export function getCachedDriverProfile(): UserProfile | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(PROFILE_KEY)
    if (!raw) return null
    const profile = JSON.parse(raw) as UserProfile
    return profile.role === 'DRIVER' && Boolean(profile.id) ? profile : null
  } catch {
    return null
  }
}

function clearAccessToken(): void {
  if (typeof window !== 'undefined') window.sessionStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const token = authenticated ? getAccessToken() : null
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  if (response.status === 204) return undefined as T

  const body = (await response.json()) as T | ApiErrorBody
  if (!response.ok) {
    const error = new ApiError(response.status, body as ApiErrorBody)
    if (error.status === 401 && error.code !== 'INVALID_CREDENTIALS') clearAccessToken()
    throw error
  }
  return body as T
}

export async function signIn(email: string, password: string): Promise<UserProfile> {
  const result = await request<LoginResponse>(
    '/api/v1/auth/login',
    { method: 'POST', body: JSON.stringify({ email, password }) },
    false,
  )
  window.sessionStorage.setItem(TOKEN_KEY, result.access_token)
  if (result.user.role === 'DRIVER') window.localStorage.setItem(PROFILE_KEY, JSON.stringify(result.user))
  return result.user
}

export async function currentUser(): Promise<UserProfile> {
  const profile = await request<UserProfile>('/api/v1/auth/me')
  if (profile.role === 'DRIVER') window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
  return profile
}

export function getOrderEligibility(): Promise<OrderEligibility> {
  return request<OrderEligibility>('/api/v1/store/orders/eligibility')
}

export async function listStoreOrders(): Promise<StoreOrder[]> {
  const result = await request<{ items: StoreOrder[]; next_cursor: string | null }>('/api/v1/store/orders')
  return result.items
}

export function createStoreOrder(order: CreateStoreOrder, idempotencyKey: string): Promise<StoreOrder> {
  return request<StoreOrder>('/api/v1/store/orders', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(order),
  })
}

export async function listDispatcherOrders(filters: DispatcherFilters = {}): Promise<DispatcherOrder[]> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value) query.set(key, value)
  }
  const suffix = query.size ? `?${query.toString()}` : ''
  const result = await request<{ items: DispatcherOrder[]; next_cursor: string | null }>(
    `/api/v1/dispatcher/orders${suffix}`,
  )
  return result.items
}

export async function createDispatcherPlan(planningDate: string, idempotencyKey: string): Promise<DispatcherPlan> {
  const result = await request<{ plan: DispatcherPlan }>('/api/v1/dispatcher/plans', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ planning_date: planningDate }),
  })
  return result.plan
}

export async function listDispatcherPlans(planningDate?: string): Promise<DispatcherPlan[]> {
  const query = planningDate ? `?planning_date=${encodeURIComponent(planningDate)}` : ''
  const result = await request<{ items: DispatcherPlan[] }>(`/api/v1/dispatcher/plans${query}`)
  return result.items
}

export async function getDispatcherPlan(planId: string): Promise<DispatcherPlan> {
  const result = await request<{ plan: DispatcherPlan }>(`/api/v1/dispatcher/plans/${planId}`)
  return result.plan
}

export interface PublishedPlanResult {
  plan_version_id: string
  version_number: number
  status: 'PUBLISHED'
  published_at: string
  served_orders: number
  deferred_orders: number
  replayed: boolean
}

export function publishDispatcherPlan(planId: string, idempotencyKey: string, reason: string): Promise<PublishedPlanResult> {
  return request<PublishedPlanResult>(`/api/v1/dispatcher/plans/${planId}/publish`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ reason: reason.trim() || null }),
  })
}

export async function signOut(): Promise<void> {
  try {
    await request<void>('/api/v1/auth/logout', { method: 'POST' })
  } finally {
    clearAccessToken()
    if (typeof window !== 'undefined') window.localStorage.removeItem(PROFILE_KEY)
  }
}
