"""Domain-only, unverified reports. No message content or conversation metadata."""
import re
from flask import Blueprint, jsonify, request, session
from sqlalchemy.exc import IntegrityError
from modules.extensions import db
from modules.authentication import now, rate_limit

community_threats = Blueprint('community_threats', __name__, url_prefix='/api/threats')


class ThreatReport(db.Model):
    __tablename__ = 'threat_reports'
    reporter_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    indicator = db.Column(db.String(253), primary_key=True)
    category = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.BigInteger, nullable=False)


def normalize_domain(value):
    if not isinstance(value, str) or len(value) > 253:
        raise ValueError('Provide a domain only, without a URL, path, or query.')
    domain = value.lower().rstrip('.')
    try:
        domain = domain.encode('idna').decode('ascii')
    except UnicodeError:
        raise ValueError('Invalid domain.') from None
    labels = domain.split('.')
    if len(domain) > 253 or len(labels) < 2 or all(part.isdigit() for part in labels):
        raise ValueError('Invalid domain.')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in labels):
        raise ValueError('Invalid domain.')
    return domain


def summary(domain):
    return dict(indicator=domain, indicator_type='domain',
                report_count=ThreatReport.query.filter_by(indicator=domain).count(),
                reported_by_you=db.session.get(ThreatReport, (session['user_id'], domain)) is not None,
                status='unverified', scope='exact_hostname')


@community_threats.get('/community')
def community():
    limited = rate_limit('threat-read', str(session['user_id']), 120, 60)
    if limited is not None:
        return limited
    try:
        domain = normalize_domain(request.args.get('indicator'))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify(summary(domain))


@community_threats.post('/report')
def report():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Invalid report.'), 400
    try:
        domain = normalize_domain(data.get('indicator'))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    action = data.get('action', 'report')
    category = data.get('category', 'suspicious_link')
    if action not in ('report', 'withdraw') or category not in ('suspicious_link', 'possible_phishing', 'scam'):
        return jsonify(error='Invalid report action or category.'), 400
    limited = rate_limit('threat-report', str(session['user_id']), 20, 3600)
    if limited is not None:
        return limited
    row = db.session.get(ThreatReport, (session['user_id'], domain))
    if action == 'withdraw':
        if row:
            db.session.delete(row)
    elif not row:
        db.session.add(ThreatReport(reporter_user_id=session['user_id'], indicator=domain,
                                   category=category, created_at=now()))
    try:
        db.session.commit()
    except IntegrityError:
        # Concurrent duplicate submissions cannot inflate the composite key.
        db.session.rollback()
    return jsonify(summary(domain))
