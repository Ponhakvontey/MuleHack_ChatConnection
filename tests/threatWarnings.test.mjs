import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { explainLink, extractLinks } from '../frontend/runtime/securitySignals.js'

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.textContent = '' }
  appendChild(child) {
    this.children.push(child)
    if (this.tag === 'select' && this.children.length === 1) this.value = child.value
  }
  setAttribute(name, value) { this[name] = value }
  addEventListener(name, callback) { this.listeners[name] = callback }
  click() { return this.listeners.click() }
}

function renderer(fetch) {
  // Inject the transport and DOM boundary; exercise the actual card renderer.
  const source = readFileSync(new URL('../frontend/runtime/threatWarnings.js', import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '').replace('export function', 'function')
  return new Function('backendFetch', 'explainLink', 'extractLinks', 'document', source + '\nreturn attachThreatWarnings')(
    fetch, explainLink, extractLinks, { createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag) })
}

function descendants(node) {
  return node.children.flatMap(child => [child, ...descendants(child)])
}

test('card sends only hostname after explicit action and renders unverified counts', async () => {
  const requests = []
  const attach = renderer(async (path, options) => {
    requests.push({ path, options })
    return { ok: true, json: async () => ({ report_count: 1, reported_by_you: true }) }
  })
  const container = new Element('div')
  attach(container, 'https://ucmo-scholarship.example/private?token=secret#fragment')
  assert.equal(requests.length, 0)
  const card = container.children[0]
  assert.equal(card.tag, 'article')
  assert.equal(card.className, 'talky-safety-card danger')
  const nodes = descendants(card)
  const buttons = nodes.filter(node => node.tag === 'button')
  const panel = nodes.find(node => node.className === 'report-panel')
  assert.equal(panel.hidden, true)
  buttons[2].click()
  assert.equal(panel.hidden, false)
  assert.equal(buttons[2]['aria-expanded'], 'true')
  await buttons[3].click()
  const body = JSON.parse(requests[0].options.body)
  assert.deepEqual(body, { indicator: 'ucmo-scholarship.example', action: 'report', category: 'suspicious_link' })
  assert.ok(nodes.some(node => node.textContent.includes('1 community report — unverified')))
  assert.equal(buttons[3].textContent, 'Withdraw my report')
  await buttons[3].click()
  assert.equal(JSON.parse(requests[1].options.body).action, 'withdraw')
  assert.ok(buttons.every(node => !node.disabled))
})

test('report failures do not throw or remove the local explanation', async () => {
  const container = new Element('div')
  renderer(async () => { throw new Error('Service unavailable') })(container, 'http://unrelated.example')
  const card = container.children[0]
  const nodes = descendants(card)
  const check = nodes.find(node => node.className === 'check-link')
  await check.click()
  assert.ok(nodes.some(node => node.textContent === 'Service unavailable'))
  assert.ok(nodes.some(node => node.textContent.includes('HTTP rather than HTTPS')))
  assert.equal(check.disabled, false)
})
