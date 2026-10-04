# Talky

Vue 3 / Vue Router frontend and Flask backend with email/password login,
email OTP verification, and database-backed authentication sessions. Existing
chat styling, usernames, message formats, encryption, uploads, and call UI are
retained. Login uses email; registration includes an email field; OTP verification
and Logout are the only new authentication UI.

## Local development

Use Node 22.12+ and Python 3.11+. Copy `.env.example` to `.env`, fill in SMTP
configuration, and generate SESSION_SECRET with:

```sh
python -c "import secrets; print(secrets.token_hex(32))"
```

For an existing installation, preserve its old SECRET_KEY (including the value
in `.secret_key`) as CHAT_KEY_SECRET so existing message encryption keys remain
usable. SESSION_SECRET and OTP_SECRET are backend-only secrets. Never put any
secret in a variable prefixed with VITE_.

Install dependencies:

```sh
npm install
python -m pip install -r requirements.txt
```

Run two terminals:

```sh
npm run dev
```

```sh
python app.py
```

`npm run dev:backend` is equivalent to `python app.py`. Flask reads `.env`.
Leave VITE_API_BASE_URL empty locally: Vite proxies API, media and WebSocket
requests to BACKEND_URL. Use the exact FRONTEND_URL origin in your browser;
localhost and 127.0.0.1 are different origins. SQLite and local uploads are
supported only in development. No OTP is printed or returned to the frontend.
SMTP is needed even locally; failed delivery returns a safe error.

Build the frontend:

```sh
npm run build
```

Output is `dist/index.html`, `dist/assets/`, and copies of the existing CSS and
images under `dist/static/assets/`. Flask-rendered template entries are no
longer used; the backend's page URLs redirect to the Vue application.

## Existing accounts and database migration

Back up the database before deployment. Startup keeps the users and messages
and adds nullable `users.email` with a unique index plus `auth_sessions`,
`auth_otp_challenges`, and `auth_rate_limits`. Existing usernames remain chat
identities; no email is invented for an old account. Attach an operator-verified
address before that account can use the new login:

```sh
python -m flask --app app link-email existing_username person@example.com
```

New passwords use Werkzeug scrypt. Legacy salted PBKDF2 password hashes still
verify and upgrade to scrypt after a successful password check. Existing blocked
accounts remain blocked. Copy existing SQLite data to PostgreSQL before switching
DATABASE_URL if you need to retain it; this change does not automatically export
or upload the local database.

## Authentication behavior

POST `/api/auth/login` accepts `{email, password}` and sends a backend-generated
6-digit OTP. Password authentication creates a pending session only. POST
`/api/auth/verify-otp` accepts `{code}`. OTPs expire after 300 seconds, allow five
attempts, are single-use, and are stored as keyed hashes. Resend replaces the
previous hash, resets the five-attempt budget, and requires an account-wide
60-second cooldown. POST `/api/auth/resend-otp` and POST `/api/auth/logout` accept
an empty JSON object. GET `/api/auth/me` checks authentication; GET
`/api/auth/csrf` supplies a CSRF token. POST `/api/auth/register` preserves signup
with `{username, email, password}`.

Sessions are opaque random HttpOnly cookies. Only a hash of the cookie and the
server-side session data are persisted, with an eight-hour absolute expiry.
Cookies rotate at password and OTP authentication; logout revokes the session.
Neither auth tokens nor OTPs are stored in localStorage. Database-backed rate
limits apply independently to IP and account: login 10/10 minutes, OTP requests
5/hour, verification requests 20/10 minutes, and registration 5/hour. Each OTP
also has its own stricter five-attempt maximum. Responses do not reveal whether
an email exists. Mutating requests require X-CSRF-Token and allowed origins.

Backend authorization independently protects all private routes, including
WebSocket handshakes, message history, keys, uploads and downloads. WebSocket
identity comes from the verified session, and session expiry/revocation is
checked during connections and before forwarding. Vue route guards help
navigation but do not grant backend access.

## Render deployment

