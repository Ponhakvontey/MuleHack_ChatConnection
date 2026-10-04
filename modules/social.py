"""Friend discovery and private-chat permissions using stable account IDs."""
from flask import Blueprint, jsonify, request, session
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from modules.extensions import db
from modules.authentication import User, now, rate_limit
from modules.user_profile import UserProfile

social = Blueprint('social', __name__, url_prefix='/api/social')


class Friendship(db.Model):
    __tablename__ = 'friendships'
    low_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    high_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(16), nullable=False)
    updated_at = db.Column(db.BigInteger, nullable=False)


class UserBlock(db.Model):
    __tablename__ = 'blocked_users'
    blocker_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    blocked_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)


class Conversation(db.Model):
    __tablename__ = 'private_conversations'
    low_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    high_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    created_at = db.Column(db.BigInteger, nullable=False)


def pair(a, b):
    return tuple(sorted((a, b)))


def blocked(a, b):
    return bool(db.session.get(UserBlock, (a, b)) or db.session.get(UserBlock, (b, a)))


def friend_ids(uid):
    return {row.high_id if row.low_id == uid else row.low_id for row in Friendship.query.filter(
        or_(Friendship.low_id == uid, Friendship.high_id == uid), Friendship.status == 'accepted').all()
        if not blocked(uid, row.high_id if row.low_id == uid else row.low_id)}


def relationship(uid, other):
    if blocked(uid, other): return 'BLOCKED'
    row = db.session.get(Friendship, pair(uid, other))
    if not row: return 'NONE'
    if row.status == 'none': return 'NONE'
    if row.status == 'accepted': return 'FRIENDS'
    return 'PENDING_SENT' if row.requester_id == uid else 'PENDING_RECEIVED'


def public_user(user, uid):
    profile = db.session.get(UserProfile, user.id)
    return dict(id=user.id, username=user.username, full_name=profile.full_name if profile else '',
                relationship=relationship(uid, user.id))


def has_history(a, b):
    return db.session.execute(text('SELECT 1 FROM messages WHERE (sender=:a AND receiver=:b) OR (sender=:b AND receiver=:a) LIMIT 1'),
        dict(a=a.username, b=b.username)).first() is not None


def can_message(uid, username):
    other = User.query.filter_by(username=username).first() if isinstance(username, str) else None
    user = db.session.get(User, uid)
    if not user or not other or user.id == other.id or user.is_blocked or other.is_blocked or blocked(uid, other.id): return False
    # Grandfather genuine stored conversations without inventing friendships.
    return relationship(uid, other.id) == 'FRIENDS' or (db.session.get(Friendship, pair(uid, other.id)) is None and has_history(user, other))


def conversation_users(uid):
    user = db.session.get(User, uid)
    ids = {r.high_id if r.low_id == uid else r.low_id for r in Conversation.query.filter(or_(Conversation.low_id == uid, Conversation.high_id == uid)).all()}
    names = db.session.execute(text('SELECT DISTINCT CASE WHEN sender=:name THEN receiver ELSE sender END FROM messages WHERE sender=:name OR receiver=:name'), dict(name=user.username)).scalars().all()
    users = User.query.filter(or_(User.id.in_(ids), User.username.in_(names)), User.id != uid).order_by(User.username).all()
    return [dict(public_user(other, uid), can_message=can_message(uid, other.username)) for other in users]


