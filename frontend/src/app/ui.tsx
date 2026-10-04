import type { ButtonHTMLAttributes, ReactNode } from 'react'

export function Button({ variant = 'primary', className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' }) {
  return <button type="button" className={`wp-button wp-button-${variant} ${className}`} {...props} />
}

export function Panel({ title, children, className = '' }: { title?: string; children: ReactNode; className?: string }) {
  return <section className={`wp-panel ${className}`}>{title && <h2 className="wp-panel-title">{title}</h2>}{children}</section>
}

export function PageHeading({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return <div className="wp-page-heading"><div><h1 tabIndex={-1}>{title}</h1><p>{description}</p></div>{actions && <div className="wp-actions">{actions}</div>}</div>
}

export function StatusBadge({ status }: { status: string }) {
  const tone = ['CONFIRMED', 'RECEIVED', 'RESOLVED', 'READY', 'LOADED', 'COMPLETED', 'DELIVERED', 'CONNECTED'].includes(status) ? 'success' : ['DEFERRED', 'PARTIAL', 'DISPUTED', 'DISPATCH_HOLD', 'OPEN', 'PENDING_SYNC', 'OFFLINE', 'CONFLICT', 'FAILED'].includes(status) ? 'warning' : 'info'
  return <span className={`wp-badge wp-badge-${tone}`}>{status.replace(/_/g, ' ')}</span>
}

export function Alert({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'error' | 'success' | 'warning' }) {
  return <div className={`wp-alert wp-alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>{children}</div>
}

export function Facts({ values }: { values: Record<string, ReactNode> }) {
  return <dl className="wp-facts">{Object.entries(values).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}
