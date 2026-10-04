import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { UserProfile } from '../lib/api'
import { roleNames, rolePages, type WorkspacePage } from '../lib/navigation'

export default function AppShell({ user, page, onNavigate, onSignOut, children }: { user: UserProfile; page: WorkspacePage; onNavigate: (page: WorkspacePage) => void; onSignOut: () => void; children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const main = useRef<HTMLElement>(null)
  const previousPage = useRef(page)
  const entries = rolePages[user.role]
  const title = entries.find(item => item.id === page)?.label ?? entries[0].label
  const scope = user.outlet_id ? `Outlet ${user.outlet_id}` : user.depot_code ? `Depot ${user.depot_code}` : 'All operations'
  useEffect(() => {
    if (previousPage.current !== page) { main.current?.focus(); previousPage.current = page }
  }, [page])
  return <div className={`wp-shell ${user.role === 'DRIVER' ? 'wp-driver-shell' : ''}`}>
    <a className="wp-skip" href="#workspace">Skip to workspace</a>
    <aside className={`wp-sidebar ${menuOpen ? 'wp-menu-open' : ''}`}>
      <div className="wp-brand"><span className="wp-emblem"><img src="/figma-assets/logo.svg" alt="" /></span><div><strong>WAYPOINT</strong><small>DELIVERY OPERATIONS</small></div></div>
      <nav aria-label={`${roleNames[user.role]} navigation`}>{entries.map(item => <button key={item.id} aria-current={page === item.id ? 'page' : undefined} onClick={() => { onNavigate(item.id); setMenuOpen(false) }}>
        {item.icon && <img src={`/figma-assets/${item.icon}.svg`} alt="" />}{item.label}
      </button>)}</nav>
      <div className="wp-sidebar-account"><span className="wp-avatar"><img src="/figma-assets/account.svg" alt="" /></span><div><strong>{roleNames[user.role]}</strong><small>{scope}</small></div></div>
    </aside>
    <div className="wp-workspace"><header className="wp-topbar">
      <button className="wp-menu-toggle" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} onClick={() => setMenuOpen(value => !value)}>Menu</button>
      <p className="wp-breadcrumb">{user.role === 'STORE' ? 'Store Operations' : 'Operations'} <span>/</span> <strong>{title}</strong></p>
      <div className="wp-header-context"><time>{new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Colombo' }).format(new Date())}</time><span>{roleNames[user.role]}</span><code>{user.outlet_id ?? user.depot_code ?? 'Central'}</code><button onClick={onSignOut}>Sign out</button></div>
    </header><main id="workspace" ref={main} tabIndex={-1} className="wp-content" aria-label={title}>{children}</main></div>
  </div>
}
