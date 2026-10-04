"""Database-backed sessions, single-use OTPs and shared rate limits."""
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from functools import wraps
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import click
from flask import Blueprint, current_app, g, jsonify, request, session, redirect
from flask.sessions import SessionInterface, SessionMixin
from sqlalchemy import inspect, text, update, delete
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from modules.extensions import db

auth = Blueprint('auth', __name__, url_prefix='/api/auth')
GENERIC_ERROR = 'Unable to authenticate. Check your details and try again.'
OTP_ERROR = 'Invalid or expired verification code.'


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text, unique=True, nullable=False)
    email = db.Column(db.Text, unique=True)
    password = db.Column(db.Text, nullable=False)
    failed_attempts = db.Column(db.Integer, default=0)
    is_blocked = db.Column(db.Integer, default=0)


class ServerSession(db.Model):
    __tablename__ = 'auth_sessions'
    token_hash = db.Column(db.String(64), primary_key=True)
    data = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False, index=True)


class OtpChallenge(db.Model):
    __tablename__ = 'auth_otp_challenges'
    id = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    last_sent_at = db.Column(db.BigInteger, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    used_at = db.Column(db.BigInteger)


class RateLimit(db.Model):
    __tablename__ = 'auth_rate_limits'
    key = db.Column(db.String(64), primary_key=True)
    hits = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False, index=True)


def now():
    return int(time.time())


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class DatabaseSession(dict, SessionMixin):
    def __init__(self, values=None, token=None):
        super().__init__(values or {})
        self.token = token or secrets.token_urlsafe(32)
        self.invalidated = False
        self.loaded = token is not None


class DatabaseSessionInterface(SessionInterface):
    def open_session(self, app, req):
        token = req.cookies.get(app.config['SESSION_COOKIE_NAME'])
        if token and len(token) <= 128:
            row = db.session.get(ServerSession, token_hash(token))
            if row and row.expires_at > now():
                return DatabaseSession(json.loads(row.data), token)
        return DatabaseSession()

    def save_session(self, app, value, response):
        response.vary.add('Cookie')
        if value.invalidated:
            response.delete_cookie(app.config['SESSION_COOKIE_NAME'], path='/',
                                   secure=app.config['SESSION_COOKIE_SECURE'],
                                   httponly=True, samesite=app.config['SESSION_COOKIE_SAMESITE'])
            return
        # Persisted explicitly by auth endpoints. Ordinary requests cannot extend
        # expiry or resurrect a session concurrently revoked by logout.
        if getattr(value, 'issue_cookie', False):
            response.set_cookie(app.config['SESSION_COOKIE_NAME'], value.token,
                max_age=app.config['SESSION_TTL_SECONDS'], path='/', httponly=True,
                secure=app.config['SESSION_COOKIE_SECURE'],
                samesite=app.config['SESSION_COOKIE_SAMESITE'])


def persist_session():
    expiry = now() + (current_app.config['SESSION_TTL_SECONDS'] if session.get('user') else 900)
    db.session.merge(ServerSession(token_hash=token_hash(session.token),
                                  data=json.dumps(dict(session)), expires_at=expiry))
    db.session.commit()
    session.issue_cookie = True


def rotate_session(values):
    db.session.execute(delete(ServerSession).where(ServerSession.token_hash == token_hash(session.token)))
    session.clear()
    session.update(values)
    session.token = secrets.token_urlsafe(32)
    persist_session()


def csrf_token():
    if not session.get('csrf'):
        session['csrf'] = secrets.token_urlsafe(32)
        persist_session()
    return session['csrf']


def is_authenticated():
    return bool(session.get('user') and session.get('user_id'))


def verified_session_record(session_hash):
    row = db.session.get(ServerSession, session_hash)
    if not row or row.expires_at <= now():
        return None
    values = json.loads(row.data)
    user = db.session.get(User, values.get('user_id')) if values.get('user_id') else None
    return row if user and not user.is_blocked and values.get('user') == user.username else None


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            return jsonify(error='Authentication required'), 401
        return view(*args, **kwargs)
    return wrapped