`render.yaml` defines a Static Site and a Python Web Service. No deployment or
resource creation is performed by this repository change. Configure these:

| Setting | Frontend Static Site | Backend Web Service |
| --- | --- | --- |
| Root directory | repository root | repository root |
| Build command | `npm ci && npm run build` | `pip install -r requirements.txt` |
| Publish directory | `dist` | not applicable |
| Start command | none | `gunicorn --worker-class gevent --workers 1 --bind 0.0.0.0:$PORT app:app` |
| Health check | not applicable | `/health` |
| Instances | static hosting | one, as required by existing in-process chat connections |

`npm start` runs the same production Gunicorn command on Linux with PORT exported.
On Windows use `python app.py` for development; Gunicorn runs on Render's Linux
service. PORT is assigned by Render and the backend binds to 0.0.0.0.

Frontend build variable: VITE_API_BASE_URL must be the backend's public HTTPS
origin. Rebuild the Static Site when this variable changes. Add the Render
rewrite rule `/*` -> `/index.html` (type Rewrite) for route refreshes/direct
navigation; real static assets are served normally. The rule is included in the
Blueprint. Render's [rewrite documentation](https://render.com/docs/redirects-rewrites)
and [Flask deployment guide](https://render.com/docs/deploy-flask) describe the
hosting settings.

Backend required variables: NODE_ENV=production, DATABASE_URL, SESSION_SECRET,
FRONTEND_URL, BACKEND_URL, SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_USER and
SMTP_PASSWORD when your provider requires them, USE_SUPABASE=true, SUPABASE_URL,
and SUPABASE_KEY. Use a durable PostgreSQL service, with a standard postgres://
or postgresql:// connection URL. The database role needs schema migration
permissions on initial startup. Production refuses SQLite or local upload
storage. Configure a PRIVATE Supabase bucket (default `uploads`, overridden by
SUPABASE_BUCKET); authenticated download authorization issues a short-lived
signed URL, never a public bucket URL. The Supabase key stays on the backend.

Optional configuration: SECRET_KEY is a legacy alias for SESSION_SECRET;
OTP_SECRET defaults to SESSION_SECRET; CHAT_KEY_SECRET defaults to SESSION_SECRET
and must retain the old chat key for existing messages. SMTP_SSL=true uses TLS
from connect (usually port 465); otherwise SMTP_STARTTLS=true uses STARTTLS
(usually port 587). Production refuses unencrypted SMTP. See `.env.example`
for every setting and its development defaults.

Use sibling HTTPS custom domains, for example app.example.com and
api.example.com, for reliable cookie behavior across browsers. Set FRONTEND_URL,
BACKEND_URL and VITE_API_BASE_URL to those exact origins, and set
SESSION_COOKIE_SAMESITE=Lax. All production cookies use Secure, HttpOnly, Path=/,
and a __Host- name with no Domain attribute. If using unrelated service domains,
set SESSION_COOKIE_SAMESITE=None; cookies then depend on the browser allowing
third-party cookies. Do not treat a deployment on default unrelated domains as
verified until testing that policy in your target browsers. CORS allows only the
configured frontend/backend origins and includes credentials, never wildcard
origins. [Flask cookie security](https://flask.palletsprojects.com/en/stable/web-security/)
explains the cookie attributes; [MDN third-party cookie guidance](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies)
explains the browser restriction.

## Verification

```sh
python -m unittest discover -s tests -v
npm run build
```

The tests use isolated temporary databases and mocked SMTP transport; no test
writes to the existing application database. Coverage includes password and OTP
success/failure, expiry, attempt limits, resend, shared rate limits, cookie
rotation/expiry/revocation, replay, CSRF, CORS, protected routes, legacy account
email linking/password upgrade, successful private uploads, and WebSocket
identity. Browser verification covers protected direct navigation, password/OTP
forms, authenticated refresh, existing encrypted chat, and logout. Actual SMTP
delivery, PostgreSQL connectivity, Supabase storage and the final hosted HTTPS
configuration must also be checked after setting deployment credentials.
