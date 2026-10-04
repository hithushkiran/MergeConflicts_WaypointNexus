const configuredApiUrl = import.meta.env.VITE_API_URL

/** Base URL for the versioned backend API. */
export const API_BASE_URL = configuredApiUrl?.replace(/\/$/, '') ?? 'http://localhost:8000'

const TOKEN_KEY = 'waypoint.access-token'

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
  trip_number: number
  brand: string
  district: string
  status: string
  metrics: Record<string, number | boolean>
  stops: PlanStop[]
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
  return result.user
}

export function currentUser(): Promise<UserProfile> {
  return request<UserProfile>('/api/v1/auth/me')
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
  }
}