def consume_limit(action, identifier, maximum, window):
    timestamp = now()
    bucket = timestamp // window
    key = hmac.new(current_app.secret_key.encode(),
        f'{action}:{identifier}:{bucket}'.encode(), hashlib.sha256).hexdigest()
    result = db.session.execute(text('''INSERT INTO auth_rate_limits (key, hits, expires_at)
        VALUES (:key, 1, :expires) ON CONFLICT (key) DO UPDATE
        SET hits = auth_rate_limits.hits + 1 RETURNING hits'''),
        {'key': key, 'expires': (bucket + 1) * window}).scalar_one()
    db.session.execute(delete(RateLimit).where(RateLimit.expires_at <= timestamp))
    db.session.execute(delete(ServerSession).where(ServerSession.expires_at <= timestamp))
    db.session.execute(delete(OtpChallenge).where(OtpChallenge.expires_at < timestamp - 86400))
    db.session.commit()
    if result > maximum:
        response = jsonify(error='Too many attempts. Please try again later.')
        response.status_code = 429
        response.headers['Retry-After'] = str((bucket + 1) * window - timestamp)
        return response


def rate_limit(action, account='', maximum=10, window=600):
    if not current_app.config['PRODUCTION'] and not current_app.testing:
        window = min(window, 60)
    # IP and account buckets are independent, so rotating either alone cannot
    # evade the other. Only trust the proxy configured by the deployment.
    blocked = consume_limit(action + ':ip', request.remote_addr or 'unknown', maximum, window)
    if blocked:
        return blocked
    if account:
        return consume_limit(action + ':account', account, maximum, window)


def normalize_email(value):
    return value.strip().lower() if isinstance(value, str) else ''


def valid_email(value):
    return len(value) <= 254 and bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value))


def verify_password(stored, provided):
    if not isinstance(provided, str) or len(provided) > 1024:
        return False
    if stored.startswith(('scrypt:', 'pbkdf2:')):
        return check_password_hash(stored, provided)
    # Preserve existing accounts and upgrade their legacy PBKDF2 hashes on login.
    try:
        salt, digest = stored.split(':', 1)
        actual = hashlib.pbkdf2_hmac('sha256', provided.encode(), bytes.fromhex(salt), 200000)
        return hmac.compare_digest(actual.hex(), digest)
    except (ValueError, TypeError):
        return False


def otp_hash(challenge_id, code):
    return hmac.new(current_app.config['OTP_SECRET'].encode(),
                    (challenge_id + ':' + code).encode(), hashlib.sha256).hexdigest()


def send_otp(email, code):
    # Test injection is server-side only; never return or log OTPs.
    sender = current_app.config.get('OTP_SENDER')
    if sender:
        sender(email, code)
        return
    body = (f'Your Talky verification code is {code}. It expires in 5 minutes. '
            'If you did not request this code, ignore this email.')
    provider = os.getenv('EMAIL_PROVIDER', 'smtp').strip().lower()
    if provider == 'brevo':
        api_key = os.getenv('BREVO_API_KEY')
        from_address = os.getenv('EMAIL_FROM')
        if not api_key or not from_address:
            raise RuntimeError('Brevo email configuration is missing')
        payload = json.dumps({'sender': {'name': 'Talky', 'email': from_address},
                              'to': [{'email': email}],
                              'subject': 'Your Talky verification code', 'textContent': body}).encode('utf-8')
        outgoing = Request('https://api.brevo.com/v3/smtp/email', data=payload, method='POST',
                           headers={'api-key': api_key,
                                    'Content-Type': 'application/json', 'User-Agent': 'Talky/1.0'})
        try:
            with urlopen(outgoing, timeout=15, context=ssl.create_default_context()) as response:
                if response.status != 201:
                    raise RuntimeError('Email provider rejected delivery')
                result = json.loads(response.read())
                if not isinstance(result, dict) or not result.get('messageId'):
                    raise RuntimeError('Email provider did not acknowledge delivery')
        except (HTTPError, URLError, TimeoutError, ValueError):
            # Do not include provider response bodies, recipient, code or credentials.
            raise RuntimeError('HTTPS email delivery failed') from None
        return
    if provider != 'smtp':
        raise RuntimeError('Unsupported EMAIL_PROVIDER')
    message = EmailMessage()
    message['Subject'] = 'Your Talky verification code'
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = email
    message.set_content(body)
    use_ssl = os.getenv('SMTP_SSL', 'false').lower() == 'true'
    transport = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    tls_context = ssl.create_default_context()
    connection_options = {'timeout': 15}
    if use_ssl:
        connection_options['context'] = tls_context
    with transport(os.environ['SMTP_HOST'], int(os.getenv('SMTP_PORT', '587')), **connection_options) as smtp:
        if not use_ssl and os.getenv('SMTP_STARTTLS', 'true').lower() == 'true':
            smtp.starttls(context=tls_context)
        if os.getenv('SMTP_USER'):
            smtp.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
        smtp.send_message(message)


