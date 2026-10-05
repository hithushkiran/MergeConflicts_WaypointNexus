/* Real-browser acceptance against the isolated synthetic Compose stack.
 * Install playwright and axe-core in .t09-verification/browser-tools first.
 * Run after verify_golden_path.py --prepare-only using an unused eligible date.
 * Never records credentials or bearer tokens in evidence.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const tools = path.resolve('.t09-verification/browser-tools/node_modules')
const { chromium } = require(path.join(tools, 'playwright'))
const axe = path.join(tools, 'axe-core/axe.min.js')
const prepared = JSON.parse(fs.readFileSync(process.argv[2] || '.t09-verification/browser-prepared.json', 'utf8'))
const output = path.resolve('.t09-verification/browser')
fs.mkdirSync(output, { recursive: true })
const evidence = { checks: [], accessibility: [], responsive: [] }

async function login(page, role) {
  await page.getByLabel('Email', { exact: true }).fill(`${role}@waypoint.local`)
  await page.getByLabel('Password', { exact: true }).fill(process.env.DEV_SEED_PASSWORD || 'waypoint-local-demo')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.locator('.app-shell').waitFor()
  await page.waitForLoadState('networkidle')
}

async function audit(page, label, widths) {
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    const sizes = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }))
    evidence.responsive.push({ label, width, ...sizes })
    assert.ok(sizes.content <= sizes.viewport + 1, `${label}: page overflow at ${width}px`)
    await page.addScriptTag({ path: axe })
    const result = await page.evaluate(async () => {
      const results = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })
      return { violations: results.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => ({ target: n.target, summary: n.failureSummary })) })), incomplete: results.incomplete.map(v => v.id) }
    })
    evidence.accessibility.push({ label, width, ...result })
    await page.screenshot({ path: path.join(output, `${label}-${width}.png`), fullPage: true })
  }
}

async function outbox(page) {
  return page.evaluate(async () => {
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open('waypoint-driver-offline', 1)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    const rows = await new Promise((resolve, reject) => {
      const request = db.transaction('outbox').objectStore('outbox').getAll()
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    db.close()
    return rows
  })
}

async function main() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  try {
    const context = await browser.newContext()
    const page = await context.newPage()
    await page.goto('http://localhost:5174/')
    await audit(page, 'login', [360, 1440])
    for (const [role, widths] of [['store.manager', [360, 1440]], ['dispatcher', [360, 1440]], ['loader', [360, 768]]]) {
      await login(page, role)
      const failurePaths = {
        'store.manager': ['**/api/v1/store/orders', 'Refresh orders'],
        loader: ['**/api/v1/loader/trips', 'Refresh loading bay'],
        dispatcher: ['**/api/v1/dispatcher/shortfalls', 'Refresh exceptions'],
      }
      const [failurePath, refreshName] = failurePaths[role]
      await page.route(failurePath, route => route.abort('failed'))
      await page.reload()
      await page.getByRole('alert').first().waitFor()
      await page.unroute(failurePath)
      await page.getByRole('button', { name: refreshName, exact: true }).click()
      await page.waitForLoadState('networkidle')
      assert.equal(await page.getByRole('alert').count(), 0)
      evidence.checks.push(`${role}: injected network read failure surfaced and recovered via refresh`)
      await page.keyboard.press('Tab')
      await page.getByRole('link', { name: 'Skip to workspace' }).focus()
      await page.keyboard.press('Enter')
      assert.equal(await page.evaluate(() => document.activeElement.id), 'workspace-content')
      await audit(page, role, widths)
      await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    }
    await login(page, 'driver')
    await page.getByRole('button', { name: 'Arrived', exact: true }).first().waitFor()
    await audit(page, 'driver', [360, 768])
    if (process.argv.includes('--audit-only')) {
      assert.equal(evidence.accessibility.flatMap(item => item.violations).length, 0, 'Accessibility violations; inspect browser/results.json')
      evidence.result = 'AUDIT_PASSED'
      return
    }
    await page.evaluate(async () => { await navigator.serviceWorker.ready })
    await page.reload()
    await page.getByRole('button', { name: 'Arrived', exact: true }).first().waitFor()
    const token = await page.evaluate(() => sessionStorage.getItem('waypoint.access-token'))
    await context.setOffline(true)
    await page.reload()
    await page.getByRole('button', { name: 'Arrived', exact: true }).first().waitFor()
    for (let index = 0; index < 2; index++) {
      await page.getByRole('button', { name: 'Arrived', exact: true }).first().click()
      await page.getByLabel('Receiver name', { exact: true }).fill('Browser receiving team')
      await page.getByLabel('Delivery notes or failure reason').fill('Recorded offline in acceptance')
      await page.reload()
      assert.equal(await page.getByLabel('Receiver name', { exact: true }).inputValue(), 'Browser receiving team')
      await page.getByRole('button', { name: 'Delivered', exact: true }).click()
    }
    await page.reload()
    const saved = await outbox(page)
    assert.equal(saved.length, 4)
    assert.ok(saved.every(row => row.state === 'PENDING'))
    evidence.checks.push('Disconnected shell reload, receiver draft reload and four queued commands persisted')
    // Revoke through the existing API: exercises the same INVALID_TOKEN path as expiry,
    // without editing the acceptance database or adding a test-only auth endpoint.
    const revoked = await fetch('http://localhost:8001/api/v1/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    assert.equal(revoked.status, 204)
    await context.setOffline(false)
    await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor()
    assert.match(await page.getByRole('alert').innerText(), /session expired/i)
    const paused = await outbox(page)
    assert.equal(paused.length, 4)
    assert.ok(paused.every(row => row.state !== 'CONFLICT'))
    assert.deepEqual(paused.map(row => [row.id, row.idempotency_key, row.command]), saved.map(row => [row.id, row.idempotency_key, row.command]))
    await login(page, 'driver')
    await page.waitForFunction(() => document.body.textContent.includes('0 updates waiting'))
    assert.deepEqual(await outbox(page), [])
    evidence.checks.push('Revoked/expired-token response preserved commands; same-driver login drained queue')
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await login(page, 'store.manager')
    for (let index = 0; index < prepared.order_refs.length; index++) {
      const select = page.getByLabel('Delivered order')
      const option = await select.locator('option').filter({ hasText: prepared.order_refs[index] }).getAttribute('value')
      await select.selectOption(option)
      await page.getByLabel('Receiver name', { exact: true }).fill('Store receiving team')
      if (index === 0) {
        await page.getByRole('checkbox').check()
        await page.getByRole('button', { name: 'Confirm Receipt', exact: true }).click()
        await page.getByRole('heading', { name: 'Receipt Confirmed' }).waitFor()
      } else {
        await page.getByRole('button', { name: 'Report an Issue', exact: true }).click()
        await page.getByLabel('Issue details').fill('Two chilled units missing; approved loading shortage')
        await audit(page, 'receipt-form', [360, 1440])
        await page.getByRole('button', { name: 'Submit Issue', exact: true }).click()
        await page.getByRole('heading', { name: 'Delivery Issue Submitted' }).waitFor()
      }
    }
    await audit(page, 'receipt-result', [360, 1440])
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await login(page, 'dispatcher')
    const issue = page.locator('section[aria-labelledby="delivery-issues-heading"] article').filter({ hasText: prepared.order_refs[1] })
    await issue.getByLabel('Review reason').fill('Verify approved loading shortage against recorded receiving')
    await issue.getByRole('button', { name: 'Start review' }).click()
    await issue.getByLabel('Resolution reason').fill('Accept recorded partial intake; no replacement implied')
    await issue.getByRole('button', { name: 'Resolve recorded outcome' }).click()
    await issue.getByText('Resolved:', { exact: false }).waitFor()
    evidence.checks.push('Store confirmed ambient receipt, reported chilled discrepancy; dispatcher reviewed and resolved')
    // Verify final persisted results and duplicate replay without another POD.
    const driverLogin = await fetch('http://localhost:8001/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'driver@waypoint.local', password: process.env.DEV_SEED_PASSWORD || 'waypoint-local-demo' }) }).then(r => r.json())
    for (const entry of saved) {
      const item = entry.command
      const replay = await fetch(`http://localhost:8001/api/v1/driver/stops/${item.stop_id}/${item.kind === 'ARRIVE' ? 'arrive' : 'complete'}`, { method: 'POST', headers: { Authorization: `Bearer ${driverLogin.access_token}`, 'Content-Type': 'application/json', 'Idempotency-Key': entry.idempotency_key, 'X-Command-Id': entry.id }, body: JSON.stringify(item.kind === 'ARRIVE' ? { occurred_at: item.occurred_at } : { outcome: item.outcome, receiver_name: item.receiver_name, notes: item.notes, occurred_at: item.occurred_at }) })
      assert.equal(replay.status, 200)
      assert.equal((await replay.json()).replayed, true)
    }
    evidence.checks.push('Original driver command IDs replayed successfully after receiving and case review')
    const violations = evidence.accessibility.flatMap(item => item.violations)
    assert.equal(violations.length, 0, `Accessibility violations: ${JSON.stringify(violations)}`)
    evidence.result = 'PASSED'
  } finally {
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(evidence, null, 2))
    await browser.close()
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1 })
