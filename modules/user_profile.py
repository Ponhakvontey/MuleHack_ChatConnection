"""Optional, user-controlled profile data, separate from login credentials."""
from flask import Blueprint, jsonify, request, session
from sqlalchemy import text
from modules.extensions import db

profiles = Blueprint('user_profile', __name__, url_prefix='/api/user')
FIELDS = {'full_name': 120, 'display_name': 80, 'phone': 40,
          'organization': 160, 'major': 120, 'bio': 1000}


class UserProfile(db.Model):
    __tablename__ = 'user_profiles'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    organization = db.Column(db.String(160), nullable=False)
    major = db.Column(db.String(120), nullable=False)
    bio = db.Column(db.Text, nullable=False)


@profiles.route('/profile', methods=['GET', 'POST'])
def current_profile():
    # Existing application middleware enforces authentication and mutation CSRF.
    user_id = session['user_id']
    if request.method == 'GET':
        row = db.session.get(UserProfile, user_id)
        return jsonify(profile={field: getattr(row, field) for field in FIELDS} if row else None)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - set(FIELDS):
        return jsonify(error='Invalid profile fields.'), 400
    values = {}
    for field, maximum in FIELDS.items():
        value = data.get(field, '')
        if not isinstance(value, str) or len(value) > maximum:
            return jsonify(error=f'{field.replace("_", " ").capitalize()} must be text of at most {maximum} characters.'), 400
        values[field] = value.strip()
    # Primary-key upsert guarantees one profile per user, including concurrent saves.
    db.session.execute(text('''INSERT INTO user_profiles
        (user_id, full_name, display_name, phone, organization, major, bio)
        VALUES (:user_id, :full_name, :display_name, :phone, :organization, :major, :bio)
        ON CONFLICT (user_id) DO UPDATE SET full_name=excluded.full_name,
        display_name=excluded.display_name, phone=excluded.phone,
        organization=excluded.organization, major=excluded.major, bio=excluded.bio'''),
        dict(user_id=user_id, **values))
    db.session.commit()
    return jsonify(profile=values)
