// Narrow, explainable heuristics; these do not establish identity or safety.
export function usernameSkeleton(value) {
  return String(value).normalize('NFKC').toLowerCase().replace(/[_\-\s]/g, '')
    .replace(/rn/g, 'm').replace(/[1іı]/g, 'i').replace(/[0οо]/g, 'o')
    .replace(/а/g, 'a').replace(/е/g, 'e').replace(/с/g, 'c').replace(/р/g, 'p')
}

function distance(a, b) {
  let row = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 0; i < a.length; i++) {
    const next = [i + 1]
    for (let j = 0; j < b.length; j++) next.push(Math.min(next[j] + 1, row[j + 1] + 1, row[j] + (a[i] === b[j] ? 0 : 1)))
    row = next
  }
  return row[b.length]
}

export function similarContact(user, friends) {
  const candidate = usernameSkeleton(user.username).slice(0, 100)
  return friends.find(friend => {
    if (friend.id === user.id) return false
    const known = usernameSkeleton(friend.username).slice(0, 100)
    return candidate === known || (Math.min(candidate.length, known.length) >= 6 && distance(candidate, known) <= 1)
  }) || null
}

export function usernameDifference(value, other) {
  const a = Array.from(value), b = Array.from(other)
  let start = 0, end = 0
  while (start < Math.min(a.length, b.length) && a[start] === b[start]) start++
  while (end < Math.min(a.length, b.length) - start && a[a.length - end - 1] === b[b.length - end - 1]) end++
  return [a.slice(0, start).join(''), a.slice(start, a.length - end).join(''), end ? a.slice(-end).join('') : '']
}

export function extractLinks(text) {
  return [...new Set((String(text).match(/https?:\/\/[^\s<>"']+/gi) || [])
    .map(link => link.replace(/[.,!?;:)\]}]+$/, '')))].slice(0, 5)
}

export function explainLink(link, trustedDomains = ['ucmo.edu']) {
  const url = new URL(link)
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Unsupported link')
  const host = url.hostname.toLowerCase().replace(/\.$/, '')
  const reasons = []
  if (url.username || url.password) reasons.push('The URL contains user information before the real destination; this can disguise the hostname.')
  if (url.protocol === 'http:') reasons.push('This link uses HTTP rather than HTTPS; transport encryption is not provided by this URL.')
  if (host.includes('xn--')) reasons.push('The hostname uses an internationalized encoding. Check its displayed characters carefully; this alone does not imply a threat.')
  for (const trusted of trustedDomains) {
    if (host === trusted || host.endsWith('.' + trusted)) continue
    const brand = trusted.split('.')[0]
    const labels = host.split('.')
    if (host.includes(trusted + '.') || labels.some(label => label.includes(brand) || (label.length >= 4 && distance(label, brand) <= 1))) {
      reasons.push(`The hostname resembles or includes ${trusted}, but is not that domain or one of its subdomains.`)
    }
  }
  return { host, reasons, risk_level: reasons.length ? 'attention' : 'unknown',
    source: 'Local URL checks', safe_action: 'Verify the sender and website through a known channel before entering credentials.' }
}
