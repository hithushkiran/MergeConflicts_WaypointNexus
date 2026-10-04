import type { UserRole } from './api'

export type WorkspacePage = 'orders' | 'deliveries' | 'account' | 'planning' | 'exceptions' | 'issues' | 'loading' | 'driver'
export const rolePages: Record<UserRole, Array<{ id: WorkspacePage; label: string; icon?: string }>> = {
  STORE: [{ id: 'orders', label: 'Orders', icon: 'orders' }, { id: 'deliveries', label: 'Deliveries', icon: 'deliveries' }, { id: 'account', label: 'Store', icon: 'store' }],
  DISPATCHER: [{ id: 'planning', label: 'Orders & Planning' }, { id: 'exceptions', label: 'Loading Decisions' }, { id: 'issues', label: 'Receiving Issues' }],
  LOADER: [{ id: 'loading', label: 'Loading Bay' }],
  DRIVER: [{ id: 'driver', label: 'My Route' }],
}
export const roleNames: Record<UserRole, string> = { STORE: 'Store Manager', DISPATCHER: 'Dispatcher', LOADER: 'Loader', DRIVER: 'Driver' }

export function allowedPage(role: UserRole, page: WorkspacePage): WorkspacePage {
  return rolePages[role].some(item => item.id === page) ? page : rolePages[role][0].id
}
