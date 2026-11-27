"""Shared application controller; HTTP transports are deliberately independent of business operations."""
import re
from database import operations
from . import service, insights

COOKIE_NAME = 'localdeal_session'

def cookie_header(token, clear=False):
    age = 0 if clear else service.SESSION_SECONDS
    return f'{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}'

def dispatch_api(method, limiter, client_ip, connection, session, raw_token, path, query, payload):
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
            limiter_key = (client_ip,str(payload.get('email','')).strip().lower())
            if path.endswith('/register'):
                limiter_key = (client_ip,'registration')
            limiter.attempt(limiter_key)
            action = service.login if path.endswith('/login') else service.register
            data, token = action(connection,payload,raw_token)
            if path.endswith('/login'):
                limiter.clear(limiter_key)
            return data,201 if path.endswith('/register') else 200,cookie_header(token)
        if path == '/api/auth/logout':
            service.fields(payload,())
            return service.logout(connection,session),200,cookie_header('',clear=True)
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
        stock_match = re.fullmatch(r'/api/merchant/coupons/([^/]+)/stock',path)
        if stock_match:
            return service.adjust_coupon_stock(connection,session,stock_match[1],payload),200,None
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

