import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('renders the sign-in form for a signed-out user', () => {
    const markup = renderToStaticMarkup(<App />)

    expect(markup).toContain('Waypoint Nexus')
    expect(markup).toContain('Sign in')
    expect(markup).toContain('name="email"')
    expect(markup).toContain('name="password"')
  })
})
