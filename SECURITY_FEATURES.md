# Scoped cybersecurity additions

Only three existing source files changed: `app.py` registers the new report
module before the existing schema initialization; `PeoplePanel.vue` adds
contact-similarity warnings; `frontend/runtime/chat.js` attaches security cards
after text rendering. No existing message payload, encryption, authentication,
call, profile, recommendation, or friendship action was changed. No dependency,
global style, or dashboard changes were made.

## New files

- `modules/community_threats.py`: validated, authenticated domain reports.
- `frontend/runtime/securitySignals.js`: local link and username checks.
- `frontend/runtime/threatWarnings.js`: additive expandable cards and report actions.
- Three focused test files covering signals, cards, and report APIs.

## Database and APIs

The existing SQLAlchemy `create_all()` creates one additive `threat_reports`
table at startup. Its composite primary key is `(reporter_user_id, indicator)`;
other fields are category and creation time. Existing tables and data are not
rewritten. SQLite was tested; PostgreSQL was not integration-tested.

- `GET /api/threats/community?indicator=example.com`: aggregate distinct-user
  count, exact hostname, unverified status, and whether the requester reported it.
- `POST /api/threats/report`: hostname, category, and report/withdraw action.

Both routes use the existing verified-session boundary. POST uses existing
CSRF and origin enforcement. Reads are limited to 120/minute and report actions
to 20/hour per IP and account. Duplicate submissions do not inflate counts.
The authenticated session supplies the reporter ID; client-supplied IDs are ignored.

## Scope and limitations

No active reputation scanner or threat-warning component was found in this
checkout. Cards therefore explain local URL findings: HTTP, URL user information,
internationalized hostname encoding, and resemblance to the explicitly configured
trusted domain `ucmo.edu`. They do not invent provider results, domain ages, or
numerical risk scores. Unflagged links have unknown safety. Checks use actual
hostnames and exact/subdomain boundaries; no public-suffix or registrable-domain
classification is claimed. No destination is fetched and no external service is added.

Username checks compare only the viewer's existing friends, exclude the same
stable account ID, normalize separators and selected lookalike characters, and
allow one edit for names of at least six characters. Differences are highlighted.
These limited heuristics can have false positives/negatives; they never block or
claim verified impersonation. The original friend actions remain intact.

Community matching is exact-hostname/domain-level, not exact-URL-level. Reports
about one page may affect context for other pages on that hostname. The UI explains
this limitation. Only explicit check/report actions send a hostname to Talky;
no message text, URL path/query/fragment, reporter name, sender, or conversation ID
is submitted or returned. Reporter IDs remain internal for deduplication. Counts
can still reveal activity in small communities, and coordinated reports remain
possible. Counts are not proof and trigger no enforcement.

Counts refresh on user action, not via WebSocket broadcasts. No reports are
automatically posted. Report failure does not block message rendering.

## Verification and demo

Run `python -m unittest discover -s tests -v`,
`node --test tests/securitySignals.test.mjs tests/threatWarnings.test.mjs tests/calls.test.mjs`,
and `npm run build`.

Backend coverage includes registration/authentication, OTP, sessions, account
editing, friends, blocks, message forwarding, private attachments, call signaling,
and the new report validation/deduplication/withdrawal/rate-limit/privacy tests.
Node tests cover existing audio/video call behavior plus local signals and card
request/failure behavior. Live browser, SMTP/provider, PostgreSQL, and actual
microphone/camera/network calls are not verified by these automated tests.

Demo using existing accounts or disposable data:

1. With `john_smith` in your friends, search for a different account named
   `john_srnith`. Expand the warning to see the differing characters.
2. In an authorized chat, send `https://ucmo-scholarship.example/login`.
   Expand its local explanation. `.example` is a harmless reserved test domain.
3. Report its hostname as possible phishing. Another signed-in user receiving
   the same hostname can expand the card and click check/refresh to see the
   unverified aggregate. Repeated reports by one account keep the count unchanged.
4. Withdraw the report and refresh the other user's count.
