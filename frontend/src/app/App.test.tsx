import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('renders the development home screen', () => {
    const markup = renderToStaticMarkup(<App />)

    expect(markup).toContain('Waypoint Nexus')
    expect(markup).toContain('Delivery Orchestration Platform')
  })
})