def challenge_status():
    row = db.session.get(OtpChallenge, session.get('challenge_id')) if session.get('challenge_id') else None
    if not row or row.used_at is not None:
        return None
    return {'expires_in': max(0, row.expires_at - now()),
            'resend_in': max(0, row.last_sent_at + 60 - now())}


@auth.get('/csrf')
def csrf():
    return jsonify(csrf_token=csrf_token())


@auth.get('/me')
def me():
    if not is_authenticated():
        return jsonify(authenticated=False, challenge=challenge_status()), 401
    user = db.session.get(User, session['user_id'])
    if not user or user.is_blocked:
        return jsonify(authenticated=False), 401
    return jsonify(authenticated=True, user={'username': user.username, 'email': user.email})


@auth.post('/register')
def register():
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    email = normalize_email(data.get('email'))
    # Short registration window for local testing; retain production protection.
    window = 3600 if current_app.config['PRODUCTION'] else 60
    limited = rate_limit('register', email, 5, window)
    if limited:
        return limited
    username = data.get('username', '')
    password = data.get('password', '')
    if not isinstance(username, str) or not re.fullmatch(r'[\w.-]{1,50}', username) or not valid_email(email):
        return jsonify(error='Please enter a username and valid email address.'), 400
    if not isinstance(password, str) or not 6 <= len(password) <= 1024 or (password.isdigit() and len(set(password)) == 1):
        return jsonify(error='Please enter a valid password of at least 6 characters.'), 400
    try:
        from modules.account_editing import PreviousUsername
        if db.session.get(PreviousUsername, username):
            return jsonify(message='You can now try signing in with your email and password.'), 200
        db.session.add(User(username=username, email=email, password=generate_password_hash(password)))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Same response as success; do not disclose account existence.
    return jsonify(message='You can now try signing in with your email and password.'), 200


