import hashlib
import io
import json
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Never run authentication tests against an existing application database.
temporary = tempfile.TemporaryDirectory(prefix='auth-test-', dir=Path(__file__).resolve().parents[1])
os.environ['LOCAL_DATABASE_PATH'] = str(Path(temporary.name) / 'test.db')
os.environ['SESSION_SECRET'] = secrets.token_hex(32)
os.environ['NODE_ENV'] = 'test'
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ.pop('DATABASE_URL', None)
os.environ.pop('RENDER', None)
os.environ.pop('USE_SUPABASE', None)

from app import app, db, Message
from modules.user_profile import UserProfile
from modules.account_editing import ChatIdentity, EmailChange, PreviousUsername
from modules.social import Friendship, UserBlock, Conversation, can_message
from modules.authentication import User, OtpChallenge, ServerSession, RateLimit, send_otp, verify_password
from werkzeug.security import generate_password_hash


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        db.session.remove()
        for model in (Conversation, UserBlock, Friendship, PreviousUsername, ChatIdentity, EmailChange, UserProfile, ServerSession, OtpChallenge, RateLimit, Message, User):
            db.session.query(model).delete()
        db.session.commit()
        self.clock = patch('modules.authentication.now', return_value=1800000000)
        self.now = self.clock.start()
        # WebSocket uses the same imported clock function.
        self.ws_clock = patch('app.now', side_effect=lambda: self.now.return_value)
        self.ws_clock.start()
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False, SESSION_COOKIE_SAMESITE='Lax')
        self.mail = []
        app.config['OTP_SENDER'] = lambda email, code: self.mail.append((email, code))
        self.user = User(username='alice', email='alice@example.test', password=generate_password_hash('testpass123'))
        db.session.add(self.user)
        db.session.add(User(username='bob', email='bob@example.test', password=generate_password_hash('testpass123')))
        db.session.commit()
        bob = User.query.filter_by(username='bob').one()
        db.session.add(Friendship(low_id=self.user.id, high_id=bob.id, requester_id=self.user.id, status='accepted', updated_at=1800000000))
        db.session.commit()
        self.client = app.test_client()
        self.csrf = self.client.get('/api/auth/csrf').json['csrf_token']

    def tearDown(self):
        self.clock.stop()
        self.ws_clock.stop()
        db.session.remove()
        self.context.pop()

    def post(self, path, data=None, client=None, csrf=None):
        response = (client or self.client).post(path, json=data or {},
            headers={'X-CSRF-Token': csrf or self.csrf, 'Origin': app.config['FRONTEND_URL']})
        if response.is_json and response.json.get('csrf_token'):
            self.csrf = response.json['csrf_token']
        return response

    def login(self):
        return self.post('/api/auth/login', {'email': 'alice@example.test', 'password': 'testpass123'})

    def authenticate(self):
        self.assertEqual(self.login().status_code, 200)
        response = self.post('/api/auth/verify-otp', {'code': self.mail[-1][1]})
        self.assertEqual(response.status_code, 200)
        return response

    def test_new_user_social_flow_and_block_history_preservation(self):
        Friendship.query.delete(); db.session.commit()
        self.authenticate()
        bob = User.query.filter_by(username='bob').one()
        state = self.client.get('/api/social/state').json
        self.assertEqual(state['friends'], [])
        self.assertEqual(state['conversations'], [])
        self.assertEqual(self.client.get('/api/dashboard').json['users'], [])
        self.assertFalse(can_message(self.user.id, 'bob'))
        def action(kind): return self.post('/api/social/action', {'user_id': bob.id, 'action': kind})
        self.assertEqual(action('request').status_code, 200)
        self.assertEqual(self.client.get('/api/social/state').json['outgoing'][0]['username'], 'bob')
        self.assertEqual(Conversation.query.count(), 0)
        self.assertEqual(action('accept').status_code, 403)
        self.post('/api/auth/logout'); self.csrf = self.client.get('/api/auth/csrf').json['csrf_token']
        self.post('/api/auth/login', {'email': 'bob@example.test', 'password': 'testpass123'})
        self.post('/api/auth/verify-otp', {'code': self.mail[-1][1]})
        self.assertEqual(self.client.get('/api/social/state').json['incoming'][0]['username'], 'alice')
        self.assertEqual(self.post('/api/social/action', {'user_id': self.user.id, 'action': 'accept'}).status_code, 200)
        self.assertEqual(Conversation.query.count(), 0)
        self.assertEqual(self.post('/api/social/action', {'user_id': self.user.id, 'action': 'message'}).status_code, 200)
        self.assertEqual(self.post('/api/social/action', {'user_id': self.user.id, 'action': 'message'}).status_code, 200)
        self.assertEqual(Conversation.query.count(), 1)
        self.assertEqual(self.post('/send', {'receiver': 'alice', 'ciphertext': 'cipher', 'nonce': 'nonce'}).status_code, 201)
        self.assertEqual(self.post('/api/social/action', {'user_id': self.user.id, 'action': 'block'}).status_code, 200)
        self.assertFalse(can_message(bob.id, 'alice')); self.assertFalse(can_message(self.user.id, 'bob'))
        self.assertEqual(self.post('/send', {'receiver': 'alice', 'ciphertext': 'cipher', 'nonce': 'nonce'}).status_code, 403)
        self.assertEqual(self.post('/api/social/action', {'user_id': self.user.id, 'action': 'request'}).status_code, 403)
        self.assertEqual(len(self.client.get('/messages/alice').json), 1)
        self.assertEqual(self.client.get('/api/social/state').json['blocked'][0]['username'], 'alice')
        self.assertEqual(self.post('/api/social/action', {'user_id': self.user.id, 'action': 'unblock'}).json['relationship'], 'NONE')
        self.assertFalse(can_message(bob.id, 'alice'))
        self.assertEqual(Message.query.count(), 1)
        self.assertEqual(self.post('/api/social/action', {'user_id': self.user.id, 'action': 'request'}).status_code, 200)

    def test_call_control_events_forward_with_session_sender_and_call_id(self):
        from app import connections
        self.authenticate()
        cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        for kind in ('call-offer', 'call-accept', 'call-answer', 'call-decline', 'call-cancel', 'call-busy', 'ice-candidate'):
            ws, target = MagicMock(), MagicMock()
            ws.connected = False
            ws.receive.side_effect = ['alice', json.dumps(dict(type=kind, sender='spoof', receiver='bob', callType='video', callId='test-call', status='missed')), None]
            with patch.dict(connections, {'bob': target}), patch('app.live_connection', return_value=target), app.test_request_context('/ws', headers={'Cookie': app.config['SESSION_COOKIE_NAME'] + '=' + cookie}):
                app.view_functions['websocket'].__wrapped__(ws)
            target.send.assert_called_once()
            payload = json.loads(target.send.call_args.args[0])
            self.assertEqual(payload['sender'], 'alice')
            self.assertEqual(payload['callId'], 'test-call')
            self.assertEqual(payload['type'], kind)
        self.assertTrue(all(m.status != 'ended' for m in Message.query.all()))

    def test_friend_websocket_forwarding_and_blocked_upload(self):
        from app import connections, connection_sessions
        self.authenticate()
        cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        ws, target = MagicMock(), MagicMock()
        ws.connected = False
        ws.receive.side_effect = ['alice', json.dumps({'receiver': 'bob', 'ciphertext': 'cipher', 'nonce': 'nonce'}), None]
        with patch.dict(connections, {'bob': target}), patch('app.live_connection', return_value=target), app.test_request_context('/ws', headers={'Cookie': app.config['SESSION_COOKIE_NAME'] + '=' + cookie}):
            app.view_functions['websocket'].__wrapped__(ws)
        target.send.assert_called_once()
        self.assertEqual(json.loads(target.send.call_args.args[0])['sender'], 'alice')
        self.assertEqual(Message.query.count(), 1)
        bob = User.query.filter_by(username='bob').one()
        self.post('/api/social/action', {'user_id': bob.id, 'action': 'block'})
        denied = MagicMock(); denied.connected = False
        denied.receive.side_effect = ['alice', json.dumps({'receiver': 'bob', 'ciphertext': 'cipher', 'nonce': 'nonce'}), None]
        with patch.dict(connections, {'bob': target}), patch('app.live_connection', return_value=target), app.test_request_context('/ws', headers={'Cookie': app.config['SESSION_COOKIE_NAME'] + '=' + cookie}):
            app.view_functions['websocket'].__wrapped__(denied)
        self.assertEqual(json.loads(denied.send.call_args.args[0])['type'], 'error')
        self.assertEqual(Message.query.count(), 1)
        response = self.client.post('/upload_file', data={'receiver': 'bob', 'file': (io.BytesIO(b'blocked'), 'file.pdf')}, headers={'X-CSRF-Token': self.csrf})
        self.assertEqual(response.status_code, 403)

    def test_search_recommendations_and_social_privacy(self):
        Friendship.query.delete(); db.session.commit()
        self.authenticate()
        bob = User.query.filter_by(username='bob').one()
        db.session.add(UserProfile(user_id=bob.id, full_name='Robert Smith', display_name='', phone='private', organization='UCM', major='CS', bio=''))
        db.session.commit()
        self.post('/api/user/profile', dict(full_name='', display_name='', phone='', organization='UCM', major='CS', bio=''))
        found = self.client.get('/api/social/search?q=rob').json['users']
        self.assertEqual(found[0]['username'], 'bob')
        self.assertNotIn('email', found[0]); self.assertNotIn('phone', found[0]); self.assertNotIn('password', found[0])
        self.assertEqual(self.client.get('/api/social/search?q=ali').json['users'], [])
        recommended = self.client.get('/api/social/state').json['recommended']
        self.assertEqual(recommended[0]['username'], 'bob'); self.assertIn('Same organization', recommended[0]['reason'])
        self.assertEqual(self.post('/api/social/action', {'user_id': bob.id, 'action': 'request', 'requester_id': bob.id}).status_code, 400)
        self.post('/api/social/action', {'user_id': bob.id, 'action': 'request'})
        self.assertEqual(self.client.get('/api/social/state').json['recommended'], [])
        self.assertEqual(self.post('/api/social/action', {'user_id': bob.id, 'action': 'cancel'}).status_code, 200)
        self.post('/api/social/action', {'user_id': bob.id, 'action': 'block'})
        self.assertEqual(self.client.get('/api/social/search?q=bob').json['users'], [])
        self.assertEqual(self.client.get('/api/social/state').json['recommended'], [])

    def test_account_mutations_are_private_and_profile_save_is_atomic(self):
        for endpoint in ('account', 'change-password', 'verify-account-email'):
            self.assertEqual(self.post('/api/user/' + endpoint, {}).status_code, 401)
        self.authenticate()
        self.assertEqual(self.post('/api/user/account', {'username': 'alice2', 'email': 'alice@example.test', 'user_id': 2}).status_code, 400)
        profile = {key: '' for key in ('full_name', 'display_name', 'phone', 'organization', 'major', 'bio')}
        profile['bio'] = 'x' * 1001
        payload = dict(username='alice2', email='alice@example.test', profile=profile)
        self.assertEqual(self.post('/api/user/account', payload).status_code, 400)
        self.assertEqual(db.session.get(User, self.user.id).username, 'alice')
        profile['bio'] = 'Saved together'
        self.assertEqual(self.post('/api/user/account', payload).status_code, 200)
        self.assertEqual(self.client.get('/api/user/profile').json['profile']['bio'], 'Saved together')
        self.assertEqual(self.post('/api/user/account', {'username': 'alice3', 'email': 'alice@example.test'}).status_code, 200)
        self.post('/api/auth/register', {'username': 'alice2', 'email': 'other@example.test', 'password': 'testpass123'})
        self.assertIsNone(User.query.filter_by(email='other@example.test').first())

    def test_account_email_code_attempts_and_expiry(self):
        self.authenticate()
        payload = dict(username='alice', email='new@example.test')
        self.post('/api/user/account', payload)
        code = self.mail[-1][1]
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            self.assertEqual(self.post('/api/user/verify-account-email', {'code': wrong}).status_code, 400)
        self.assertEqual(self.post('/api/user/verify-account-email', {'code': code}).status_code, 400)
        self.now.return_value += 61
        self.post('/api/user/account', payload)
        code = self.mail[-1][1]
        self.now.return_value += 300
        self.assertEqual(self.post('/api/user/verify-account-email', {'code': code}).status_code, 400)
        self.assertEqual(db.session.get(User, self.user.id).email, 'alice@example.test')

    def test_account_rename_preserves_identity_messages_and_keys(self):
        self.authenticate()
        uid = self.user.id
        key = self.client.get('/conversation_key/bob').json['key']
        self.post('/api/user/profile', {'bio': 'Keep me'})
        db.session.add(Message(sender='alice', receiver='bob', ciphertext='cipher', nonce='nonce', msg_type='text'))
        db.session.commit()
        self.assertEqual(self.post('/api/user/account', {'username': 'bob', 'email': 'alice@example.test'}).status_code, 409)
        response = self.post('/api/user/account', {'username': 'alice2', 'email': 'alice@example.test'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(User, uid).username, 'alice2')
        self.assertEqual(self.client.get('/api/auth/me').json['user']['username'], 'alice2')
        self.assertEqual(Message.query.first().sender, 'alice2')
        self.assertEqual(self.client.get('/conversation_key/bob').json['key'], key)
        self.assertEqual(self.client.get('/api/user/profile').json['profile']['bio'], 'Keep me')
        self.assertEqual(User.query.count(), 2)
        self.assertEqual(self.post('/api/user/account', {'username': 'alice3', 'email': 'alice@example.test'}).status_code, 200)
        self.assertEqual(self.client.get('/conversation_key/bob').json['key'], key)

    def test_account_email_requires_otp_and_keeps_user(self):
        self.authenticate()
        payload = {'username': 'alice', 'email': 'new@example.test'}
        self.assertEqual(self.post('/api/user/account', {'username': 'alice', 'email': 'bob@example.test'}).status_code, 409)
        self.assertEqual(self.post('/api/user/account', {'username': 'alice', 'email': 'invalid'}).status_code, 400)
        self.assertTrue(self.post('/api/user/account', payload).json['otp_required'])
        self.assertEqual(self.mail[-1][0], 'new@example.test')
        self.assertEqual(db.session.get(User, self.user.id).email, 'alice@example.test')
        code = self.mail[-1][1]
        wrong = '000000' if code != '000000' else '111111'
        self.assertEqual(self.post('/api/user/verify-account-email', {'code': wrong}).status_code, 400)
        self.assertEqual(self.post('/api/user/verify-account-email', {'code': code}).status_code, 200)
        self.assertEqual(self.post('/api/user/verify-account-email', {'code': code}).status_code, 400)
        self.assertEqual(self.post('/api/user/account', payload).status_code, 200)
        self.assertEqual(db.session.get(User, self.user.id).email, 'new@example.test')
        self.assertEqual(User.query.count(), 2)

    def test_password_change_validation_and_login(self):
        self.authenticate()
        payload = dict(current_password='wrong', new_password='newpass123', confirm_password='newpass123')
        self.assertEqual(self.post('/api/user/change-password', payload).status_code, 400)
        payload['current_password'] = 'testpass123'
        payload['confirm_password'] = 'different'
        self.assertEqual(self.post('/api/user/change-password', payload).status_code, 400)
        payload['confirm_password'] = 'newpass123'
        response = self.post('/api/user/change-password', payload)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('password', response.json)
        self.assertNotEqual(db.session.get(User, self.user.id).password, 'newpass123')
        self.post('/api/auth/logout')
        self.csrf = self.client.get('/api/auth/csrf').json['csrf_token']
        self.now.return_value += 61
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.post('/api/auth/login', {'email': 'alice@example.test', 'password': 'newpass123'}).status_code, 200)

    def test_profile_empty_save_edit_and_logout_persistence(self):
        self.assertEqual(self.client.get('/api/user/profile').status_code, 401)
        self.authenticate()
        self.assertIsNone(self.client.get('/api/user/profile').json['profile'])
        data = dict(full_name='Alex Smith', display_name='Alex', phone='555-1234',
                    organization='UCM', major='Cybersecurity', bio='Student')
        self.assertEqual(self.post('/api/user/profile', data).status_code, 200)
        self.assertEqual(self.client.get('/api/user/profile').json['profile'], data)
        self.post('/api/auth/logout')
        self.csrf = self.client.get('/api/auth/csrf').json['csrf_token']
        self.assertEqual(self.client.get('/api/user/profile').status_code, 401)
        self.now.return_value += 61
        self.authenticate()
        self.assertEqual(self.client.get('/api/user/profile').json['profile'], data)
        data['bio'] = 'Updated'
        self.assertEqual(self.post('/api/user/profile', data).status_code, 200)
        self.assertEqual(self.client.get('/api/user/profile').json['profile'], data)
        self.assertEqual(UserProfile.query.count(), 1)

    def test_profile_isolation_and_validation(self):
        self.authenticate()
        self.assertEqual(self.post('/api/user/profile', {'bio': 'Private'}).status_code, 200)
        self.assertEqual(self.post('/api/user/profile', {'user_id': 2}).status_code, 400)
        self.assertEqual(self.post('/api/user/profile', {'bio': 'x' * 1001}).status_code, 400)
        self.assertEqual(self.post('/api/user/profile', {'phone': 123}).status_code, 400)
        self.assertEqual(self.client.post('/api/user/profile', json={'bio': 'Bad'}).status_code, 403)
        self.post('/api/auth/logout')
        self.csrf = self.client.get('/api/auth/csrf').json['csrf_token']
        self.post('/api/auth/login', {'email': 'bob@example.test', 'password': 'testpass123'})
        self.post('/api/auth/verify-otp', {'code': self.mail[-1][1]})
        self.assertIsNone(self.client.get('/api/user/profile').json['profile'])
        self.post('/api/user/profile', {'bio': 'Bob'})
        self.assertEqual(self.client.get('/api/user/profile').json['profile']['bio'], 'Bob')
        self.assertEqual(db.session.get(UserProfile, self.user.id).bio, 'Private')
        self.assertEqual(UserProfile.query.count(), 2)

    def test_password_is_not_an_authenticated_session(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)
        self.assertEqual(self.client.get('/api/dashboard').status_code, 401)
        row = OtpChallenge.query.one()
        self.assertRegex(self.mail[-1][1], r'^\d{6}$')
        self.assertEqual(row.expires_at - self.now.return_value, 300)
        self.assertNotIn(self.mail[-1][1], row.code_hash)
        self.assertEqual(len(row.code_hash), 64)

    def test_wrong_password_and_unknown_email_are_generic(self):
        wrong = self.post('/api/auth/login', {'email': 'alice@example.test', 'password': 'wrong'})
        unknown = self.post('/api/auth/login', {'email': 'missing@example.test', 'password': 'wrong'})
        self.assertEqual((wrong.status_code, wrong.json), (unknown.status_code, unknown.json))
        self.assertEqual(self.mail, [])

    def test_valid_otp_cookie_rotation_refresh_and_replay(self):
        old_cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        self.login()
        pending_cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        self.assertNotEqual(old_cookie, pending_cookie)
        code = self.mail[-1][1]
        verified = self.post('/api/auth/verify-otp', {'code': code})
        self.assertEqual(verified.status_code, 200)
        auth_cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        self.assertNotEqual(pending_cookie, auth_cookie)
        self.assertNotIn('alice', auth_cookie)
        self.assertEqual(self.client.get('/api/auth/me').json['user']['username'], 'alice')
        self.assertEqual(self.client.get('/api/dashboard?chat_user=bob').status_code, 200)
        self.assertEqual(self.post('/api/auth/verify-otp', {'code': code}).status_code, 400)
        attacker = app.test_client()
        attacker.set_cookie(app.config['SESSION_COOKIE_NAME'], pending_cookie)
        self.assertEqual(attacker.get('/api/dashboard').status_code, 401)

    def test_invalid_and_expired_otp(self):
        self.login()
        self.assertEqual(self.post('/api/auth/verify-otp', {'code': 'abcdef'}).status_code, 400)
        self.now.return_value += 300
        self.assertEqual(self.post('/api/auth/verify-otp', {'code': self.mail[-1][1]}).status_code, 400)
        self.assertEqual(self.client.get('/api/dashboard').status_code, 401)

    def test_exactly_five_attempts_and_malformed_input_counts(self):
        self.login()
        for _ in range(5):
            self.assertEqual(self.post('/api/auth/verify-otp', {'code': []}).status_code, 400)
        self.assertEqual(OtpChallenge.query.one().attempts, 5)
        self.assertEqual(self.post('/api/auth/verify-otp', {'code': self.mail[-1][1]}).status_code, 400)

    def test_resend_cooldown_invalidates_old_code(self):
        self.login()
        old_code = self.mail[-1][1]
        self.assertEqual(self.post('/api/auth/resend-otp').status_code, 429)
        self.now.return_value += 59
        self.assertEqual(self.post('/api/auth/resend-otp').status_code, 429)
        self.now.return_value += 1
        self.assertEqual(self.post('/api/auth/resend-otp').status_code, 200)
        self.assertEqual(len(self.mail), 2)
        # Hash replacement invalidates prior code; random collision is avoided
        # by patching the generator in the separate resend test below.
        if old_code != self.mail[-1][1]:
            self.assertEqual(self.post('/api/auth/verify-otp', {'code': old_code}).status_code, 400)
        self.assertEqual(self.post('/api/auth/verify-otp', {'code': self.mail[-1][1]}).status_code, 200)

    def test_login_cannot_bypass_account_cooldown(self):
        self.login()
        self.assertEqual(self.login().status_code, 429)
        self.assertEqual(len(self.mail), 1)

    def test_login_rate_limit_is_shared_across_sessions(self):
        for _ in range(10):
            self.assertEqual(self.post('/api/auth/login', {'email': 'alice@example.test', 'password': 'bad'}).status_code, 401)
        other = app.test_client()
        csrf = other.get('/api/auth/csrf').json['csrf_token']
        response = self.post('/api/auth/login', {'email': 'alice@example.test', 'password': 'bad'}, other, csrf)
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response.headers)

    def test_otp_verification_rate_limit(self):
        self.login()
        for _ in range(20):
            self.assertEqual(self.post('/api/auth/verify-otp', {'code': ''}).status_code, 400)
        self.assertEqual(self.post('/api/auth/verify-otp', {'code': ''}).status_code, 429)

    def test_otp_request_rate_limit(self):
        self.login()
        for _ in range(4):
            self.now.return_value += 60
            self.assertEqual(self.post('/api/auth/resend-otp').status_code, 200)
        self.now.return_value += 60
        self.assertEqual(self.post('/api/auth/resend-otp').status_code, 429)

    def test_csrf_and_exact_cors_origin(self):
        self.assertEqual(self.client.post('/api/auth/login', json={}).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/login', json={}, headers={'X-CSRF-Token': 'é'}).status_code, 403)
        evil = self.client.get('/api/auth/me', headers={'Origin': 'https://evil.example'})
        self.assertEqual(evil.status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', evil.headers)
        good = self.client.options('/api/auth/login', headers={'Origin': app.config['FRONTEND_URL']})
        self.assertEqual(good.status_code, 204)
        self.assertEqual(good.headers['Access-Control-Allow-Origin'], app.config['FRONTEND_URL'])
        self.assertEqual(good.headers['Access-Control-Allow-Credentials'], 'true')

    def test_all_private_endpoints_reject_anonymous_and_pending(self):
        for pending in (False, True):
            if pending:
                self.login()
            for path in ('/api/dashboard', '/messages/bob', '/conversation_key/bob', '/public_key/bob', '/uploads/file.pdf', '/debug-messages', '/ws'):
                self.assertEqual(self.client.get(path).status_code, 401, path)
            for path in ('/send', '/upload_file', '/upload_image', '/upload_audio'):
                self.assertEqual(self.post(path).status_code, 401, path)

    def test_logout_revokes_old_cookie(self):
        self.authenticate()
        cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        with patch.dict(app.config, {'CLOSE_USER_CONNECTION': MagicMock()}):
            self.assertEqual(self.post('/api/auth/logout').status_code, 200)
            app.config['CLOSE_USER_CONNECTION'].assert_called_once_with('alice')
        attacker = app.test_client()
        attacker.set_cookie(app.config['SESSION_COOKIE_NAME'], cookie)
        self.assertEqual(attacker.get('/api/dashboard').status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)

    def test_session_expiry(self):
        self.authenticate()
        self.now.return_value += app.config['SESSION_TTL_SECONDS']
        self.assertEqual(self.client.get('/api/dashboard').status_code, 401)

    def test_production_cookie_flags(self):
        app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='None')
        client = app.test_client()
        response = client.get('/api/auth/csrf', base_url='https://localhost')
        cookie = response.headers['Set-Cookie']
        for flag in ('HttpOnly', 'Secure', 'SameSite=None', 'Path=/'):
            self.assertIn(flag, cookie)

    def test_registration_and_duplicate_are_indistinguishable(self):
        data = {'username': 'carol', 'email': 'carol@example.test', 'password': 'testpass123'}
        first = self.post('/api/auth/register', data)
        second = self.post('/api/auth/register', data)
        self.assertEqual((first.status_code, first.json), (second.status_code, second.json))
        self.assertTrue(User.query.filter_by(username='carol').one().password.startswith('scrypt:'))

    def test_legacy_password_upgrade_and_email_link_command(self):
        salt = secrets.token_bytes(16)
        self.user.password = salt.hex() + ':' + hashlib.pbkdf2_hmac('sha256', b'testpass123', salt, 200000).hex()
        self.user.email = None
        db.session.commit()
        result = app.test_cli_runner().invoke(args=['link-email', 'alice', 'alice@example.test'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.login().status_code, 200)
        self.assertTrue(db.session.get(User, self.user.id).password.startswith('scrypt:'))

    def test_smtp_sender_uses_tls_and_does_not_return_otp(self):
        app.config.pop('OTP_SENDER')
        with patch.dict(os.environ, {'SMTP_HOST': 'smtp.example.test', 'SMTP_FROM': 'noreply@example.test', 'SMTP_PORT': '587'}), patch('modules.authentication.smtplib.SMTP') as transport:
            self.assertIsNone(send_otp('alice@example.test', '123456'))
            smtp = transport.return_value.__enter__.return_value
            smtp.starttls.assert_called_once()
            import ssl
            self.assertEqual(smtp.starttls.call_args.kwargs['context'].verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(smtp.starttls.call_args.kwargs['context'].check_hostname)
            self.assertIn('123456', smtp.send_message.call_args.args[0].get_content())

    def test_email_failure_never_authenticates(self):
        app.config['OTP_SENDER'] = MagicMock(side_effect=RuntimeError('SMTP failed'))
        self.assertEqual(self.login().status_code, 503)
        self.assertEqual(OtpChallenge.query.count(), 0)
        self.assertEqual(self.client.get('/api/dashboard').status_code, 401)

    def test_malformed_json_payloads_do_not_crash(self):
        for path in ('login', 'register', 'verify-otp', 'resend-otp'):
            response = self.client.post('/api/auth/' + path, json=['invalid'], headers={'X-CSRF-Token': self.csrf})
            self.assertLess(response.status_code, 500)

    def test_successful_uploads_stay_private(self):
        self.authenticate()
        upload_folder = Path(temporary.name) / 'uploads'
        upload_folder.mkdir(exist_ok=True)
        for endpoint, field, filename in (
            ('upload_file', 'file', 'test.pdf'), ('upload_image', 'image', 'test.png'),
            ('upload_audio', 'audio', 'test.webm')):
            with patch('app.UPLOAD_FOLDER', str(upload_folder)):
                response = self.client.post('/' + endpoint,
                    data={'receiver': 'bob', field: (io.BytesIO(b'test fixture'), filename)},
                    headers={'X-CSRF-Token': self.csrf})
                self.assertEqual(response.status_code, 201, response.json)
                from urllib.parse import urlparse
                path = urlparse(response.json['url']).path
                downloaded = self.client.get(path)
                self.assertEqual(downloaded.status_code, 200)
                downloaded.close()
                self.assertEqual(app.test_client().get(path).status_code, 401)

    def test_production_config_rejects_local_state(self):
        from flask import Flask
        from modules.settings import configure
        with patch.dict(os.environ, {
            'NODE_ENV': 'production', 'SESSION_SECRET': secrets.token_hex(32),
            'DATABASE_URL': 'sqlite:///temporary.db'
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'PostgreSQL'):
                configure(Flask('configuration-test'))

    def test_websocket_rejects_claimed_identity(self):
        self.authenticate()
        cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        ws = MagicMock()
        ws.receive.return_value = 'bob'
        with app.test_request_context('/ws', headers={'Cookie': app.config['SESSION_COOKIE_NAME'] + '=' + cookie}):
            app.view_functions['websocket'].__wrapped__(ws)
        ws.close.assert_called_once()
        ws.send.assert_not_called()

    def test_expired_websocket_cannot_receive_forwarded_messages(self):
        from app import live_connection, connections, connection_sessions
        from modules.authentication import token_hash
        self.authenticate()
        cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        ws = MagicMock()
        with patch.dict(connections, {'alice': ws}, clear=True), patch.dict(connection_sessions, {'alice': token_hash(cookie)}, clear=True):
            self.assertIs(live_connection('alice'), ws)
            self.now.return_value += app.config['SESSION_TTL_SECONDS']
            self.assertIsNone(live_connection('alice'))
            ws.close.assert_called_once()

    def test_concurrent_otp_verification_issues_only_one_session(self):
        from concurrent.futures import ThreadPoolExecutor
        self.login()
        cookie = self.client.get_cookie(app.config['SESSION_COOKIE_NAME']).value
        code, csrf = self.mail[-1][1], self.csrf
        def verify():
            client = app.test_client()
            client.set_cookie(app.config['SESSION_COOKIE_NAME'], cookie)
            return client.post('/api/auth/verify-otp', json={'code': code},
                               headers={'X-CSRF-Token': csrf}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: verify(), range(2)))
        self.assertEqual(results.count(200), 1, results)
        self.assertTrue(all(status in (200, 400, 403) for status in results), results)
        self.assertIsNotNone(OtpChallenge.query.one().used_at)

    def test_authenticated_nonparticipant_cannot_download_upload(self):
        self.authenticate()
        db.session.add(Message(sender='bob', receiver='carol', file_name='private.pdf', msg_type='file'))
        db.session.commit()
        self.assertEqual(self.client.get('/uploads/private.pdf').status_code, 403)


def tearDownModule():
    with app.app_context():
        db.session.remove()
        db.engine.dispose()
    temporary.cleanup()
