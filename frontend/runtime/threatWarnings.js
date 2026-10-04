import { backendFetch } from '../services/auth.js'
import { explainLink, extractLinks } from './securitySignals.js'
import './threatWarnings.css'

// Additive DOM cards because the existing chat renderer is DOM-based.
// All untrusted content is assigned via textContent, never HTML.
export function attachThreatWarnings(container, text) {
  for (const link of extractLinks(text)) {
    let finding
    try { finding = explainLink(link) } catch { continue }
    const card = document.createElement('article')
    card.className = 'talky-safety-card ' + (finding.reasons.length ? 'danger' : 'unknown')
    const add = (tag, value, parent = card, className = '') => {
      const node = document.createElement(tag)
      node.textContent = value
      node.className = className
      parent.appendChild(node)
      return node
    }
    const top = add('div', '', card, 'safety-top')
    const icon = add('span', '', top, 'safety-icon')
    icon.setAttribute('aria-hidden', 'true')
    const shield = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    for (const [name, value] of Object.entries({ viewBox: '0 0 24 24', width: '20', height: '20', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })) shield.setAttribute(name, value)
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    path.setAttribute('d', 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm0-13v4m0 3h.01')
    shield.appendChild(path)
    icon.appendChild(shield)
    const title = add('div', '', top, 'safety-title')
    add('span', finding.reasons.length ? 'Link needs review' : 'Link not verified', title, 'risk-label')
    add('h3', finding.host, title)
    add('p', finding.reasons[0] || "We could not confirm this website’s reputation. Verify the sender before opening it.", card, 'risk-summary')
    const details = add('details', '', card, 'safety-disclosure')
    add('summary', 'Why am I seeing this?', details, 'details-toggle')
    const evidence = add('div', '', details, 'safety-details')
    add('small', `${finding.source} · ${new Date().toLocaleString()} · No reputation provider result available`, evidence)
    for (const reason of finding.reasons) add('p', '• ' + reason, evidence)
    if (!finding.reasons.length) add('p', 'No local warning found. This does not establish that the website is safe.', evidence)
    add('p', finding.safe_action, evidence)
    add('small', 'Community checks send only this hostname to Talky. Reports apply to all links on this exact hostname, not a specific page. No message, URL path, query, or fragment is submitted.', evidence)
    const status = add('p', 'Community reports have not been checked.', card, 'community-status')
    status.setAttribute('role', 'status')
    const actions = add('div', '', card, 'safety-actions')
    const reportPanel = add('div', '', card, 'report-panel')
    reportPanel.hidden = true
    const category = document.createElement('select')
    category.setAttribute('aria-label', 'Report category')
    for (const [value, label] of [['suspicious_link', 'Suspicious link'], ['possible_phishing', 'Possible phishing'], ['scam', 'Possible scam']]) {
      const option = document.createElement('option')
      option.value = value; option.textContent = label; category.appendChild(option)
    }
    reportPanel.appendChild(category)
    let reported = false, busy = false
    const buttons = []
    const request = async action => {
      if (busy) return
      busy = true
      buttons.forEach(button => { button.disabled = true })
      try {
        const response = await backendFetch(action
          ? '/api/threats/report'
          : '/api/threats/community?indicator=' + encodeURIComponent(finding.host), action ? {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ indicator: finding.host, action, category: category.value })
          } : {})
        const data = await response.json()
        if (!response.ok) throw new Error(data.error || 'Community reporting unavailable.')
        reported = data.reported_by_you
        status.textContent = `${data.report_count} community report${data.report_count === 1 ? '' : 's'} — unverified. Reports are not proof of maliciousness.`
        reportButton.textContent = reported ? 'Withdraw my report' : 'Submit report'
      } catch (error) {
        status.textContent = error.message || 'Community reporting unavailable. Chat is unaffected.'
      } finally {
        busy = false
        buttons.forEach(button => { button.disabled = false })
      }
    }
    const button = (label, action, parent = actions, className = '') => {
      const node = add('button', label, parent, className)
      node.type = 'button'
      node.addEventListener('click', action)
      buttons.push(node)
      return node
    }
    // The original message remains plain text; this explicit action opens only
    // an HTTP(S) URL after the user has had a chance to review the card.
    button('Open anyway', () => window.open(link, '_blank', 'noopener,noreferrer'), actions, 'open-link')
    button('↻ Check again', () => request(), actions, 'check-link')
    const toggle = button('⚑ Report', () => {
      reportPanel.hidden = !reportPanel.hidden
      toggle.setAttribute('aria-expanded', String(!reportPanel.hidden))
    }, actions, 'report-link')
    toggle.setAttribute('aria-expanded', 'false')
    const reportButton = button('Submit report', () => request(reported ? 'withdraw' : 'report'), reportPanel, 'check-link')
    container.appendChild(card)
  }
}