@auth.post('/login')
def login():
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    email = normalize_email(data.get('email'))
    password = data.get('password', '')
    limited = rate_limit('login', email, 10, 600)
    if limited:
        return limited
    user = User.query.filter_by(email=email).first() if valid_email(email) else None
    # Perform the same expensive password check even for an unknown email.
    candidate = user.password if user else current_app.config['DUMMY_PASSWORD_HASH']
    matched = verify_password(candidate, password)
    if not user or user.is_blocked or not matched:
        return jsonify(error=GENERIC_ERROR), 401
    limited = rate_limit('otp-send', str(user.id), 5, 3600)
    if limited:
        return limited
    # Cooldown is account-wide, including repeated password authentication.
    timestamp = now()
    # A row lock serializes logins/resends for the same account on PostgreSQL.
    user = db.session.execute(db.select(User).where(User.id == user.id).with_for_update()).scalar_one()
    recent = OtpChallenge.query.filter_by(user_id=user.id).filter(OtpChallenge.last_sent_at > timestamp - 60).first()
    if recent:
        db.session.rollback()
        return jsonify(error='Please wait before requesting another code.'), 429, {'Retry-After': '60'}
    db.session.execute(delete(OtpChallenge).where(OtpChallenge.user_id == user.id))
    challenge_id = secrets.token_urlsafe(32)
    code = f'{secrets.randbelow(1000000):06d}'
    row = OtpChallenge(id=challenge_id, user_id=user.id, code_hash=otp_hash(challenge_id, code),
                       expires_at=timestamp + 300, last_sent_at=timestamp, attempts=0)
    db.session.add(row)
    if not user.password.startswith('scrypt:'):
        user.password = generate_password_hash(password)
    db.session.commit()
    try:
        send_otp(user.email, code)
    except Exception:
        current_app.logger.error('OTP email delivery failed')
        db.session.execute(delete(OtpChallenge).where(OtpChallenge.id == challenge_id))
        db.session.commit()
        return jsonify(error='Unable to send a verification email. Please try again later.'), 503
    rotate_session({'challenge_id': challenge_id, 'csrf': secrets.token_urlsafe(32)})
    return jsonify(otp_required=True, expires_in=300, resend_in=60, csrf_token=session['csrf'])


@auth.post('/verify-otp')
def verify_otp():
    challenge_id = session.get('challenge_id')
    limited = rate_limit('otp-verify', challenge_id or '', 20, 600)
    if limited:
        return limited
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    code = data.get('code', '')
    if not isinstance(code, str):
        code = ''
    # The atomic UPDATE enforces attempt/expiry/single-use limits under concurrent
    # requests. The subsequent consume operation is in the same transaction.
    row = db.session.execute(update(OtpChallenge).where(
        OtpChallenge.id == challenge_id, OtpChallenge.used_at.is_(None),
        OtpChallenge.expires_at > now(), OtpChallenge.attempts < 5
    ).values(attempts=OtpChallenge.attempts + 1).returning(OtpChallenge)).scalar_one_or_none()
    valid = bool(row and re.fullmatch(r'\d{6}', code) and
                 hmac.compare_digest(row.code_hash, otp_hash(challenge_id, code)))
    if not valid:
        db.session.commit()
        return jsonify(error=OTP_ERROR), 400
    user = db.session.get(User, row.user_id)
    if not user or user.is_blocked:
        db.session.commit()
        return jsonify(error=OTP_ERROR), 400
    row.used_at = now()
    # Session issuance, challenge consumption and old-session revocation commit
    # together; there is never a password-only authenticated session.
    rotate_session({'user': user.username, 'user_id': user.id, 'csrf': secrets.token_urlsafe(32)})
    return jsonify(authenticated=True, user={'username': user.username, 'email': user.email}, csrf_token=session['csrf'])


@auth.post('/resend-otp')
def resend_otp():
    challenge_id = session.get('challenge_id')
    row = db.session.get(OtpChallenge, challenge_id) if challenge_id else None
    limited = rate_limit('otp-send', str(row.user_id) if row else '', 5, 3600)
    if limited:
        return limited
    if not row or row.used_at is not None:
        return jsonify(error=OTP_ERROR), 400
    user = db.session.execute(db.select(User).where(User.id == row.user_id).with_for_update()).scalar_one()
    if user.is_blocked:
        db.session.rollback()
        return jsonify(error=OTP_ERROR), 400
    code = f'{secrets.randbelow(1000000):06d}'
    timestamp = now()
    changed = db.session.execute(update(OtpChallenge).where(
        OtpChallenge.id == challenge_id, OtpChallenge.used_at.is_(None),
        OtpChallenge.last_sent_at <= timestamp - 60
    ).values(code_hash=otp_hash(challenge_id, code), expires_at=timestamp + 300,
             last_sent_at=timestamp, attempts=0)).rowcount
    if not changed:
        remaining = max(1, row.last_sent_at + 60 - timestamp)
        db.session.rollback()
        return jsonify(error='Please wait before requesting another code.'), 429, {'Retry-After': str(remaining)}
    db.session.commit()
    try:
        send_otp(user.email, code)
    except Exception:
        current_app.logger.error('OTP email delivery failed')
        db.session.execute(update(OtpChallenge).where(OtpChallenge.id == challenge_id).values(expires_at=now()))
        db.session.commit()
        return jsonify(error='Unable to send a verification email. Please try again later.'), 503
    return jsonify(expires_in=300, resend_in=60)


