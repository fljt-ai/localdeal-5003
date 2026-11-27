"""Same-origin JSON API and allowlisted frontend assets, bound to loopback only.

This dependency-free HTTP server is a local coursework demonstration. Public
deployment requires a production server and HTTPS rather than exposing this one.
"""
from contextlib import closing
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import re
import socket
import sqlite3
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit

from database import operations
from . import service, insights
from .database import DEFAULT_DB, ROOT, initialize_database

COOKIE_NAME = 'localdeal_session'
MAX_BODY = 16384
FRONTEND = ROOT / 'frontend'
STATIC_PATHS = {'/','/index.html','/styles.css','/src/app.js','/src/http-api.js','/src/i18n.js',
                '/assets/favicon.svg','/assets/burger.jpg','/assets/dumplings.jpg','/assets/coffee.jpg'}
STATIC_CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.svg': 'image/svg+xml; charset=utf-8',
    '.jpg': 'image/jpeg',
}


class LoginLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.attempts = {}

    def attempt(self, key):
        now = time.monotonic()
        with self.lock:
            self.attempts = {k:v for k,v in self.attempts.items() if v[1] > now}
            count, until = self.attempts.get(key,(0,now+300))
            if count >= 10:
                raise service.APIError(429,'RATE_LIMITED','尝试次数过多，请五分钟后再试。')
            self.attempts[key] = (count+1,until)

    def clear(self, key):
        with self.lock:
            self.attempts.pop(key,None)


class LocalDealServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalDeal/1.0'
    sys_version = ''
    protocol_version = 'HTTP/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        if not self.server.quiet:
            # Do not log cookies, request bodies or credential-bearing fields.
            print(self.command, urlsplit(self.path).path, args[1] if len(args)>1 else '')

    def headers_common(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; connect-src 'self'; base-uri 'none'; object-src 'none'; "
                         "frame-ancestors 'none'; form-action 'self'")

    def json_reply(self, status, value, cookie=None):
        encoded = json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(encoded)))
        self.send_header('Cache-Control','no-store')
        self.headers_common()
        if cookie is not None:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(encoded)

    def cookie_header(self, token, clear=False):
        age = 0 if clear else service.SESSION_SECONDS
        return f'{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}'

    def raw_token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie',''))
            return cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else None
        except CookieError:
            return None

    def check_host(self):
        allowed = {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if len(self.headers.get_all('Host',[])) != 1 or self.headers.get('Host') not in allowed:
            raise service.APIError(403,'INVALID_HOST','服务器仅接受本机访问。')

    def mutation_body(self):
        origin = self.headers.get('Origin')
        if len(self.headers.get_all('Origin',[])) > 1 or (origin is not None and origin != 'http://' + self.headers.get('Host','')):
            raise service.APIError(403,'INVALID_ORIGIN','请求来源不被允许。')
        if self.headers.get('X-LocalDeal-Request') != '1':
            raise service.APIError(403,'REQUEST_HEADER_REQUIRED','缺少应用请求标识。')
        if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
            raise service.APIError(415,'JSON_REQUIRED','请求需使用 JSON 格式。')
        if self.headers.get('Transfer-Encoding') is not None:
            raise service.APIError(400,'INVALID_BODY','不支持这种请求传输格式。')
        lengths = self.headers.get_all('Content-Length',[])
        if len(lengths) != 1:
            raise service.APIError(411,'LENGTH_REQUIRED','请求需提供内容长度。')
        try:
            length = int(lengths[0])
        except ValueError:
            raise service.APIError(400,'INVALID_LENGTH','内容长度无效。')
        if length < 0:
            raise service.APIError(400,'INVALID_LENGTH','内容长度无效。')
        if length > MAX_BODY:
            raise service.APIError(413,'BODY_TOO_LARGE','请求内容过大。')

        def object_unique(pairs):
            result = {}
            for key,value in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON key')
                result[key] = value
            return result

        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Incomplete body')
            payload = json.loads(raw.decode('utf-8'),object_pairs_hook=object_unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        except (UnicodeError,ValueError):
            raise service.APIError(400,'INVALID_JSON','JSON 内容无效。')
        if not isinstance(payload,dict):
            raise service.APIError(400,'INVALID_JSON','JSON 请求需为对象。')
        return payload

    def csrf_check(self, session):
        service.require_session(session)
        supplied = self.headers.get('X-CSRF-Token','')
        if not re.fullmatch(r'[0-9a-f]{64}',supplied) or not hmac.compare_digest(supplied,session['csrf_token']):
            raise service.APIError(403,'CSRF_FAILED','会话验证未通过，请刷新页面后重试。')

    def static_reply(self, path):
        if path not in STATIC_PATHS:
            raise service.APIError(404,'NOT_FOUND','没有找到这个资源。')
        relative = 'index.html' if path == '/' else path.lstrip('/')
        target = (FRONTEND / relative).resolve()
        if not target.is_relative_to(FRONTEND.resolve()) or not target.is_file():
            raise service.APIError(404,'NOT_FOUND','没有找到这个资源。')
        data = target.read_bytes()
        # Use explicit MIME types rather than OS-specific registry mappings.
        content_type = STATIC_CONTENT_TYPES.get(target.suffix.lower(), 'application/octet-stream')
        self.send_response(200)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-cache')
        self.headers_common()
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def dispatch(self):
        try:
            self.check_host()
            split = urlsplit(self.path)
            path = unquote(split.path)
            if not path.startswith('/api/'):
                if self.command not in ('GET','HEAD'):
                    raise service.APIError(405,'METHOD_NOT_ALLOWED','这种请求方法不被允许。')
                self.static_reply(path)
                return
            if self.command not in ('GET','POST','PATCH','DELETE'):
                raise service.APIError(405,'METHOD_NOT_ALLOWED','这种请求方法不被允许。')
            payload = self.mutation_body() if self.command != 'GET' else None
            with closing(operations.connect(self.server.database_path)) as connection:
                raw_token = self.raw_token()
                session = service.session_for_token(connection,raw_token)
                if self.command != 'GET' and path not in ('/api/auth/login','/api/auth/register'):
                    self.csrf_check(session)
                data, status, cookie = self.api(connection,session,raw_token,path,
                                               parse_qs(split.query,keep_blank_values=True),payload)
            self.json_reply(status,{'data':data},cookie)
        except service.APIError as error:
            self.json_reply(error.status,{'error':{'code':error.code,'message':error.message}})
        except operations.DatabaseRuleError as error:
            mapped = service.map_rule(error)
            self.json_reply(mapped.status,{'error':{'code':mapped.code,'message':mapped.message}})
        except sqlite3.OperationalError as error:
            if 'locked' in str(error).lower() or 'busy' in str(error).lower():
                self.json_reply(503,{'error':{'code':'DATABASE_BUSY','message':'数据库忙，请稍后重试。'}})
            else:
                self.json_reply(500,{'error':{'code':'DATABASE_ERROR','message':'数据库操作未完成。'}})
        except (socket.timeout,TimeoutError):
            self.json_reply(408,{'error':{'code':'REQUEST_TIMEOUT','message':'请求超时。'}})
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception:
            self.json_reply(500,{'error':{'code':'INTERNAL_ERROR','message':'操作未完成，请稍后重试。'}})

    def api(self, connection, session, raw_token, path, query, payload):
        method = self.command
        if method == 'GET':
            if path == '/api/health':
                return {'status':'ok','databaseVersion':2},200,None
            if path == '/api/state':
                return service.state(connection,session),200,None
            if path == '/api/auth/session':
                return {'user':service.user_object(connection,session['user_id']) if session else None,
                        'csrfToken':session['csrf_token'] if session else None},200,None
            if path == '/api/stores':
                return service.stores_page(connection,session,query),200,None
            if path == '/api/group-match':
                return insights.group_match(connection,session,query),200,None
            if path == '/api/users/me/favorites':
                return service.stores_page(connection,session,query,favorites=True),200,None
            if path == '/api/users/me/reviews':
                return service.reviews_page(connection,session,query,own=True),200,None
            if path == '/api/merchant/orders':
                return service.orders_page(connection,session,query,merchant=True),200,None
            if path == '/api/merchant/analytics':
                return insights.merchant_analytics(connection,session,query),200,None
            store_match = re.fullmatch(r'/api/stores/([^/]+)(/(menu|reviews))?',path)
            if store_match:
                identifier, _, sub = store_match.groups()
                if sub == 'reviews':
                    return service.reviews_page(connection,session,query,store_id=identifier),200,None
                store = service.get_store(connection,identifier,session)
                if sub == 'menu':
                    return store['menu'],200,None
                return store,200,None
            if path == '/api/coupons':
                return service.coupons_page(connection,query),200,None
            coupon_match = re.fullmatch(r'/api/coupons/([^/]+)',path)
            if coupon_match:
                return service.get_coupon(connection,coupon_match[1]),200,None
            if path == '/api/orders':
                return service.orders_page(connection,session,query),200,None
            order_match = re.fullmatch(r'/api/orders/([^/]+)',path)
            if order_match:
                user_id = service.require_session(session)
                return service.get_order(connection,order_match[1],user_id),200,None
            if path == '/api/export':
                return service.personal_export(connection,session),200,None
        if method == 'POST':
            if path in ('/api/auth/login','/api/auth/register'):
                limiter_key = (self.client_address[0],str(payload.get('email','')).strip().lower())
                if path.endswith('/register'):
                    limiter_key = (self.client_address[0],'registration')
                self.server.limiter.attempt(limiter_key)
                action = service.login if path.endswith('/login') else service.register
                data, token = action(connection,payload,raw_token)
                if path.endswith('/login'):
                    self.server.limiter.clear(limiter_key)
                return data,201 if path.endswith('/register') else 200,self.cookie_header(token)
            if path == '/api/auth/logout':
                service.fields(payload,())
                return service.logout(connection,session),200,self.cookie_header('',clear=True)
            if path == '/api/favorites/toggle':
                return service.toggle_favorite(connection,session,payload),200,None
            review_match = re.fullmatch(r'/api/stores/([^/]+)/reviews',path)
            if review_match:
                service.fields(payload,('rating','comment'))
                user_id = service.require_session(session)
                result = operations.save_review(connection,user_id,review_match[1],payload['rating'],payload['comment'])
                return service.get_review(connection,result['review_id']),201,None
            if path == '/api/orders':
                service.fields(payload,('couponId','idempotencyKey'))
                user_id = service.require_session(session)
                coupon_id = service.text(payload['couponId'],'优惠编号',1,80)
                old = connection.execute('SELECT 1 FROM orders WHERE user_id = ? AND idempotency_key = ?',
                                         (user_id,payload['idempotencyKey'] if isinstance(payload['idempotencyKey'],str) else '')).fetchone()
                order = operations.purchase_coupon(connection,user_id,coupon_id,payload['idempotencyKey'])
                return service.get_order(connection,order['order_id'],user_id),200 if old else 201,None
            if path == '/api/orders/redeem':
                service.fields(payload,('code','storeId'))
                user_id = service.require_session(session)
                store_id = service.text(payload['storeId'],'门店编号',1,80)
                result = operations.redeem_coupon(connection,user_id,store_id,payload['code'])
                return service.get_order(connection,result['order_id']),200,None
        if method == 'PATCH':
            if path == '/api/users/me':
                return service.update_profile(connection,session,payload),200,None
            review_match = re.fullmatch(r'/api/reviews/([^/]+)',path)
            if review_match:
                service.fields(payload,('rating','comment'))
                user_id = service.require_session(session)
                original = connection.execute('SELECT store_id FROM reviews WHERE review_id = ?', (review_match[1],)).fetchone()
                if original is None:
                    raise service.APIError(404,'REVIEW_NOT_FOUND','这条点评不存在。')
                result = operations.save_review(connection,user_id,original['store_id'],payload['rating'],payload['comment'],review_match[1])
                return service.get_review(connection,result['review_id']),200,None
        if method == 'DELETE':
            review_match = re.fullmatch(r'/api/reviews/([^/]+)',path)
            if review_match:
                service.fields(payload,())
                operations.delete_review(connection,service.require_session(session),review_match[1])
                return {'deleted':True},200,None
        raise service.APIError(404,'NOT_FOUND','没有找到这个接口。')

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch
    do_PATCH = dispatch
    do_DELETE = dispatch
    do_OPTIONS = dispatch
    do_PUT = dispatch
    do_TRACE = dispatch
    do_CONNECT = dispatch


def create_server(database_path=DEFAULT_DB, port=0, quiet=True):
    path = initialize_database(database_path)
    server = LocalDealServer(('127.0.0.1',port),Handler)
    server.database_path = path
    server.quiet = quiet
    server.limiter = LoginLimiter()
    return server
