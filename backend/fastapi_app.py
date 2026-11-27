"""FastAPI transport for LocalDeal's shared application controller.

Serve the same business API and SQLite database through a documented ASGI
interface. All ordinary application requests retain local-only access,
same-origin checks, server-side sessions, CSRF validation and explicit MIME.
"""
from contextlib import closing
from http.cookies import CookieError, SimpleCookie
import hmac
import json
import re
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from database import operations
from . import schemas, service
from .controller import COOKIE_NAME, dispatch_api
from .database import DEFAULT_DB, ROOT, initialize_database
from .server import LoginLimiter, MAX_BODY, STATIC_CONTENT_TYPES, STATIC_PATHS

FRONTEND = ROOT / 'frontend'
VENDOR = ROOT / 'backend/vendor/swagger-ui'
COMMON_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'same-origin',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; object-src 'none'; "
    "frame-ancestors 'none'; form-action 'self'",
}

# Explicit route manifest also drives OpenAPI. Keep business rules in controller/service.
# (HTTP method, route, summary, request model, optional query parameters)
ROUTES = [
    ('GET','/api/health','Service health',None,()),
    ('GET','/api/state','Compact application bootstrap',None,()),
    ('GET','/api/auth/session','Current session',None,()),
    ('GET','/api/stores','Search and paginate stores',None,('q','district','category','sort','couponOnly','limit','offset')),
    ('GET','/api/group-match','Fair group dining recommendations',None,('members','district','limit','offset')),
    ('GET','/api/users/me/favorites','My favourite restaurants',None,('limit','offset')),
    ('GET','/api/users/me/reviews','My reviews',None,('limit','offset')),
    ('GET','/api/merchant/orders','Authorized branch orders',None,('storeId','status','limit','offset')),
    ('GET','/api/merchant/analytics','Authorized branch analytics',None,('storeId','days')),
    ('GET','/api/stores/{store_id}/menu','Restaurant menu',None,()),
    ('GET','/api/stores/{store_id}/reviews','Paginated restaurant reviews',None,('rating','sort','limit','offset')),
    ('GET','/api/stores/{store_id}','Restaurant detail',None,()),
    ('GET','/api/coupons','Paginated vouchers',None,('storeId','limit','offset')),
    ('GET','/api/coupons/{coupon_id}','Voucher detail',None,()),
    ('GET','/api/orders','My voucher wallet',None,('status','limit','offset')),
    ('GET','/api/orders/{order_id}','My order detail',None,()),
    ('GET','/api/export','Export my data',None,()),
    ('POST','/api/auth/login','Sign in',schemas.LoginBody,()),
    ('POST','/api/auth/register','Register a customer',schemas.RegisterBody,()),
    ('POST','/api/auth/logout','Sign out',schemas.RequestBody,()),
    ('POST','/api/favorites/toggle','Toggle a favourite',schemas.FavoriteBody,()),
    ('POST','/api/stores/{store_id}/reviews','Create review',schemas.ReviewBody,()),
    ('POST','/api/orders','Purchase a simulated voucher',schemas.PurchaseBody,()),
    ('POST','/api/orders/redeem','Redeem a voucher at an authorized branch',schemas.RedeemBody,()),
    ('PATCH','/api/users/me','Edit profile',schemas.ProfileBody,()),
    ('PATCH','/api/reviews/{review_id}','Edit own review',schemas.ReviewBody,()),
    ('PATCH','/api/merchant/coupons/{coupon_id}/stock','Set unsold voucher stock',schemas.StockBody,()),
    ('DELETE','/api/reviews/{review_id}','Delete own review',schemas.RequestBody,()),
]


def error_reply(status, code, message):
    return JSONResponse({'error': {'code': code, 'message': message}}, status_code=status,
                        headers={'Cache-Control':'no-store', **COMMON_HEADERS})


def raw_cookie(request):
    try:
        cookies = SimpleCookie()
        cookies.load(request.headers.get('cookie',''))
        return cookies[COOKIE_NAME].value if COOKIE_NAME in cookies else None
    except CookieError:
        return None


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON key')
        value[key] = item
    return value