@social.get('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query: return jsonify(users=[])
    if len(query) > 100: return jsonify(error='Search is too long.'), 400
    # Escape LIKE wildcards; case-insensitive literal partial matching.
    pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    users = User.query.outerjoin(UserProfile, UserProfile.user_id == User.id).filter(
        User.id != session['user_id'], User.is_blocked == 0,
        or_(User.username.ilike(pattern, escape='\\'), UserProfile.full_name.ilike(pattern, escape='\\'))).order_by(User.username).all()
    return jsonify(users=[public_user(u, session['user_id']) for u in users if not blocked(session['user_id'], u.id)][:30])


@social.get('/state')
def state():
    uid = session['user_id']
    own_friends = friend_ids(uid)
    friends, incoming, outgoing, recommendations = [], [], [], []
    profile = db.session.get(UserProfile, uid)
    for user in User.query.filter(User.id != uid, User.is_blocked == 0).order_by(User.username).all():
        data = public_user(user, uid)
        status = data['relationship']
        if status == 'FRIENDS': friends.append(data)
        elif status == 'PENDING_RECEIVED': incoming.append(data)
        elif status == 'PENDING_SENT': outgoing.append(data)
        elif status == 'NONE':
            other_profile = db.session.get(UserProfile, user.id)
            mutual = len(own_friends & friend_ids(user.id))
            same_org = bool(profile and other_profile and profile.organization.strip() and profile.organization.strip().casefold() == other_profile.organization.strip().casefold())
            same_major = bool(profile and other_profile and profile.major.strip() and profile.major.strip().casefold() == other_profile.major.strip().casefold())
            score = 50*mutual + 25*same_org + 15*same_major
            if score:
                reasons = ([f'{mutual} mutual friend' + ('s' if mutual != 1 else '')] if mutual else []) + (['Same organization'] if same_org else []) + (['Same major'] if same_major else [])
                recommendations.append((score, dict(data, reason=' · '.join(reasons))))
    recommendations.sort(key=lambda r: (-r[0], r[1]['username']))
    blocks = UserBlock.query.filter_by(blocker_id=uid).all()
    blocked_users = [public_user(db.session.get(User, row.blocked_id), uid) for row in blocks]
    return jsonify(friends=friends, incoming=incoming, outgoing=outgoing,
        recommended=[data for _, data in recommendations[:20]], blocked=blocked_users,
        conversations=conversation_users(uid))


@social.post('/action')
def action():
    limited = rate_limit('social-action', str(session['user_id']), 60, 60)
    if limited: return limited
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'user_id', 'action'} or type(data['user_id']) is not int:
        return jsonify(error='Invalid request.'), 400
    uid, other_id, operation = session['user_id'], data['user_id'], data['action']
    other = db.session.get(User, other_id)
    if not other or uid == other_id or other.is_blocked: return jsonify(error='Invalid user.'), 400
    if operation not in ('request', 'accept', 'decline', 'cancel', 'block', 'unblock', 'message'):
        return jsonify(error='Invalid action.'), 400
    # Lock accounts consistently in PostgreSQL to serialize pair changes.
    db.session.query(User).filter(User.id.in_([uid, other_id])).order_by(User.id).with_for_update().all()
    key = pair(uid, other_id)
    row = db.session.get(Friendship, key)
    if operation == 'unblock':
        mine = db.session.get(UserBlock, (uid, other_id))
        if mine: db.session.delete(mine)
    elif operation == 'block':
        db.session.merge(UserBlock(blocker_id=uid, blocked_id=other_id))
        if row: row.status = 'none'; row.updated_at = now()
        else: db.session.add(Friendship(low_id=key[0], high_id=key[1], requester_id=uid, status='none', updated_at=now()))
    else:
        if blocked(uid, other_id): return jsonify(error='This user is blocked.'), 403
        if operation == 'request':
            if row and row.status != 'none': return jsonify(error='A friendship or request already exists.'), 409
            if row: row.requester_id = uid; row.status = 'pending'; row.updated_at = now()
            else: db.session.add(Friendship(low_id=key[0], high_id=key[1], requester_id=uid, status='pending', updated_at=now()))
        elif operation in ('accept', 'decline'):
            if not row or row.status != 'pending' or row.requester_id == uid: return jsonify(error='No incoming request.'), 403
            if operation == 'decline': row.status = 'none'; row.updated_at = now()
            else: row.status = 'accepted'; row.updated_at = now()
        elif operation == 'cancel':
            if not row or row.status != 'pending' or row.requester_id != uid: return jsonify(error='No outgoing request.'), 403
            row.status = 'none'; row.updated_at = now()
        elif operation == 'message':
            if not can_message(uid, other.username): return jsonify(error='Become friends before starting a conversation.'), 403
            if not db.session.get(Conversation, key): db.session.add(Conversation(low_id=key[0], high_id=key[1], created_at=now()))
    try: db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='Relationship changed. Refresh and try again.'), 409
    return jsonify(status='ok', username=other.username, relationship=relationship(uid, other_id))
