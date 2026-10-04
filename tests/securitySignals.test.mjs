import test from 'node:test'
import assert from 'node:assert/strict'
import { explainLink, extractLinks, similarContact, usernameDifference } from '../frontend/runtime/securitySignals.js'

test('lookalikes are warnings, genuine trusted subdomains are not', () => {
  assert.ok(explainLink('https://ucmo-scholarship.example/login').reasons.length)
  assert.ok(explainLink('https://ucmo.edu.attacker.example').reasons.length)
  assert.ok(explainLink('https://ucm0.edu').reasons.length)
  assert.equal(explainLink('https://portal.ucmo.edu').reasons.length, 0)
  assert.equal(explainLink('https://unrelated.example').risk_level, 'unknown')
})
test('real destination, credentials, HTTP and internationalized host are handled', () => {
  const result = explainLink('http://ucmo.edu@attacker.example/path?token=private')
  assert.equal(result.host, 'attacker.example')
  assert.equal(result.reasons.length, 2)
  assert.ok(explainLink('https://xn--pple-43d.example').reasons.length)
  assert.throws(() => explainLink('javascript:alert(1)'))
})
test('extraction is bounded and deduplicated', () => {
  assert.deepEqual(extractLinks('https://example.com. https://example.com.'), ['https://example.com'])
  assert.equal(extractLinks(Array.from({ length: 8 }, (_, i) => `https://${i}.example`).join(' ')).length, 5)
})
test('contact similarity checks distinct identities without flagging unrelated names', () => {
  const friends = [{ id: 1, username: 'john_smith' }, { id: 2, username: 'admin01' }]
  assert.equal(similarContact({ id: 3, username: 'john_srnith' }, friends).id, 1)
  assert.equal(similarContact({ id: 3, username: 'adm1n01' }, friends).id, 2)
  assert.equal(similarContact({ id: 1, username: 'john_smith' }, friends), null)
  assert.equal(similarContact({ id: 3, username: 'sarah_jones' }, friends), null)
  assert.deepEqual(usernameDifference('john_srnith', 'john_smith'), ['john_s', 'rn', 'ith'])
})