@auth.post('/logout')
def logout():
    username = session.get('user')
    if session.get('challenge_id'):
        db.session.execute(delete(OtpChallenge).where(OtpChallenge.id == session['challenge_id']))
    db.session.execute(delete(ServerSession).where(ServerSession.token_hash == token_hash(session.token)))
    db.session.commit()
    session.clear()
    session.invalidated = True
    if username:
        current_app.config['CLOSE_USER_CONNECTION'](username)
    return jsonify(message='Signed out')


def init_auth(app):
    from modules.social import social
    app.register_blueprint(social)
    from modules.account_editing import accounts
    app.register_blueprint(accounts)
    from modules.user_profile import profiles
    app.register_blueprint(profiles)
    # Add the only missing column without replacing users or their message IDs.
    with app.app_context():
        columns = {column['name'] for column in inspect(db.engine).get_columns('users')}
        if 'email' not in columns:
            with db.engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN email TEXT'))
        with db.engine.begin() as connection:
            connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (email)'))
        db.create_all()
    app.session_interface = DatabaseSessionInterface()
    app.config['DUMMY_PASSWORD_HASH'] = generate_password_hash(secrets.token_urlsafe(32))
    app.register_blueprint(auth)

    @app.before_request
    def security_boundary():
        origin = request.headers.get('Origin')
        allowed = {app.config['FRONTEND_URL'], app.config['BACKEND_URL']}
        if origin and origin not in allowed:
            return jsonify(error='Origin not allowed'), 403
        if request.method == 'OPTIONS':
            return '', 204
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            supplied = request.headers.get('X-CSRF-Token', '')
            expected = session.get('csrf', '')
            if not expected or not hmac.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8')):
                return jsonify(error='Request verification failed'), 403
        public = request.path.startswith('/static/') or request.path in (
            '/', '/login', '/register', '/verify-otp', '/health',
            '/api/auth/csrf', '/api/auth/login', '/api/auth/register',
            '/api/auth/verify-otp', '/api/auth/resend-otp', '/api/auth/me', '/api/auth/logout')
        if not public:
            if not is_authenticated():
                if request.path == '/dashboard':
                    return redirect(app.config['FRONTEND_URL'] + '/login')
                return jsonify(error='Authentication required'), 401
            user = db.session.get(User, session['user_id'])
            if not user or user.is_blocked:
                return jsonify(error='Authentication required'), 401

    @app.after_request
    def security_headers(response):
        origin = request.headers.get('Origin')
        if origin in {app.config['FRONTEND_URL'], app.config['BACKEND_URL']}:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.vary.add('Origin')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if not request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store'
        if app.config['PRODUCTION']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.cli.command('link-email')
    @click.argument('username')
    @click.argument('email')
    def link_email(username, email):
        """Attach an operator-verified email to an existing chat username."""
        normalized = normalize_email(email)
        if not valid_email(normalized):
            raise click.ClickException('Invalid email address')
        user = User.query.filter_by(username=username).first()
        if not user:
            raise click.ClickException('Username not found')
        if user.email and user.email != normalized:
            raise click.ClickException('Account already has an email address')
        user.email = normalized
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise click.ClickException('Email already assigned')
        click.echo('Email linked; username and messages preserved.')
