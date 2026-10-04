import os
import secrets
from pathlib import Path
from urllib.parse import urlparse


def configure(app):
    production = os.getenv('NODE_ENV') == 'production' or os.getenv('RENDER') == 'true'
    secret = os.getenv('SESSION_SECRET') or os.getenv('SECRET_KEY')
    if not secret:
        if production:
            raise RuntimeError('SESSION_SECRET is required in production')
        key_file = Path(app.root_path) / '.secret_key'
        if not key_file.exists():
            key_file.write_text(secrets.token_hex(32), encoding='utf-8')
        secret = key_file.read_text(encoding='utf-8').strip()
    if len(secret) < 32:
        raise RuntimeError('SESSION_SECRET must contain at least 32 characters')
    database_url = os.getenv('DATABASE_URL')
    if production and (not database_url or not database_url.startswith(('postgres://', 'postgresql://'))):
        raise RuntimeError('Production requires a persistent PostgreSQL DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    if not database_url:
        database_url = 'sqlite:///' + Path(os.getenv('LOCAL_DATABASE_PATH') or str(Path(app.instance_path) / 'database.db')).resolve().as_posix()
    frontend = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
    backend = os.getenv('BACKEND_URL', 'http://localhost:5000').rstrip('/')
    if production:
        for value in (frontend, backend):
            if urlparse(value).scheme != 'https':
                raise RuntimeError('Production FRONTEND_URL and BACKEND_URL must use HTTPS')
        if os.getenv('SMTP_SSL', 'false').lower() != 'true' and os.getenv('SMTP_STARTTLS', 'true').lower() != 'true':
            raise RuntimeError('Production SMTP must use TLS')
        for name in ('SMTP_HOST', 'SMTP_FROM'):
            if not os.getenv(name):
                raise RuntimeError(f'{name} is required in production')
        if os.getenv('USE_SUPABASE') != 'true' or not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_KEY'):
            raise RuntimeError('Production requires USE_SUPABASE=true and private Supabase storage credentials')
    same_site = os.getenv('SESSION_COOKIE_SAMESITE', 'None' if production else 'Lax')
    if same_site not in ('Lax', 'Strict', 'None'):
        raise RuntimeError('Invalid SESSION_COOKIE_SAMESITE')
    otp_secret = os.getenv('OTP_SECRET') or secret
    if len(otp_secret) < 32:
        raise RuntimeError('OTP_SECRET must contain at least 32 characters')
    app.config.update(
        SECRET_KEY=secret, PRODUCTION=production,
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        FRONTEND_URL=frontend, BACKEND_URL=backend,
        SESSION_COOKIE_NAME='__Host-talky_session' if production else 'talky_session',
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=production,
        SESSION_COOKIE_SAMESITE=same_site, SESSION_COOKIE_PATH='/',
        SESSION_TTL_SECONDS=28800, MAX_CONTENT_LENGTH=25 * 1024 * 1024,
        OTP_SECRET=otp_secret,
        CHAT_KEY_SECRET=os.getenv('CHAT_KEY_SECRET') or secret,
    )
