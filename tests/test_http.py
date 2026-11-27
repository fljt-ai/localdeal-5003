"""Real loopback HTTP checks using isolated databases and browser-like cookies."""
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
import http.client
from http.cookiejar import CookieJar
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.auth import DEMO_PASSWORD, token_hash, verify_password
from backend.database import initialize_database
from backend.server import MAX_BODY, create_server
from database import operations


class Client:
    def __init__(self, base):
        self.base = base
        self.cookies = CookieJar()
        # Loopback tests must never inherit a machine's external proxy settings.
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(self.cookies))
        self.csrf = None

    def request(self, method, path, payload=None, headers=None, raw=None):
        outgoing = {}
        data = None
        if method not in ('GET', 'HEAD', 'OPTIONS'):
            outgoing = {'Content-Type': 'application/json', 'Origin': self.base,
                        'X-LocalDeal-Request': '1'}
            if self.csrf:
                outgoing['X-CSRF-Token'] = self.csrf
            data = raw if raw is not None else json.dumps(payload if payload is not None else {}).encode('utf-8')
        for key, value in (headers or {}).items():
            if value is None:
                outgoing.pop(key, None)
            else:
                outgoing[key] = value
        request = Request(self.base + path, data=data, headers=outgoing, method=method)
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            content_type = response.headers.get('Content-Type', '').split(';')[0]
            value = json.loads(body) if body and content_type == 'application/json' else body
            return response.status, value, response.headers

    def login(self, email='alex@example.com', password=DEMO_PASSWORD):
        result = self.request('POST', '/api/auth/login', {'email': email, 'password': password})
        if result[0] == 200:
            self.csrf = result[1]['data']['csrfToken']
        return result

    def register(self, name, email, password=DEMO_PASSWORD):
        result = self.request('POST', '/api/auth/register', {'name': name, 'email': email, 'password': password})
        if result[0] == 201:
            self.csrf = result[1]['data']['csrfToken']
        return result

    def token(self):
        return next(cookie.value for cookie in self.cookies if cookie.name == 'localdeal_session')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Hash the nine fictional demo credentials once, then copy this isolated
        # template. The supplied database is never opened or modified by tests.
        cls.template_directory = tempfile.TemporaryDirectory(prefix='localdeal-http-template-')
        cls.template = Path(cls.template_directory.name) / 'template.db'
        initialize_database(cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.template_directory.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='localdeal-http-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'test.db'
        shutil.copyfile(self.template, self.path)
        self.server = None
        self.start_server()
        self.addCleanup(self.stop_server)
        self.client = Client(self.base)

    def start_server(self):
        self.server = create_server(self.path, port=0, quiet=True)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join(timeout=5)
            self.server.server_close()
            self.server = None

    def db(self):
        return operations.connect(self.path)

    def sql(self, statement, parameters=()):
        connection = self.db()
        try:
            return connection.execute(statement, parameters).fetchall()
        finally:
            connection.close()

    def data(self, result, expected=200):
        status, payload, headers = result
        self.assertEqual(status, expected, payload)
        self.assertEqual(headers.get('Content-Type', '').split(';')[0], 'application/json')
        self.assertEqual(headers.get('Cache-Control'), 'no-store')
        self.assertIn('data', payload)
        return payload['data']

    def error(self, result, expected, code=None):
        status, payload, headers = result
        self.assertEqual(status, expected, payload)
        self.assertEqual(headers.get('Content-Type', '').split(';')[0], 'application/json')
        self.assertIn('error', payload)
        if code:
            self.assertEqual(payload['error']['code'], code)
        self.assertNotIn('Traceback', json.dumps(payload))
        return payload['error']

    def authenticated(self, email='alex@example.com'):
        client = Client(self.base)
        self.data(client.login(email))
        return client

    def page(self, result):
        page = self.data(result)
        for key in ('items', 'total', 'limit', 'offset', 'hasMore'):
            self.assertIn(key, page)
        self.assertIsInstance(page['items'], list)
        self.assertIsInstance(page['hasMore'], bool)
        self.assertLessEqual(len(page['items']), page['limit'])
        self.assertEqual(len(page['items']), min(page['limit'], max(0, page['total'] - page['offset'])))
        self.assertEqual(page['hasMore'], page['offset'] + len(page['items']) < page['total'])
        return page

    def pages(self, client, route, limit=7):
        items, total, offset = [], None, 0
        while True:
            separator = '&' if '?' in route else '?'
            page = self.page(client.request('GET', route + separator + urlencode({'limit': limit, 'offset': offset})))
            if total is None:
                total = page['total']
            self.assertEqual(page['total'], total)
            items.extend(page['items'])
            if not page['hasMore']:
                break
            offset += limit
        self.assertEqual(len(items), total)
        self.assertEqual(len({item['id'] for item in items}), total)
        return items

    def paging_fixture(self):
        """Enough temporary rows to expose page boundaries, ties and ownership."""
        now = int(time.time())
        today = datetime.now(operations.HK).date()
        future = (today + timedelta(days=45)).isoformat()
        expired = (today - timedelta(days=1)).isoformat()
        purchased = int(datetime.combine(today - timedelta(days=3),
                                         datetime.min.time(), operations.HK).timestamp())
        connection = self.db()
        try:
            with operations.transaction(connection):
                connection.execute("INSERT INTO tags(tag) VALUES('paging-probe')")
                for index in range(30):
                    suffix = f'{index:02d}'
                    store_id, user_id = 'z-page-store-' + suffix, 'page-user-' + suffix
                    name = 'Pagination 100%_Kitchen' if index == 0 else 'Pagination Store ' + suffix
                    connection.execute(
                        'INSERT INTO stores(store_id,merchant_id,category_id,district_id,name,english_name,'
                        'address,hours,description,price_per_person_cents,image_path) '
                        "SELECT ?,merchant_id,category_id,district_id,?,?,'Test address',hours,description,?,image_path "
                        "FROM stores WHERE store_id='s1'",
                        (store_id, name, 'Pagination Store ' + suffix, 10000 + (index // 5) * 100))
                    connection.execute('INSERT INTO users(user_id,email,display_name,created_at) VALUES(?,?,?,?)',
                                       (user_id, user_id + '@example.com', 'Paging Author ' + suffix, now - 2000))
                    connection.execute('INSERT INTO reviews(review_id,store_id,user_id,rating,comment,created_at,updated_at) '
                                       'VALUES(?,?,?,?,?,?,?)',
                                       ('page-review-' + suffix, 's1', user_id, index % 5 + 1,
                                        'Paging review ' + suffix, now - 1000, now - 1000))
                    connection.execute('INSERT INTO reviews(review_id,store_id,user_id,rating,comment,created_at,updated_at) '
                                       'VALUES(?,?,?,?,?,?,?)',
                                       ('own-page-review-' + suffix, store_id, 'u-demo', index % 5 + 1,
                                        'My paging review ' + suffix, now - 1000, now - 1000))
                    connection.execute('INSERT INTO favorites(user_id,store_id,created_at) VALUES(?,?,?)',
                                       ('u-demo', store_id, now - 1000))
                    connection.execute('INSERT INTO coupons(coupon_id,store_id,title,description,original_price_cents,'
                                       'price_cents,total_stock,available_stock,expires_on) VALUES(?,?,?,?,?,?,?,?,?)',
                                       ('page-coupon-' + suffix, store_id, 'Pagination Coupon ' + suffix,
                                        'Temporary paging offer', 20000, 10000 + index, 5, 5, future))
                    if index < 2:
                        connection.execute('INSERT INTO store_tags VALUES(?,?,1)', (store_id, 'paging-probe'))
                    if index == 2:
                        connection.execute('INSERT INTO menu_items(menu_item_id,store_id,name,description,price_cents,position) '
                                           'VALUES(?,?,?,?,?,1)', ('page-menu', store_id, 'Paging Noodles', 'Test menu item', 1000))
                    coupon_id = ('c1', 'c3', 'c5')[index % 3]
                    owner = 'u-demo' if index % 2 == 0 else 'u-amy'
                    expiry = expired if index % 3 == 2 else future
                    order_id = 'page-order-' + suffix
                    connection.execute(
                        'INSERT INTO orders(order_id,user_id,coupon_id,title_snapshot,price_paid_cents,'
                        'original_price_cents_snapshot,expires_on_snapshot,redeem_code,idempotency_key,purchased_at) '
                        'SELECT ?,?,coupon_id,title,price_cents,original_price_cents,?,?,?,? '
                        'FROM coupons WHERE coupon_id=?',
                        (order_id, owner, expiry, 'LD-PAGE-ORDER-' + suffix, order_id, purchased, coupon_id))
                    if index % 3 == 1:
                        connection.execute('INSERT INTO redemptions VALUES(?,?,?)',
                                           (order_id, 'u-dumpling', purchased + 1))
                # Two offers at one store must still yield one store card/count.
                connection.execute('INSERT INTO coupons(coupon_id,store_id,title,description,original_price_cents,'
                                   'price_cents,total_stock,available_stock,expires_on) VALUES(?,?,?,?,?,?,?,?,?)',
                                   ('page-second-offer', 'z-page-store-00', 'Second Paging Offer',
                                    'Temporary second offer', 20000, 9000, 5, 5, future))
                connection.execute(
                    'INSERT INTO stores(store_id,merchant_id,category_id,district_id,name,english_name,address,hours,'
                    'description,price_per_person_cents,image_path,is_active) '
                    "SELECT 'z-page-inactive',merchant_id,category_id,district_id,'Inactive Pagination','Inactive Pagination',"
                    "address,hours,description,price_per_person_cents,image_path,0 FROM stores WHERE store_id='s1'")
        finally:
            connection.close()

    def test_public_state_and_private_routes_do_not_expose_customers_or_credentials(self):
        state = self.data(self.client.request('GET', '/api/state'))
        self.assertIsNone(state['user'])
        self.assertIsNone(state['csrfToken'])
        for key in ('stores', 'coupons', 'reviews', 'orders', 'favorites', 'merchantOrders'):
            self.assertEqual(state[key], [])
        self.assertEqual(state['summary'], {'favorites': 0, 'reviews': 0,
                                          'orders': {'all': 0, 'unused': 0, 'redeemed': 0, 'expired': 0}})
        self.assertEqual(len(state['categories']), 3)
        self.assertEqual(len(state['districts']), 3)
        self.assertEqual(self.page(self.client.request('GET', '/api/stores'))['total'], 6)
        self.assertEqual(self.page(self.client.request('GET', '/api/coupons'))['total'], 6)
        serialized = json.dumps(state)
        for private_value in ('password_hash', 'pbkdf2_sha256', DEMO_PASSWORD,
                              'token_hash', 'alex@example.com', 'LD-HARBOR01'):
            self.assertNotIn(private_value, serialized)
        for route in ('/api/orders', '/api/orders/o-demo-1', '/api/export',
                      '/api/users/me/reviews', '/api/users/me/favorites', '/api/merchant/orders'):
            with self.subTest(route=route):
                self.error(self.client.request('GET', route), 401, 'UNAUTHENTICATED')
        self.error(self.client.request('POST', '/api/orders', {'couponId': 'c1', 'idempotencyKey': 'guest'}), 401)

    def test_login_credentials_cookie_flags_and_hashed_session_storage(self):
        self.error(self.client.login(password='wrong-password-2026'), 401, 'INVALID_CREDENTIALS')
        self.error(self.client.login('unknown@example.com'), 401, 'INVALID_CREDENTIALS')
        result = self.client.login(' ALEX@EXAMPLE.COM ')
        logged_in = self.data(result)
        self.assertEqual(logged_in['user']['id'], 'u-demo')
        self.assertEqual(logged_in['user']['merchantStoreIds'], [])
        cookie = SimpleCookie()
        cookie.load(result[2]['Set-Cookie'])
        credential = cookie['localdeal_session']
        self.assertTrue(credential['httponly'])
        self.assertEqual(credential['samesite'], 'Strict')
        self.assertEqual(credential['path'], '/')
        self.assertEqual(credential['max-age'], '86400')
        token = self.client.token()
        stored = self.sql('SELECT * FROM sessions')[0]
        self.assertEqual(stored['token_hash'], token_hash(token))
        self.assertNotEqual(stored['token_hash'], token)
        self.assertEqual(stored['user_id'], 'u-demo')
        encoded = self.sql("SELECT password_hash FROM users WHERE user_id='u-demo'")[0][0]
        self.assertNotEqual(encoded, DEMO_PASSWORD)
        self.assertTrue(verify_password(DEMO_PASSWORD, encoded))
        self.assertEqual(self.data(self.client.request('GET', '/api/auth/session'))['csrfToken'], self.client.csrf)

    def test_registration_validates_fields_duplicates_and_preserves_sql_strings_as_data(self):
        name = "Robert'); DROP TABLE users; --"
        result = self.client.register(name, ' New.Customer@Example.com ')
        user = self.data(result, 201)['user']
        self.assertEqual(user['name'], name)
        self.assertEqual(user['email'], 'new.customer@example.com')
        self.assertEqual(len(self.sql('SELECT user_id FROM users')), 10)
        self.assertEqual(self.data(self.client.request('GET', '/api/state'))['orders'], [])
        other = Client(self.base)
        self.error(other.register('Other', 'NEW.CUSTOMER@EXAMPLE.COM'), 409, 'EMAIL_EXISTS')
        self.error(other.register('Other', 'invalid'), 400, 'INVALID_EMAIL')
        self.error(other.register('Other', 'short@example.com', 'short'), 400, 'INVALID_PASSWORD')
        self.error(other.request('POST', '/api/auth/register',
                                {'name': 'Other', 'email': 'role@example.com',
                                 'password': DEMO_PASSWORD, 'role': 'owner'}), 400, 'INVALID_FIELDS')
        self.error(other.login("' OR 1=1 --@example.com"), 400, 'INVALID_EMAIL')
        self.assertEqual(self.data(other.request('GET', '/api/state'))['user'], None)

    def test_clients_cannot_forge_user_identity_roles_or_private_order_lookup(self):
        alex = self.authenticated()
        amy = self.authenticated('amy@example.com')
        for route, payload in [
            ('/api/orders', {'couponId': 'c2', 'idempotencyKey': 'forged', 'userId': 'u-amy'}),
            ('/api/favorites/toggle', {'storeId': 's2', 'userId': 'u-amy'}),
            ('/api/stores/s2/reviews', {'rating': 5, 'comment': 'Forged author', 'userId': 'u-amy'}),
        ]:
            with self.subTest(route=route):
                self.error(alex.request('POST', route, payload), 400, 'INVALID_FIELDS')
        self.error(alex.request('PATCH', '/api/users/me', {'name': 'Owner', 'userId': 'u-harbor'}), 400, 'INVALID_FIELDS')
        self.error(amy.request('GET', '/api/orders/o-demo-1'), 404, 'ORDER_NOT_FOUND')
        self.assertEqual(self.page(amy.request('GET', '/api/orders'))['items'], [])
        self.assertEqual(self.data(alex.request('GET', '/api/state'))['user']['id'], 'u-demo')

    def test_profile_favorites_and_export_are_scoped_to_the_session(self):
        alex = self.authenticated()
        amy = self.authenticated('amy@example.com')
        self.data(alex.request('PATCH', '/api/users/me', {'name': '<b>Updated Alex</b>'}))
        self.assertTrue(self.data(alex.request('POST', '/api/favorites/toggle', {'storeId': 's2'}))['saved'])
        state = self.data(alex.request('GET', '/api/state'))
        self.assertEqual(state['user']['name'], '<b>Updated Alex</b>')
        self.assertEqual(state['summary']['favorites'], 3)
        favorites = self.page(alex.request('GET', '/api/users/me/favorites'))['items']
        self.assertIn('s2', [store['id'] for store in favorites])
        mine = self.page(alex.request('GET', '/api/users/me/reviews'))['items']
        self.assertEqual(len(mine), 2)
        self.assertTrue(all(r['userName'] == '<b>Updated Alex</b>' for r in mine))
        other = self.data(amy.request('GET', '/api/state'))
        self.assertEqual(other['favorites'], [])
        self.assertEqual(other['orders'], [])
        self.assertEqual(other['summary']['favorites'], 0)
        self.assertEqual(other['summary']['orders']['all'], 0)
        exported = self.data(alex.request('GET', '/api/export'))
        self.assertEqual(exported['metadata']['scope'], 'current-user')
        self.assertTrue(all(r['userId'] == 'u-demo' for r in exported['reviews']))
        self.assertTrue(all(o['userId'] == 'u-demo' for o in exported['orders']))
        self.assertEqual(len(exported['orders']), 3)
        self.assertEqual(len(exported['reviews']), 2)
        self.assertNotIn('csrfToken', exported)
        self.assertNotIn('merchantOrders', exported)
        self.assertNotIn('password', json.dumps(exported))

    def test_reviews_owner_crud_duplicate_rule_and_public_rating_updates(self):
        alex = self.authenticated()
        amy = self.authenticated('amy@example.com')
        review = self.data(alex.request('POST', '/api/stores/s2/reviews',
                                       {'rating': 1, 'comment': "SQL text '); DROP TABLE orders; --"}), 201)
        self.assertEqual(review['userId'], 'u-demo')
        self.error(alex.request('POST', '/api/stores/s2/reviews', {'rating': 5, 'comment': 'Another review'}), 409, 'REVIEW_EXISTS')
        path = '/api/reviews/' + review['id']
        self.error(amy.request('PATCH', path, {'rating': 5, 'comment': 'Someone else'}), 403, 'FORBIDDEN')
        self.error(amy.request('DELETE', path, {}), 403, 'FORBIDDEN')
        edited = self.data(alex.request('PATCH', path, {'rating': 5, 'comment': 'Updated experience'}))
        self.assertEqual(edited['rating'], 5)
        store = self.data(self.client.request('GET', '/api/stores/s2'))
        self.assertEqual(store['reviewCount'], 6)
        expected = self.sql("SELECT round(avg(rating),1) FROM reviews WHERE store_id='s2'")[0][0]
        self.assertEqual(store['averageRating'], expected)
        self.assertTrue(self.data(alex.request('DELETE', path, {}))['deleted'])
        self.assertEqual(self.data(self.client.request('GET', '/api/stores/s2'))['reviewCount'], 5)
        self.error(alex.request('DELETE', path, {}), 404, 'REVIEW_NOT_FOUND')
        self.error(alex.request('POST', '/api/stores/s2/reviews', {'rating': True, 'comment': 'Bad rating'}), 400, 'INVALID_RATING')

    def test_purchase_snapshots_inventory_idempotency_and_profile_separation(self):
        alex = self.authenticated()
        amy = self.authenticated('amy@example.com')
        stock = self.sql("SELECT available_stock FROM coupons WHERE coupon_id='c2'")[0][0]
        order = self.data(alex.request('POST', '/api/orders', {'couponId': 'c2', 'idempotencyKey': 'http-purchase'}), 201)
        self.assertEqual(order['userId'], 'u-demo')
        self.assertEqual(self.sql("SELECT available_stock FROM coupons WHERE coupon_id='c2'")[0][0], stock - 1)
        self.sql("UPDATE coupons SET available_stock=0,title='Changed',price_cents=1,expires_on='2000-01-01' WHERE coupon_id='c2'")
        retried = self.data(alex.request('POST', '/api/orders', {'couponId': 'c2', 'idempotencyKey': 'http-purchase'}))
        self.assertEqual(retried, order)
        self.error(alex.request('POST', '/api/orders', {'couponId': 'c3', 'idempotencyKey': 'http-purchase'}), 409, 'RETRY_CONFLICT')
        self.assertEqual(self.page(amy.request('GET', '/api/orders'))['items'], [])
        separate = self.data(amy.request('POST', '/api/orders', {'couponId': 'c3', 'idempotencyKey': 'http-purchase'}), 201)
        self.assertEqual(separate['userId'], 'u-amy')
        self.assertNotEqual(separate['id'], order['id'])
        self.error(amy.request('GET', '/api/orders/' + order['id']), 404, 'ORDER_NOT_FOUND')

    def test_purchase_soldout_expired_missing_offer_and_injected_failure_are_atomic(self):
        alex = self.authenticated()
        count = self.sql('SELECT count(*) FROM orders')[0][0]
        self.sql("UPDATE coupons SET available_stock=0 WHERE coupon_id='c2'")
        self.error(alex.request('POST', '/api/orders', {'couponId': 'c2', 'idempotencyKey': 'soldout'}), 409, 'SOLD_OUT')
        self.sql("UPDATE coupons SET expires_on='2000-01-01' WHERE coupon_id='c3'")
        self.error(alex.request('POST', '/api/orders', {'couponId': 'c3', 'idempotencyKey': 'expired'}), 409, 'EXPIRED')
        self.error(alex.request('POST', '/api/orders', {'couponId': 'missing', 'idempotencyKey': 'missing'}), 404, 'COUPON_NOT_FOUND')
        self.sql("CREATE TRIGGER http_insert_failure BEFORE INSERT ON orders WHEN NEW.idempotency_key='failed-insert' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        stock = self.sql("SELECT available_stock FROM coupons WHERE coupon_id='c6'")[0][0]
        failed = alex.request('POST', '/api/orders', {'couponId': 'c6', 'idempotencyKey': 'failed-insert'})
        self.assertIn(failed[0], (409, 500))
        self.assertEqual(self.sql("SELECT available_stock FROM coupons WHERE coupon_id='c6'")[0][0], stock)
        self.assertEqual(self.sql('SELECT count(*) FROM orders')[0][0], count)

    def test_staff_scope_wrong_branch_expired_repeat_and_valid_redemption(self):
        customer = self.authenticated()
        harbor = self.authenticated('harbor.owner@example.com')
        coffee = self.authenticated('coffee.owner@example.com')
        self.error(customer.request('POST', '/api/orders/redeem', {'code': 'LD-HARBOR01', 'storeId': 's1'}), 403, 'FORBIDDEN')
        self.error(coffee.request('POST', '/api/orders/redeem', {'code': 'LD-HARBOR01', 'storeId': 's1'}), 403, 'FORBIDDEN')
        self.error(harbor.request('POST', '/api/orders/redeem', {'code': 'LD-HARBOR01', 'storeId': 's2'}), 409, 'WRONG_STORE')
        self.error(coffee.request('POST', '/api/orders/redeem', {'code': 'LD-COFFEE03', 'storeId': 's5'}), 409, 'EXPIRED')
        self.sql("UPDATE store_staff SET is_active=0 WHERE store_id='s1' AND user_id='u-harbor'")
        self.error(harbor.request('POST', '/api/orders/redeem', {'code': 'LD-HARBOR01', 'storeId': 's1'}), 403, 'FORBIDDEN')
        self.sql("UPDATE store_staff SET is_active=1 WHERE store_id='s1' AND user_id='u-harbor'")
        redeemed = self.data(harbor.request('POST', '/api/orders/redeem', {'code': ' ld-harbor01 ', 'storeId': 's1'}))
        self.assertEqual(redeemed['status'], 'redeemed')
        self.error(harbor.request('POST', '/api/orders/redeem', {'code': 'LD-HARBOR01', 'storeId': 's1'}), 409, 'ALREADY_REDEEMED')
        self.assertEqual(self.data(customer.request('GET', '/api/orders/o-demo-1'))['status'], 'redeemed')
        merchant = self.data(harbor.request('GET', '/api/state'))
        self.assertEqual(merchant['user']['merchantStoreIds'], ['s1', 's2'])
        self.assertEqual(merchant['orders'], [])
        self.assertEqual(merchant['merchantOrders'], [])
        ledger = self.page(harbor.request('GET', '/api/merchant/orders'))['items']
        self.assertTrue(all(o['storeId'] in ('s1', 's2') for o in ledger))
        self.assertNotIn('LD-COFFEE03', json.dumps(ledger))

    def test_csrf_origin_host_and_application_header_are_required(self):
        alex = self.authenticated()
        payload = {'storeId': 's2'}
        self.error(alex.request('POST', '/api/favorites/toggle', payload, {'X-CSRF-Token': None}), 403, 'CSRF_FAILED')
        self.error(alex.request('POST', '/api/favorites/toggle', payload, {'X-CSRF-Token': 'wrong'}), 403, 'CSRF_FAILED')
        self.error(alex.request('POST', '/api/favorites/toggle', payload, {'Origin': 'https://external.example'}), 403, 'INVALID_ORIGIN')
        self.error(alex.request('POST', '/api/favorites/toggle', payload, {'X-LocalDeal-Request': None}), 403, 'REQUEST_HEADER_REQUIRED')
        self.error(alex.request('GET', '/api/state', headers={'Host': 'external.example'}), 403, 'INVALID_HOST')
        state = self.data(alex.request('GET', '/api/state'))
        self.assertEqual(state['summary']['favorites'], 2)
        self.assertTrue(self.data(alex.request('POST', '/api/favorites/toggle', payload))['saved'])

    def test_non_ascii_csrf_header_is_a_validation_error(self):
        alex = self.authenticated()
        self.error(alex.request('POST', '/api/favorites/toggle', {'storeId': 's2'},
                                {'X-CSRF-Token': '\u00e9'}), 403, 'CSRF_FAILED')
        self.assertEqual(self.data(alex.request('GET', '/api/state'))['summary']['favorites'], 2)

    def test_json_content_type_shape_duplicate_keys_and_body_limits(self):
        credentials = {'email': 'alex@example.com', 'password': DEMO_PASSWORD}
        self.error(self.client.request('POST', '/api/auth/login', credentials,
                                       {'Content-Type': 'application/x-www-form-urlencoded'}), 415, 'JSON_REQUIRED')
        for raw in [b'{', b'[]', b'null', b'\xff', b'{"email":"a","email":"b"}',
                    b'{"email":NaN,"password":"x"}']:
            with self.subTest(raw=raw):
                self.error(self.client.request('POST', '/api/auth/login', raw=raw), 400, 'INVALID_JSON')
        self.error(self.client.request('POST', '/api/auth/login', raw=b'x' * (MAX_BODY + 1)), 413, 'BODY_TOO_LARGE')
        self.error(self.client.request('POST', '/api/auth/login', credentials,
                                       {'Transfer-Encoding': 'chunked'}), 400, 'INVALID_BODY')
        self.data(self.client.login())

    def test_invalid_and_duplicate_content_lengths_do_not_block(self):
        for lengths, expected, code in [(['-1'], 400, 'INVALID_LENGTH'),
                                        (['bad'], 400, 'INVALID_LENGTH'),
                                        (['0', '0'], 411, 'LENGTH_REQUIRED'),
                                        ([], 411, 'LENGTH_REQUIRED')]:
            with self.subTest(lengths=lengths):
                connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
                try:
                    connection.putrequest('POST', '/api/auth/login')
                    connection.putheader('Content-Type', 'application/json')
                    connection.putheader('X-LocalDeal-Request', '1')
                    connection.putheader('Origin', self.base)
                    for length in lengths:
                        connection.putheader('Content-Length', length)
                    connection.endheaders()
                    response = connection.getresponse()
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, expected, payload)
                    self.assertEqual(payload['error']['code'], code)
                finally:
                    connection.close()
        self.assertEqual(self.data(self.client.request('GET', '/api/health'))['status'], 'ok')

    def test_logout_and_expired_session_cannot_be_replayed(self):
        alex = self.authenticated()
        old_token = alex.token()
        logout = alex.request('POST', '/api/auth/logout', {})
        self.assertTrue(self.data(logout)['loggedOut'])
        self.assertIn('Max-Age=0', logout[2]['Set-Cookie'])
        self.assertEqual(self.sql('SELECT token_hash FROM sessions WHERE token_hash=?', (token_hash(old_token),)), [])
        replay = Client(self.base)
        self.assertIsNone(self.data(replay.request('GET', '/api/state', headers={'Cookie': 'localdeal_session=' + old_token}))['user'])
        self.error(replay.request('POST', '/api/orders', {'couponId': 'c1', 'idempotencyKey': 'replay'},
                                  {'Cookie': 'localdeal_session=' + old_token, 'X-CSRF-Token': alex.csrf}), 401)
        self.data(alex.login())
        self.sql('UPDATE sessions SET created_at=?,expires_at=? WHERE token_hash=?',
                 (int(time.time()) - 100, int(time.time()) - 1, token_hash(alex.token())))
        self.assertIsNone(self.data(alex.request('GET', '/api/state'))['user'])
        self.error(alex.request('POST', '/api/favorites/toggle', {'storeId': 's2'}), 401)

    def test_forged_cookie_and_login_rotation_do_not_restore_prior_identity(self):
        forged = Client(self.base)
        self.assertIsNone(self.data(forged.request('GET', '/api/state', headers={'Cookie': 'localdeal_session=' + 'A' * 43}))['user'])
        alex = self.authenticated()
        prior = alex.token()
        self.data(alex.login('amy@example.com'))
        self.assertNotEqual(alex.token(), prior)
        self.assertEqual(self.data(alex.request('GET', '/api/state'))['user']['id'], 'u-amy')
        self.assertIsNone(self.data(forged.request('GET', '/api/state', headers={'Cookie': 'localdeal_session=' + prior}))['user'])

    def test_static_allowlist_blocks_database_code_config_and_encoded_traversal(self):
        root = self.client.request('GET', '/')
        self.assertEqual(root[0], 200)
        self.assertIn(b'LocalDeal', root[1])
        for allowed in ('/styles.css', '/src/app.js', '/src/http-api.js', '/src/i18n.js', '/assets/favicon.svg'):
            with self.subTest(allowed=allowed):
                self.assertEqual(self.client.request('GET', allowed)[0], 200)
        blocked = ['/database/localdeal.db', '/database/localdeal.db-wal', '/database/localdeal.db-shm',
                   '/database/schema.sql', '/backend/server.py', '/backend/auth.py', '/run.py', '/.env',
                   '/README.md', '/src/mock-api.js', '/../database/localdeal.db',
                   '/%2e%2e/database/localdeal.db', '/assets/%2e%2e/%2e%2e/database/localdeal.db',
                   '/%252e%252e/database/localdeal.db', '/src/app.js%00', '//backend/server.py']
        for path in blocked:
            with self.subTest(path=path):
                self.error(self.client.request('GET', path), 404, 'NOT_FOUND')

    def test_static_content_types_are_independent_of_os_mime_registry(self):
        expected = {
            '/': 'text/html; charset=utf-8',
            '/index.html': 'text/html; charset=utf-8',
            '/styles.css': 'text/css; charset=utf-8',
            '/src/i18n.js': 'text/javascript; charset=utf-8',
            '/src/http-api.js': 'text/javascript; charset=utf-8',
            '/src/app.js': 'text/javascript; charset=utf-8',
            '/assets/favicon.svg': 'image/svg+xml; charset=utf-8',
            '/assets/burger.jpg': 'image/jpeg',
            '/assets/dumplings.jpg': 'image/jpeg',
            '/assets/coffee.jpg': 'image/jpeg',
        }
        with patch('mimetypes.guess_type', return_value=('text/plain', None)):
            for path, content_type in expected.items():
                for method in ('GET', 'HEAD'):
                    with self.subTest(path=path, method=method):
                        status, body, headers = self.client.request(method, path)
                        self.assertEqual(status, 200)
                        self.assertEqual(headers.get('Content-Type'), content_type)
                        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')
                        if method == 'HEAD':
                            self.assertEqual(body, b'')
                        else:
                            self.assertTrue(body)

    def test_merchant_stock_adjustment_preserves_sales_and_requires_current_stock(self):
        customer=self.authenticated()
        owner=self.authenticated('harbor.owner@example.com')
        other=self.authenticated('coffee.owner@example.com')
        original=self.data(customer.request('GET','/api/coupons/c1'))['stock']
        old_sold=self.sql("SELECT total_stock-available_stock FROM coupons WHERE coupon_id='c1'")[0][0]
        path='/api/merchant/coupons/c1/stock'
        payload={'stock':original+5,'expectedStock':original}
        self.error(customer.request('PATCH',path,payload),403,'FORBIDDEN')
        self.error(other.request('PATCH',path,payload),403,'FORBIDDEN')
        self.assertEqual(self.data(owner.request('PATCH',path,payload))['stock'],original+5)
        self.error(owner.request('PATCH',path,payload),409,'STOCK_CHANGED')
        self.error(owner.request('PATCH',path,{'stock':-1,'expectedStock':original+5}),400,'INVALID_STOCK')
        self.assertEqual(self.data(owner.request('PATCH',path,{'stock':0,'expectedStock':original+5}))['stock'],0)
        self.assertEqual(self.data(customer.request('GET','/api/coupons/c1'))['stock'],0)
        self.assertEqual(self.sql("SELECT total_stock-available_stock FROM coupons WHERE coupon_id='c1'")[0][0],old_sold)
        self.assertEqual(self.sql("SELECT count(*) FROM orders WHERE coupon_id='c1'")[0][0],old_sold)
        self.assertEqual(self.data(owner.request('GET','/api/merchant/analytics?storeId=s1'))['offers'][0]['stock'],0)

    def test_api_unknown_routes_options_and_unsupported_methods_return_json(self):
        self.error(self.client.request('GET', '/api/unknown'), 404, 'NOT_FOUND')
        self.error(self.client.request('OPTIONS', '/api/state'), 405, 'METHOD_NOT_ALLOWED')
        for method in ('PUT', 'TRACE', 'CONNECT'):
            with self.subTest(method=method):
                self.error(self.client.request(method, '/api/state', {}), 405, 'METHOD_NOT_ALLOWED')
        status, body, headers = self.client.request('HEAD', '/api/state')
        self.assertEqual(status, 405)
        self.assertEqual(body, b'')
        self.assertEqual(headers.get('Content-Type', '').split(';')[0], 'application/json')
        self.assertIsNone(headers.get('Access-Control-Allow-Origin'))
        alex = self.authenticated()
        self.error(alex.request('POST', '/api/unknown', {}), 404, 'NOT_FOUND')

    def test_search_detail_pagination_and_sql_metacharacters(self):
        query = urlencode({'district': 'central', 'category': 'cat-western'})
        stores = self.page(self.client.request('GET', '/api/stores?' + query))['items']
        self.assertEqual([s['id'] for s in stores], ['s1'])
        self.assertEqual(len(self.data(self.client.request('GET', '/api/stores/s1/menu'))), 3)
        self.assertEqual(self.page(self.client.request('GET', '/api/stores/s1/reviews'))['total'], 5)
        self.assertEqual(self.data(self.client.request('GET', '/api/coupons/c1'))['storeId'], 's1')
        self.assertEqual(len(self.page(self.client.request('GET', '/api/stores?limit=2&offset=2'))['items']), 2)
        for query in ('limit=0', 'limit=51', 'limit=bad', 'offset=-1', 'offset=1000001'):
            with self.subTest(query=query):
                self.error(self.client.request('GET', '/api/stores?' + query), 400, 'INVALID_PAGINATION')
        for search in ("' OR 1=1 --", '%', '_'):
            with self.subTest(search=search):
                self.assertEqual(self.page(self.client.request('GET', '/api/stores?' + urlencode({'q': search})))['items'], [])
        self.assertEqual(self.page(self.client.request('GET', '/api/stores'))['total'], 6)

    def test_compact_bootstrap_default_pages_and_page_bounds(self):
        before = self.data(self.client.request('GET', '/api/state'))
        self.paging_fixture()
        after = self.data(self.client.request('GET', '/api/state'))
        for key in ('stores', 'coupons', 'reviews', 'orders', 'favorites', 'merchantOrders'):
            self.assertEqual(after[key], [])
        self.assertLessEqual(len(json.dumps(after)), len(json.dumps(before)) + 300)
        self.assertEqual([len(after['categories']), len(after['districts'])], [3, 3])
        self.assertIsNotNone(after['featuredStore'])
        self.assertIsNotNone(after['featuredCoupon'])
        alex = self.authenticated()
        harbor = self.authenticated('harbor.owner@example.com')
        routes = [
            (self.client, '/api/stores', 12, 36),
            (self.client, '/api/coupons', 12, 37),
            (self.client, '/api/stores/s1/reviews', 10, 35),
            (alex, '/api/users/me/favorites', 12, 32),
            (alex, '/api/users/me/reviews', 10, 32),
            (alex, '/api/orders', 10, 18),
            (harbor, '/api/merchant/orders', 10, 11),
        ]
        for client, route, default, total in routes:
            with self.subTest(route=route):
                page = self.page(client.request('GET', route))
                self.assertEqual((page['total'], page['limit'], page['offset']), (total, default, 0))
                self.assertTrue(page['hasMore'])
                for query in ('limit=0', 'limit=51', 'limit=1.5', 'offset=-1', 'offset=1000001'):
                    self.error(client.request('GET', route + '?' + query), 400, 'INVALID_PAGINATION')
                empty = self.page(client.request('GET', route + '?limit=50&offset=1000000'))
                self.assertEqual((empty['items'], empty['total'], empty['hasMore']), ([], total, False))

    def test_store_pages_filters_escaped_search_sort_and_complete_ratings(self):
        self.paging_fixture()
        alex = self.authenticated()
        recommended = self.pages(alex, '/api/stores?sort=recommended')
        self.assertEqual(len(recommended), 36)
        self.assertEqual([s['id'] for s in recommended], [s['id'] for s in sorted(recommended,key=lambda s:(-s['recommendation']['score'],s['id']))])
        self.assertTrue(all(s['menu'] == [] for s in recommended))
        by_id = {s['id']: s for s in recommended}
        self.assertTrue(by_id['s1']['isFavorite'])
        self.assertFalse(by_id['s2']['isFavorite'])
        self.assertEqual(by_id['s1']['reviewCount'], 35)
        self.assertEqual(by_id['s1']['averageRating'], self.sql("SELECT round(avg(rating),1) FROM reviews WHERE store_id='s1'")[0][0])
        self.assertEqual(by_id['z-page-store-00']['coupon']['storeId'], 'z-page-store-00')
        filtered = self.page(self.client.request('GET', '/api/stores?' + urlencode({'district': '中环', 'category': 'cat-western'})))
        self.assertEqual(filtered['total'], 31)
        cases = [('paging-probe', ['z-page-store-00', 'z-page-store-01']),
                 ('Paging Noodles', ['z-page-store-02']), ('%', ['z-page-store-00']),
                 ('_', ['z-page-store-00']), ("' OR 1=1 --", [])]
        for query, expected in cases:
            with self.subTest(query=query):
                page = self.page(self.client.request('GET', '/api/stores?' + urlencode({'q': query})))
                self.assertEqual(sorted(s['id'] for s in page['items']), sorted(expected))
        self.assertEqual(self.page(self.client.request('GET', '/api/stores?' + urlencode({'q': '西式餐厅'})))['total'], 32)
        self.assertEqual(self.page(self.client.request('GET', '/api/stores?' + urlencode({'q': '中环'})))['total'], 32)
        for sort in ('price', 'rating'):
            with self.subTest(sort=sort):
                items = self.pages(self.client, '/api/stores?sort=' + sort)
                key = (lambda s: (s['pricePerPerson'], s['id'])) if sort == 'price' else (lambda s: (-(s['averageRating'] or 0), s['id']))
                self.assertEqual([s['id'] for s in items], [s['id'] for s in sorted(items, key=key)])
        self.sql("UPDATE coupons SET expires_on='2000-01-01' WHERE coupon_id='page-coupon-01'")
        self.sql("UPDATE coupons SET is_active=0 WHERE coupon_id='page-coupon-02'")
        self.sql("UPDATE coupons SET available_stock=0 WHERE coupon_id='page-coupon-03'")
        only = self.pages(self.client, '/api/stores?couponOnly=true')
        self.assertEqual(len(only), 33)
        self.assertTrue(all(s['coupon'] is not None and s['coupon']['stock'] > 0 for s in only))
        self.assertEqual(self.page(self.client.request('GET', '/api/stores?couponOnly=false'))['total'], 36)
        self.error(self.client.request('GET', '/api/stores?couponOnly=maybe'), 400)
        self.error(self.client.request('GET', '/api/stores?sort=unknown'), 400)
        offers = self.page(self.client.request('GET', '/api/coupons?storeId=z-page-store-00&limit=1'))
        self.assertEqual(offers['total'], 2)
        self.assertTrue(offers['hasMore'])

    def test_explainable_recommendations_use_current_members_history(self):
        guest=self.page(self.client.request('GET','/api/stores'))['items']
        self.assertTrue(all(not s['recommendation']['personalized'] for s in guest))
        newcomer=Client(self.base)
        self.data(newcomer.register('New','recommendation@example.com'),201)
        before=self.page(newcomer.request('GET','/api/stores'))['items']
        self.assertEqual([(s['id'],s['recommendation']) for s in before],[(s['id'],s['recommendation']) for s in guest])
        self.data(newcomer.request('POST','/api/favorites/toggle',{'storeId':'s1'}))
        after=self.page(newcomer.request('GET','/api/stores'))['items']
        self.assertTrue(all(s['recommendation']['personalized'] for s in after))
        by_id={s['id']:s['recommendation'] for s in after}
        self.assertEqual(by_id['s1']['components']['interest'],100)
        self.assertEqual(by_id['s1']['components']['affinity'],100)
        self.assertEqual(by_id['s6']['components']['interest'],0)
        self.assertEqual(after[0]['id'],'s1')
        self.data(newcomer.request('POST','/api/favorites/toggle',{'storeId':'s1'}))
        reverted=self.page(newcomer.request('GET','/api/stores'))['items']
        self.assertEqual([(s['id'],s['recommendation']) for s in reverted],[(s['id'],s['recommendation']) for s in guest])

    def test_group_match_budget_fairness_pagination_and_validation(self):
        def route(members,district='',**params):
            return '/api/group-match?'+urlencode({'members':json.dumps(members),'district':district,**params})
        members=[{'budget':150,'category':'cat-western'},{'budget':100,'category':'cat-coffee'}]
        page=self.page(self.client.request('GET',route(members)))
        self.assertEqual(page['budgetLimit'],100)
        expected={r[0] for r in self.sql('SELECT store_id FROM stores WHERE is_active=1 AND price_per_person_cents<=10000')}
        self.assertEqual({s['id'] for s in page['items']},expected)
        self.assertTrue(expected)
        self.assertTrue(all(s['pricePerPerson']<=100 and s['groupMatch']['memberCount']==2 for s in page['items']))
        worst=[s['groupMatch']['worstScore'] for s in page['items']]
        self.assertEqual(worst,sorted(worst,reverse=True))
        paged=self.pages(self.client,route(members))
        self.assertEqual([s['id'] for s in paged],[s['id'] for s in page['items']])
        # Independently recompute max-min and mean on a mixed three-person
        # fixture. This checks more than the monotonicity of the output.
        mixed=[{'budget':180,'category':'cat-coffee'},{'budget':165,'category':'cat-coffee'},
               {'budget':200,'category':'cat-asian'}]
        actual=self.page(self.client.request('GET',route(mixed)))['items']
        scores={}
        for row in self.sql('''SELECT s.store_id,s.category_id,s.price_per_person_cents,
            round(avg(r.rating),1) AS avg_rating,count(r.review_id) AS n
            FROM stores s LEFT JOIN reviews r USING(store_id) WHERE s.is_active=1 GROUP BY s.store_id'''):
            if row['price_per_person_cents']>16500:continue
            rep=((row['avg_rating'] or 3.5)*row['n']+17.5)/(row['n']+5)/5
            individual=[100*(.65*(m['category']==row['category_id'])+.25*rep+
                           .10*(1-row['price_per_person_cents']/(m['budget']*100))) for m in mixed]
            scores[row['store_id']]=(min(individual),sum(individual)/len(individual))
        self.assertEqual([s['id'] for s in actual],sorted(scores,key=lambda sid:(-scores[sid][0],-scores[sid][1],sid)))
        for store in actual:
            self.assertAlmostEqual(store['groupMatch']['worstScore'],scores[store['id']][0],delta=.051)
            self.assertAlmostEqual(store['groupMatch']['meanScore'],scores[store['id']][1],delta=.051)
        zone=self.page(self.client.request('GET',route(members,'central')))
        self.assertTrue(all(s['district']=='中环' for s in zone['items']))
        empty=self.page(self.client.request('GET',route([{'budget':1,'category':''}]*2)))
        self.assertEqual(empty['total'],0)
        for invalid in ([],[{'budget':100,'category':''}]*9,[{'budget':True,'category':''}]*2,[{'budget':100,'category':'unknown'}]*2):
            self.error(self.client.request('GET',route(invalid)),400,'INVALID_GROUP')

    def test_merchant_analytics_reflects_purchase_redemption_and_scope(self):
        alex=self.authenticated(); harbor=self.authenticated('harbor.owner@example.com')
        route='/api/merchant/analytics?storeId=s1&days=7'
        self.error(self.client.request('GET',route),401)
        self.error(alex.request('GET',route),403)
        self.error(harbor.request('GET','/api/merchant/analytics?storeId=s3&days=7'),403)
        before=self.data(harbor.request('GET',route))
        self.assertEqual({b['id'] for b in before['branches']},{'s1','s2'})
        self.assertEqual(len(before['trend']),7)
        order=self.data(alex.request('POST','/api/orders',{'couponId':'c1','idempotencyKey':'analysis-test'}),201)
        after=self.data(harbor.request('GET',route))
        self.assertEqual(after['sold'],before['sold']+1)
        self.assertAlmostEqual(after['gross'],before['gross']+order['price'])
        self.assertEqual(after['todaySold'],before['todaySold']+1)
        self.assertEqual(after['offers'][0]['stock'],before['offers'][0]['stock']-1)
        self.assertAlmostEqual(after['trend'][-1]['cumulative'],after['gross'])
        self.assertEqual(after['branches'][0]['sold'],before['branches'][0]['sold']+1)
        self.assertNotIn('u-demo',json.dumps(after))
        self.data(harbor.request('POST','/api/orders/redeem',{'storeId':'s1','code':order['code']}))
        final=self.data(harbor.request('GET',route))
        self.assertEqual(final['redeemed'],after['redeemed']+1)
        self.assertEqual(final['unused'],after['unused']-1)
        self.assertEqual(final['gross'],after['gross'])
        self.assertEqual(len(self.data(harbor.request('GET','/api/merchant/analytics?storeId=s1&days=30'))['trend']),30)

    def test_review_pages_keep_own_review_outside_filters_and_page(self):
        self.paging_fixture()
        alex = self.authenticated()
        first = self.page(alex.request('GET', '/api/stores/s1/reviews?limit=2&sort=new'))
        self.assertEqual(first['total'], 35)
        self.assertEqual(first['ownReview']['id'], 'r-s1-1')
        self.assertNotIn('r-s1-1', [r['id'] for r in first['items']])
        one_star = self.page(alex.request('GET', '/api/stores/s1/reviews?rating=1&limit=2&sort=rating'))
        self.assertEqual(one_star['total'], 6)
        self.assertTrue(all(r['rating'] == 1 for r in one_star['items']))
        self.assertEqual(one_star['ownReview']['rating'], 5)
        empty = self.page(alex.request('GET', '/api/stores/s1/reviews?rating=1&offset=100'))
        self.assertEqual(empty['items'], [])
        self.assertEqual(empty['ownReview']['id'], 'r-s1-1')
        public = self.page(self.client.request('GET', '/api/stores/s1/reviews?limit=2'))
        self.assertIsNone(public['ownReview'])
        newest = self.pages(alex, '/api/stores/s1/reviews?sort=new')
        self.assertEqual([r['id'] for r in newest[:30]], ['page-review-' + f'{i:02d}' for i in range(30)])
        rated = self.pages(alex, '/api/stores/s1/reviews?sort=rating')
        self.assertEqual([r['rating'] for r in rated], sorted((r['rating'] for r in rated), reverse=True))
        self.error(alex.request('GET', '/api/stores/s1/reviews?rating=0'), 400)
        self.error(alex.request('GET', '/api/stores/s1/reviews?sort=unknown'), 400)

    def test_personal_profile_pages_author_scope_and_intentionally_full_export(self):
        self.paging_fixture()
        alex = self.authenticated()
        amy = self.authenticated('amy@example.com')
        mine = self.pages(alex, '/api/users/me/reviews')
        favorites = self.pages(alex, '/api/users/me/favorites')
        self.assertEqual(len(mine), 32)
        self.assertEqual(len(favorites), 32)
        self.assertTrue(all(r['userId'] == 'u-demo' for r in mine))
        self.assertTrue(all(r['storeName'] for r in mine))
        self.assertTrue(all(s['isFavorite'] for s in favorites))
        theirs = self.pages(amy, '/api/users/me/reviews')
        self.assertEqual(len(theirs), 6)
        self.assertTrue(all(r['userId'] == 'u-amy' for r in theirs))
        self.assertEqual(self.page(amy.request('GET', '/api/users/me/favorites'))['items'], [])
        summary = self.data(alex.request('GET', '/api/state'))['summary']
        self.assertEqual((summary['favorites'], summary['reviews']), (32, 32))
        exported = self.data(alex.request('GET', '/api/export'))
        self.assertEqual([len(exported[key]) for key in ('favorites', 'reviews', 'orders')], [32, 32, 18])
        self.assertTrue(all(r['userId'] == 'u-demo' for r in exported['reviews']))

    def test_order_pages_status_counts_metadata_and_customer_isolation(self):
        self.paging_fixture()
        alex = self.authenticated()
        amy = self.authenticated('amy@example.com')
        counts = self.data(alex.request('GET', '/api/state'))['summary']['orders']
        self.assertEqual(counts, {'all': 18, 'unused': 6, 'redeemed': 6, 'expired': 6})
        orders = self.pages(alex, '/api/orders?status=all', limit=4)
        self.assertEqual(len(orders), 18)
        self.assertTrue(all(o['userId'] == 'u-demo' for o in orders))
        self.assertTrue(all(o['storeName'] and o['storeDistrict'] and o['storeImage'] for o in orders))
        for status in ('unused', 'redeemed', 'expired'):
            with self.subTest(status=status):
                items = self.pages(alex, '/api/orders?status=' + status, limit=2)
                self.assertEqual(len(items), counts[status])
                self.assertTrue(all(o['status'] == status for o in items))
        others = self.pages(amy, '/api/orders', limit=4)
        self.assertEqual(len(others), 15)
        self.assertTrue(all(o['userId'] == 'u-amy' for o in others))
        self.assertFalse({o['id'] for o in orders} & {o['id'] for o in others})
        self.error(alex.request('GET', '/api/orders?status=unknown'), 400, 'INVALID_STATUS')

    def test_merchant_pages_enforce_active_branch_scope_including_empty_ledgers(self):
        self.paging_fixture()
        harbor = self.authenticated('harbor.owner@example.com')
        coffee = self.authenticated('coffee.owner@example.com')
        ledger = self.pages(harbor, '/api/merchant/orders', limit=3)
        self.assertEqual(len(ledger), 11)
        self.assertTrue(all(o['storeId'] == 's1' for o in ledger))
        self.assertEqual(self.page(harbor.request('GET', '/api/merchant/orders?storeId=s2'))['total'], 0)
        self.error(harbor.request('GET', '/api/merchant/orders?storeId=s3'), 403, 'FORBIDDEN')
        self.error(harbor.request('GET', '/api/merchant/orders?storeId=missing'), 403, 'FORBIDDEN')
        self.assertEqual(self.page(harbor.request('GET', '/api/merchant/orders?status=redeemed'))['total'], 0)
        coffee_rows = self.pages(coffee, '/api/merchant/orders', limit=3)
        self.assertTrue(all(o['storeId'] == 's5' for o in coffee_rows))
        self.assertFalse({o['id'] for o in ledger} & {o['id'] for o in coffee_rows})
        self.sql("UPDATE store_staff SET is_active=0 WHERE user_id='u-harbor' AND store_id='s1'")
        self.assertEqual(self.page(harbor.request('GET', '/api/merchant/orders'))['total'], 0)
        self.error(harbor.request('GET', '/api/merchant/orders?storeId=s1'), 403, 'FORBIDDEN')

    def test_failed_login_rate_limit_and_successful_login_reset(self):
        for _ in range(10):
            self.error(self.client.login('rate-limit@example.com'), 401, 'INVALID_CREDENTIALS')
        limited = self.client.login('rate-limit@example.com')
        self.error(limited, 429, 'RATE_LIMITED')
        self.data(self.client.login())
        self.error(self.client.login(password='wrong-password-2026'), 401)
        self.data(self.client.login())

    def test_restart_preserves_account_orders_inventory_and_session(self):
        alex = self.authenticated()
        order = self.data(alex.request('POST', '/api/orders', {'couponId': 'c2', 'idempotencyKey': 'restart'}), 201)
        before = self.data(alex.request('GET', '/api/state'))
        before_orders = self.page(alex.request('GET', '/api/orders'))
        before_offer = self.data(alex.request('GET', '/api/coupons/c2'))
        self.stop_server()
        self.start_server()
        alex.base = self.base
        after = self.data(alex.request('GET', '/api/state'))
        self.assertEqual(after['user'], before['user'])
        self.assertEqual(after['summary'], before['summary'])
        self.assertEqual(self.page(alex.request('GET', '/api/orders')), before_orders)
        self.assertEqual(self.data(alex.request('GET', '/api/coupons/c2')), before_offer)
        self.assertEqual(self.data(alex.request('GET', '/api/orders/' + order['id'])), order)
        self.data(alex.request('POST', '/api/auth/logout', {}))
        self.assertEqual(len(self.sql('SELECT token_hash FROM sessions')), 0)


if __name__ == '__main__':
    unittest.main()
