import json
import re
import secrets
from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash
from modules.extensions import db
from modules.authentication import User, ServerSession, OtpChallenge, now, otp_hash, send_otp, rate_limit, token_hash, normalize_email, valid_email, verify_password

accounts = Blueprint('account_editing', __name__, url_prefix='/api/user')


class ChatIdentity(db.Model):
    __tablename__ = 'user_chat_identities'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    original_username = db.Column(db.Text, unique=True, nullable=False)


class EmailChange(db.Model):
    __tablename__ = 'user_email_changes'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    challenge_id = db.Column(db.String(64), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    email = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    sent_at = db.Column(db.BigInteger, nullable=False)
    attempts = db.Column(db.Integer, nullable=False)


class PreviousUsername(db.Model):
    __tablename__ = 'user_previous_usernames'
    username = db.Column(db.Text, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


def chat_identity(username):
    user = User.query.filter_by(username=username).first()
    identity = db.session.get(ChatIdentity, user.id) if user else None
    return identity.original_username if identity else username


def revoke_other_sessions(user):
    for row in ServerSession.query.all():
        if json.loads(row.data).get('user_id') == user.id and row.token_hash != token_hash(session.token):
            db.session.delete(row)
    db.session.execute(delete(OtpChallenge).where(OtpChallenge.user_id == user.id))


@accounts.post('/account')
def update_account():
    user = User.query.filter_by(id=session['user_id']).with_for_update().one()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not {'username', 'email'} <= set(data) or set(data) - {'username', 'email', 'profile'}:
        return jsonify(error='Invalid account fields.'), 400
    from modules.user_profile import FIELDS, UserProfile
    profile_values = data.get('profile')
    if profile_values is not None:
        if not isinstance(profile_values, dict) or set(profile_values) != set(FIELDS) or any(not isinstance(profile_values[k], str) or len(profile_values[k]) > maximum for k, maximum in FIELDS.items()):
            return jsonify(error='Invalid profile fields.'), 400
        profile_values = {k: value.strip() for k, value in profile_values.items()}
    username, email = data['username'], normalize_email(data['email'])
    if not isinstance(username, str) or not re.fullmatch(r'[\w.-]{1,50}', username):
        return jsonify(error='Please enter a valid username.'), 400
    if not valid_email(email):
        return jsonify(error='Please enter a valid email address.'), 400
    if User.query.filter(User.username == username, User.id != user.id).first() or ChatIdentity.query.filter(ChatIdentity.original_username == username, ChatIdentity.user_id != user.id).first() or PreviousUsername.query.filter(PreviousUsername.username == username, PreviousUsername.user_id != user.id).first():
        return jsonify(error='That username is already in use.'), 409
    if User.query.filter(User.email == email, User.id != user.id).first():
        return jsonify(error='That email is already in use.'), 409
    # Verify the new mailbox before changing either account field.
    if email != user.email:
        limited = rate_limit('account-email', str(user.id), 5, 3600)
        if limited: return limited
        user = User.query.filter_by(id=session['user_id']).with_for_update().one()
        pending = db.session.get(EmailChange, user.id)
        if pending and pending.email == email and pending.expires_at > now() and pending.attempts == -1:
            db.session.delete(pending)
        else:
            if pending and now() - pending.sent_at < 60:
                return jsonify(error='Please wait 60 seconds before requesting another code.'), 429
            challenge = secrets.token_hex(32)
            otp = f'{secrets.randbelow(1000000):06d}'
            try: send_otp(email, otp)
            except Exception:
                current_app.logger.error('Account verification email delivery failed')
                return jsonify(error='Unable to send a verification email. Please try again later.'), 503
            db.session.merge(EmailChange(user_id=user.id, email=email, challenge_id=challenge,
                code_hash=otp_hash(challenge, otp), sent_at=now(), expires_at=now()+300, attempts=0))
            db.session.commit()
            return jsonify(otp_required=True)
    old = user.username
    renamed = old != username
    email_changed = user.email != email
    try:
        if renamed:
            db.session.merge(PreviousUsername(username=old, user_id=user.id))
            if not db.session.get(ChatIdentity, user.id):
                db.session.add(ChatIdentity(user_id=user.id, original_username=old))
            for column in ('sender', 'receiver'):
                db.session.execute(text(f'UPDATE messages SET {column}=:new WHERE {column}=:old'), {'old': old, 'new': username})
            db.session.execute(text('UPDATE logs SET username=:new WHERE username=:old'), {'old': old, 'new': username})
            row = db.session.get(ServerSession, token_hash(session.token))
            row.data = json.dumps(dict(session, user=username))
        if renamed or email_changed:
            revoke_other_sessions(user)
        user.username, user.email = username, email
        if profile_values is not None:
            db.session.merge(UserProfile(user_id=user.id, **profile_values))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='That username or email is already in use.'), 409
    if renamed:
        session['user'] = username
        current_app.config['CLOSE_USER_CONNECTION'](old)
    return jsonify(user={'username': username, 'email': email}, renamed=renamed, profile=profile_values)


@accounts.post('/verify-account-email')
def verify_email_change():
    limited = rate_limit('account-email-verify', str(session['user_id']), 20, 600)
    if limited: return limited
    data = request.get_json(silent=True)
    code = data.get('code', '') if isinstance(data, dict) else ''
    pending = db.session.get(EmailChange, session['user_id'])
    if not pending or pending.expires_at <= now() or not 0 <= pending.attempts < 5:
        return jsonify(error='Invalid or expired verification code.'), 400
    result = db.session.execute(text('UPDATE user_email_changes SET attempts=attempts+1 WHERE user_id=:uid AND challenge_id=:challenge AND attempts>=0 AND attempts<5 AND expires_at>:now RETURNING attempts'),
        dict(uid=session['user_id'], challenge=pending.challenge_id, now=now())).scalar_one_or_none()
    valid = result is not None and isinstance(code, str) and re.fullmatch(r'\d{6}', code) and secrets.compare_digest(pending.code_hash, otp_hash(pending.challenge_id, code))
    if valid:
        db.session.execute(text('UPDATE user_email_changes SET attempts=-1 WHERE user_id=:uid AND challenge_id=:challenge'), dict(uid=session['user_id'], challenge=pending.challenge_id))
    db.session.commit()
    if not valid: return jsonify(error='Invalid or expired verification code.'), 400
    return jsonify(verified=True)


@accounts.post('/change-password')
def change_password():
    limited = rate_limit('change-password', str(session['user_id']), 5, 600)
    if limited: return limited
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'current_password', 'new_password', 'confirm_password'}:
        return jsonify(error='Invalid password request.'), 400
    user = User.query.filter_by(id=session['user_id']).with_for_update().one()
    current, new, confirm = (data[k] for k in ('current_password', 'new_password', 'confirm_password'))
    if not verify_password(user.password, current):
        return jsonify(error='Current password is incorrect.'), 400
    if new != confirm: return jsonify(error='New passwords do not match.'), 400
    if not isinstance(new, str) or not 6 <= len(new) <= 1024 or (new.isdigit() and len(set(new)) == 1):
        return jsonify(error='Please enter a valid password of at least 6 characters.'), 400
    user.password = generate_password_hash(new)
    revoke_other_sessions(user)
    db.session.execute(delete(EmailChange).where(EmailChange.user_id == user.id))
    db.session.commit()
    return jsonify(message='Password updated successfully.')
