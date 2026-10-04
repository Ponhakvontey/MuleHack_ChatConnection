"""Reuse the existing isolated database/auth fixture; never touch live data."""
import unittest
from pathlib import Path
import test_authentication as fixture
from test_authentication import app, db, User
from modules.community_threats import ThreatReport, normalize_domain


def setUpModule():
    # The original module removes its temporary DB in tearDownModule. Recreate
    # only that isolated test location if discovery ran it before this module.
    Path(fixture.temporary.name).mkdir(exist_ok=True)
    with app.app_context():
        db.create_all()


def tearDownModule():
    fixture.tearDownModule()


class CommunityThreatTests(unittest.TestCase):
    post = fixture.AuthenticationTests.post
    login = fixture.AuthenticationTests.login
    authenticate = fixture.AuthenticationTests.authenticate

    def setUp(self):
        with app.app_context():
            ThreatReport.query.delete()
            db.session.commit()
        fixture.AuthenticationTests.setUp(self)

    def tearDown(self):
        ThreatReport.query.delete()
        db.session.commit()
        fixture.AuthenticationTests.tearDown(self)

    def test_domain_only_validation(self):
        self.assertEqual(normalize_domain('EXAMPLE.com.'), 'example.com')
        for value in ('https://example.com/private?token=secret', 'example.com/path', 'localhost', '127.0.0.1', '<script>', {}, None):
            with self.assertRaises(ValueError):
                normalize_domain(value)

    def test_authentication_csrf_and_input_validation(self):
        self.assertEqual(self.client.get('/api/threats/community?indicator=example.com').status_code, 401)
        self.assertEqual(self.post('/api/threats/report', {'indicator': 'example.com'}).status_code, 401)
        self.authenticate()
        self.assertEqual(self.client.post('/api/threats/report', json={'indicator': 'example.com'}).status_code, 403)
        self.assertEqual(self.post('/api/threats/report', {'indicator': 'example.com/path'}).status_code, 400)
        self.assertEqual(self.post('/api/threats/report', {'indicator': 'example.com', 'category': '<script>'}).status_code, 400)
        self.assertEqual(ThreatReport.query.count(), 0)

    def test_deduplication_cross_user_summary_privacy_and_withdrawal(self):
        self.authenticate()
        bob = User.query.filter_by(username='bob').one()
        # Frontend-supplied identities and notes are ignored, never persisted.
        payload = dict(indicator='EXAMPLE.com', reporter_user_id=bob.id, note='private conversation')
        for _ in range(2):
            response = self.post('/api/threats/report', payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['report_count'], 1)
        self.assertEqual(ThreatReport.query.one().reporter_user_id, self.user.id)
        alice_csrf = self.csrf
        # Authenticate another independent browser session.
        other = app.test_client()
        csrf = other.get('/api/auth/csrf').json['csrf_token']
        response = self.post('/api/auth/login', {'email': bob.email, 'password': 'testpass123'}, other, csrf)
        self.assertEqual(response.status_code, 200)
        response = self.post('/api/auth/verify-otp', {'code': self.mail[-1][1]}, other, response.json['csrf_token'])
        self.assertEqual(response.status_code, 200)
        other_csrf = response.json['csrf_token']
        summary = other.get('/api/threats/community?indicator=example.com').json
        self.assertEqual(summary['report_count'], 1)
        self.assertFalse(summary['reported_by_you'])
        self.assertEqual(set(summary), {'indicator', 'indicator_type', 'report_count', 'reported_by_you', 'status', 'scope'})
        self.assertEqual(summary['status'], 'unverified')
        self.assertEqual(self.post('/api/threats/report', {'indicator': 'example.com'}, other, other_csrf).json['report_count'], 2)
        self.csrf = alice_csrf
        self.assertEqual(self.post('/api/threats/report', {'indicator': 'example.com', 'action': 'withdraw'}).json['report_count'], 1)
        self.assertEqual(self.client.get('/api/threats/community?indicator=elsewhere.example').json['report_count'], 0)

    def test_report_rate_limit(self):
        self.authenticate()
        for _ in range(20):
            self.assertEqual(self.post('/api/threats/report', {'indicator': 'example.com'}).status_code, 200)
        self.assertEqual(self.post('/api/threats/report', {'indicator': 'example.com'}).status_code, 429)
        self.assertEqual(ThreatReport.query.count(), 1)