async def parse_mutation(request, model):
    origin = request.headers.get('origin')
    if len(request.headers.getlist('origin'))>1 or (origin is not None and origin!='http://'+request.headers.get('host','')):
        raise service.APIError(403,'INVALID_ORIGIN','请求来源不被允许。')
    if request.headers.get('x-localdeal-request') != '1':
        raise service.APIError(403,'REQUEST_HEADER_REQUIRED','缺少应用请求标识。')
    if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':
        raise service.APIError(415,'JSON_REQUIRED','请求需使用 JSON 格式。')
    if request.headers.get('transfer-encoding') is not None:
        raise service.APIError(400,'INVALID_BODY','不支持这种请求传输格式。')
    lengths=request.headers.getlist('content-length')
    if len(lengths)!=1:
        raise service.APIError(411,'LENGTH_REQUIRED','请求需提供内容长度。')
    try:
        length=int(lengths[0])
    except ValueError:
        raise service.APIError(400,'INVALID_LENGTH','内容长度无效。')
    if length<0:
        raise service.APIError(400,'INVALID_LENGTH','内容长度无效。')
    if length>MAX_BODY:
        raise service.APIError(413,'BODY_TOO_LARGE','请求内容过大。')
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>MAX_BODY:
            raise service.APIError(413,'BODY_TOO_LARGE','请求内容过大。')
    try:
        if len(body)!=length:
            raise ValueError('Incomplete body')
        payload=json.loads(body.decode('utf-8'),object_pairs_hook=unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (ValueError,UnicodeError):
        raise service.APIError(400,'INVALID_JSON','JSON 内容无效。')
    if not isinstance(payload,dict):
        raise service.APIError(400,'INVALID_JSON','JSON 请求需为对象。')
    # Strict types and no extra fields; domain-specific validation is shared by both transports.
    try:
        return model.model_validate(payload).model_dump()
    except ValidationError as error:
        if any(item['type'] in ('missing','extra_forbidden') for item in error.errors()):
            raise service.APIError(400,'INVALID_FIELDS','请求字段缺失或包含不允许修改的字段。') from None
        raise service.APIError(400,'INVALID_INPUT','输入数据类型或范围无效。') from None


def create_app(database_path=DEFAULT_DB, port=8787):
    path=initialize_database(database_path)
    limiter=LoginLimiter()
    app=FastAPI(title='LocalDeal API',version='2.0.0',docs_url=None,redoc_url=None,openapi_url=None,
                description='Local coursework API. Simulated vouchers, SQLite transactions and private branch analytics.')
    app.state.database_path=path

    @app.middleware('http')
    async def local_headers(request, call_next):
        allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
        if len(request.headers.getlist('host'))!=1 or request.headers.get('host') not in allowed:
            return error_reply(403,'INVALID_HOST','服务器仅接受本机访问。')
        response=await call_next(request)
        response.headers.update(COMMON_HEADERS)
        return response

    @app.exception_handler(service.APIError)
    async def application_error(request,error):
        return error_reply(error.status,error.code,error.message)

    @app.exception_handler(operations.DatabaseRuleError)
    async def database_error(request,error):
        mapped=service.map_rule(error)
        return error_reply(mapped.status,mapped.code,mapped.message)

    @app.exception_handler(sqlite3.OperationalError)
    async def sqlite_error(request,error):
        if 'locked' in str(error).lower() or 'busy' in str(error).lower():
            return error_reply(503,'DATABASE_BUSY','数据库忙，请稍后重试。')
        return error_reply(500,'DATABASE_ERROR','数据库操作未完成。')

    @app.exception_handler(HTTPException)
    async def route_error(request,error):
        code='METHOD_NOT_ALLOWED' if error.status_code==405 else 'NOT_FOUND'
        return error_reply(error.status_code,code,'这种请求方法不被允许。' if code=='METHOD_NOT_ALLOWED' else '没有找到这个资源。')

    @app.exception_handler(Exception)
    async def unexpected(request,error):
        return error_reply(500,'INTERNAL_ERROR','操作未完成，请稍后重试。')

    def endpoint(model):
        async def handle(request: Request):
            payload=await parse_mutation(request,model) if model else None
            params={key:request.query_params.getlist(key) for key in request.query_params}
            method=request.method
            route=request.url.path
            token=raw_cookie(request)
            def query_database():
                with closing(operations.connect(path)) as db:
                    session=service.session_for_token(db,token)
                    if method!='GET' and route not in ('/api/auth/login','/api/auth/register'):
                        service.require_session(session)
                        supplied=request.headers.get('x-csrf-token','')
                        if not re.fullmatch(r'[0-9a-f]{64}',supplied) or not hmac.compare_digest(supplied,session['csrf_token']):
                            raise service.APIError(403,'CSRF_FAILED','会话验证未通过，请刷新页面后重试。')
                    return dispatch_api(method,limiter,request.client.host if request.client else 'local',db,session,token,route,params,payload)
            data,status,cookie=await run_in_threadpool(query_database)
            headers={'Cache-Control':'no-store'}
            if cookie is not None:
                headers['Set-Cookie']=cookie
            return JSONResponse({'data':data},status_code=status,headers=headers)
        return handle

    for method,route,title,model,query in ROUTES:
        parameters=[{'name':name,'in':'path','required':True,'schema':{'type':'string'}} for name in re.findall(r'\{([^}]+)\}',route)]
        parameters.extend({'name':name,'in':'query','required':name=='members' or (route=='/api/merchant/analytics' and name=='storeId'),
            'schema':{'type':'string'}} for name in query)
        extra={'parameters':parameters}
        if model:
            extra['requestBody']={'required':True,'content':{'application/json':{'schema':model.model_json_schema()}}}
        success_status=201 if method=='POST' and route in ('/api/auth/register','/api/stores/{store_id}/reviews','/api/orders') else 200
        responses={400:{'description':'Invalid request'},401:{'description':'Sign-in required'},
                   403:{'description':'Not authorized'},409:{'description':'Business state conflict'}}
        if route=='/api/orders' and method=='POST':responses[200]={'description':'Idempotent replay of a purchase'}
        app.add_api_route(route,endpoint(model),methods=[method],summary=title,
                          name=method.lower()+'_'+re.sub(r'[^a-zA-Z0-9]+','_',route),openapi_extra=extra,
                          tags=[route.split('/')[2].capitalize()],status_code=success_status,responses=responses)

    @app.get('/openapi.json',include_in_schema=False)
    async def schema():
        return JSONResponse(app.openapi())

    @app.get('/docs',include_in_schema=False)
    async def swagger():
        return HTMLResponse('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width, initial-scale=1"><title>LocalDeal API Documentation</title>'
            '<link rel="stylesheet" href="/docs-assets/swagger-ui.css"></head><body><div id="swagger-ui"></div>'
            '<script src="/docs-assets/swagger-ui-bundle.js"></script><script src="/docs-assets/init.js"></script></body></html>')

    @app.api_route('/docs-assets/{name}',methods=['GET','HEAD'],include_in_schema=False)
    async def docs_asset(request: Request,name: str):
        known={'swagger-ui.css':VENDOR/'swagger-ui.css','swagger-ui-bundle.js':VENDOR/'swagger-ui-bundle.js',
               'init.js':ROOT/'backend/swagger-init.js'}
        if name not in known:
            raise service.APIError(404,'NOT_FOUND','没有找到这个资源。')
        target=known[name]
        data=target.read_bytes()
        return Response(data if request.method=='GET' else b'',headers={'Content-Type':STATIC_CONTENT_TYPES[target.suffix],
            'Content-Length':str(len(data)),'Cache-Control':'no-cache'})

    async def asset(request: Request):
        relative='index.html' if request.url.path=='/' else request.url.path.lstrip('/')
        target=(FRONTEND/relative).resolve()
        if request.url.path not in STATIC_PATHS or not target.is_relative_to(FRONTEND.resolve()) or not target.is_file():
            raise service.APIError(404,'NOT_FOUND','没有找到这个资源。')
        data=target.read_bytes()
        return Response(data if request.method=='GET' else b'',headers={'Content-Type':STATIC_CONTENT_TYPES.get(target.suffix,'application/octet-stream'),
            'Content-Length':str(len(data)),'Cache-Control':'no-cache'})

    for route in sorted(STATIC_PATHS):
        app.add_api_route(route,asset,methods=['GET','HEAD'],include_in_schema=False)
    return app
