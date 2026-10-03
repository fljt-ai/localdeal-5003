"""SQL-backed application service. Identity is resolved by server-side sessions."""
from datetime import datetime, timezone
from contextlib import contextmanager
import re
import time
import uuid

from database import operations
from .auth import DUMMY_HASH, hash_password, new_session_credentials, token_hash, verify_password

SESSION_SECONDS = 86400


class APIError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def text(value, label, minimum=1, maximum=500):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise APIError(400, 'INVALID_INPUT', f'{label}需为 {minimum}–{maximum} 个字符。')
    return value.strip()


def email_value(value):
    value = text(value, '邮箱', 3, 254).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise APIError(400, 'INVALID_EMAIL', '请输入有效的邮箱地址。')
    return value


def password_value(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise APIError(400, 'INVALID_PASSWORD', '密码需为 12–128 个字符。')
    return value


def fields(payload, required, optional=()):
    if not isinstance(payload, dict) or set(payload) - set(required) - set(optional) or set(required) - set(payload):
        raise APIError(400, 'INVALID_FIELDS', '请求字段缺失或包含不允许修改的字段。')


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace('+00:00', 'Z') if epoch is not None else None


def staff_stores(connection, user_id):
    return [r[0] for r in connection.execute(
        'SELECT store_id FROM store_staff WHERE user_id = ? AND is_active = 1 ORDER BY store_id', (user_id,))]


def user_object(connection, user_id):
    row = connection.execute('SELECT user_id,display_name,email FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if row is None:
        return None
    return {'id':row['user_id'], 'name':row['display_name'], 'email':row['email'],
            'merchantStoreIds':staff_stores(connection,user_id)}


def session_for_token(connection, raw_token):
    if not isinstance(raw_token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', raw_token):
        return None
    return connection.execute('SELECT * FROM sessions WHERE token_hash = ? AND expires_at > ?',
                              (token_hash(raw_token),int(time.time()))).fetchone()


def require_session(session):
    if session is None:
        raise APIError(401, 'UNAUTHENTICATED', '请先登录。')
    return session['user_id']


def make_session(connection, user_id, old_token=None):
    raw_token, csrf = new_session_credentials()
    now = int(time.time())
    if old_token and re.fullmatch(r'[A-Za-z0-9_-]{43}', old_token):
        connection.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash(old_token),))
    connection.execute('DELETE FROM sessions WHERE expires_at <= ?', (now,))
    connection.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',
                       (token_hash(raw_token),user_id,csrf,now,now+SESSION_SECONDS))
    return {'user':user_object(connection,user_id),'csrfToken':csrf}, raw_token


def login(connection, payload, old_token=None):
    fields(payload, ('email','password'))
    email = email_value(payload['email'])
    password = password_value(payload['password'])
    row = connection.execute('SELECT user_id,password_hash FROM users WHERE email = ?', (email,)).fetchone()
    valid = verify_password(password, row['password_hash'] if row and row['password_hash'] else DUMMY_HASH)
    if not row or not row['password_hash'] or not valid:
        raise APIError(401, 'INVALID_CREDENTIALS', '邮箱或密码不正确。')
    with operations.transaction(connection):
        return make_session(connection,row['user_id'],old_token)


def register(connection, payload, old_token=None):
    fields(payload, ('name','email','password'))
    name = text(payload['name'],'昵称',1,60)
    email = email_value(payload['email'])
    password = password_value(payload['password'])
    encoded = hash_password(password)
    with operations.transaction(connection):
        if connection.execute('SELECT 1 FROM users WHERE email = ?', (email,)).fetchone():
            raise APIError(409, 'EMAIL_EXISTS', '这个邮箱已注册，请使用登录。')
        user_id = 'u-' + uuid.uuid4().hex
        connection.execute('INSERT INTO users (user_id,email,display_name,password_hash) VALUES (?,?,?,?)',
                           (user_id,email,name,encoded))
        return make_session(connection,user_id,old_token)


def logout(connection, session):
    require_session(session)
    with operations.transaction(connection):
        connection.execute('DELETE FROM sessions WHERE token_hash = ?', (session['token_hash'],))
    return {'loggedOut':True}


def update_profile(connection, session, payload):
    fields(payload, ('name',))
    user_id = require_session(session)
    name = text(payload['name'],'昵称',1,60)
    with operations.transaction(connection):
        connection.execute('UPDATE users SET display_name = ? WHERE user_id = ?', (name,user_id))
    return user_object(connection,user_id)


@contextmanager
def read_snapshot(connection):
    """Keep list count, page and nested cards coherent without nesting writes."""
    started = not connection.in_transaction
    if started:
        connection.execute('BEGIN')
    try:
        yield
        if started:
            connection.execute('COMMIT')
    except BaseException:
        if started and connection.in_transaction:
            connection.execute('ROLLBACK')
        raise


def query_value(query, key, default=''):
    values = query.get(key)
    if values is None:
        return default
    if len(values) != 1:
        raise APIError(400,'INVALID_QUERY','同一筛选参数只能提供一次。')
    return values[0].strip()


def page_bounds(query, default=12):
    try:
        limit_value, offset_value = query_value(query,'limit',str(default)), query_value(query,'offset','0')
        if not re.fullmatch(r'[0-9]+',limit_value) or not re.fullmatch(r'[0-9]+',offset_value):
            raise ValueError()
        limit, offset = int(limit_value), int(offset_value)
        if not 1 <= limit <= 50 or not 0 <= offset <= 1000000:
            raise ValueError()
    except ValueError:
        raise APIError(400,'INVALID_PAGINATION','每页需为 1–50 条，起始位置需为 0–1000000。')
    return limit, offset


def page_result(items, total, limit, offset, **extra):
    return {'items':items,'total':total,'limit':limit,'offset':offset,
            'hasMore':offset+len(items)<total,**extra}


def enum_value(query, key, allowed, default):
    value = query_value(query,key,default)
    if value not in allowed:
        raise APIError(400,'INVALID_'+key.upper(),'筛选或排序参数无效。')
    return value


STORE_FROM = (' FROM stores s JOIN categories cat ON cat.category_id=s.category_id '
              'JOIN districts d ON d.district_id=s.district_id ')
STORE_SELECT = (
    'SELECT s.*,cat.name AS category,d.name AS district,'
    '(SELECT round(avg(r.rating),1) FROM reviews r WHERE r.store_id=s.store_id) AS average_rating,'
    '(SELECT count(*) FROM reviews r WHERE r.store_id=s.store_id) AS review_count,'
    'EXISTS (SELECT 1 FROM favorites f WHERE f.user_id=? AND f.store_id=s.store_id) AS is_favorite,'
    '(SELECT c.coupon_id FROM coupons c WHERE c.store_id=s.store_id AND c.is_active=1 '
    "AND c.available_stock>0 AND c.expires_on>=date('now','+8 hours') "
    'AND s.is_active=1 ORDER BY c.price_cents,c.coupon_id LIMIT 1) AS best_coupon_id'
)
COUPON_FROM = (' FROM coupons c JOIN stores s ON s.store_id=c.store_id '
               'JOIN districts d ON d.district_id=s.district_id ')
COUPON_SELECT = (
    'SELECT c.*,s.name AS store_name,d.name AS store_district,s.image_path AS store_image,'
    'CASE WHEN c.is_active=1 AND s.is_active=1 AND c.available_stock>0 '
    "AND c.expires_on>=date('now','+8 hours') THEN 1 ELSE 0 END AS is_purchasable"
)
REVIEW_SELECT = (
    'SELECT r.*,u.display_name,s.name AS store_name,d.name AS store_district,s.image_path AS store_image '
    'FROM reviews r JOIN users u ON u.user_id=r.user_id JOIN stores s ON s.store_id=r.store_id '
    'JOIN districts d ON d.district_id=s.district_id '
)
ORDER_SELECT = (
    'SELECT w.*,d.name AS store_district,s.image_path AS store_image '
    'FROM wallet w JOIN stores s ON s.store_id=w.store_id JOIN districts d ON d.district_id=s.district_id '
)


def coupon_object(connection, row):
    return {'id':row['coupon_id'],'storeId':row['store_id'],'title':row['title'],
            'description':row['description'],'originalPrice':row['original_price_cents']/100,
            'price':row['price_cents']/100,'stock':row['available_stock'],'expiresAt':row['expires_on'],
            'terms':[r[0] for r in connection.execute(
                'SELECT term FROM coupon_terms WHERE coupon_id=? ORDER BY position',(row['coupon_id'],))],
            'isPurchasable':bool(row['is_purchasable']),'storeName':row['store_name'],
            'storeDistrict':row['store_district'],'storeImage':row['store_image']}


def get_coupon(connection, coupon_id):
    row = connection.execute(COUPON_SELECT+COUPON_FROM+'WHERE c.coupon_id=?',(coupon_id,)).fetchone()
    if row is None:
        raise APIError(404,'COUPON_NOT_FOUND','这项优惠不存在。')
    return coupon_object(connection,row)


def store_object(connection, row, detail=False):
    identifier = row['store_id']
    tag_sql = 'SELECT tag FROM store_tags WHERE store_id=? ORDER BY position'
    if not detail:
        tag_sql += ' LIMIT 3'
    result = {'id':identifier,'name':row['name'],'englishName':row['english_name'],
              'category':row['category'],'district':row['district'],'address':row['address'],
              'hours':row['hours'],'description':row['description'],
              'pricePerPerson':row['price_per_person_cents']/100,'image':row['image_path'],
              'tags':[r[0] for r in connection.execute(tag_sql,(identifier,))],'menu':[],
              'averageRating':row['average_rating'],'reviewCount':row['review_count'],
              'isActive':bool(row['is_active']),'isFavorite':bool(row['is_favorite']),
              'coupon':get_coupon(connection,row['best_coupon_id']) if row['best_coupon_id'] else None}
    if detail:
        result['menu'] = [{'id':r['menu_item_id'],'name':r['name'],'description':r['description'],
                           'price':r['price_cents']/100} for r in connection.execute(
            'SELECT * FROM menu_items WHERE store_id=? AND is_available=1 ORDER BY position,menu_item_id',
            (identifier,))]
    return result


def require_store(connection, store_id):
    if not connection.execute('SELECT 1 FROM stores WHERE store_id=?',(store_id,)).fetchone():
        raise APIError(404,'STORE_NOT_FOUND','这家门店不存在。')


def get_store(connection, store_id, session=None):
    user_id = session['user_id'] if session else None
    with read_snapshot(connection):
        row = connection.execute(STORE_SELECT+STORE_FROM+'WHERE s.store_id=?',(user_id,store_id)).fetchone()
        if row is None:
            raise APIError(404,'STORE_NOT_FOUND','这家门店不存在。')
        return store_object(connection,row,detail=True)


def store_conditions(query):
    conditions, parameters = ['s.is_active=1'], []
    q = query_value(query,'q')
    if len(q)>100:
        raise APIError(400,'INVALID_SEARCH','搜索词最多 100 个字符。')
    if q:
        pattern = '%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        conditions.append(
            "(s.name LIKE ? ESCAPE '\\' OR s.english_name LIKE ? ESCAPE '\\' "
            "OR cat.name LIKE ? ESCAPE '\\' OR d.name LIKE ? ESCAPE '\\' "
            "OR EXISTS (SELECT 1 FROM menu_items m WHERE m.store_id=s.store_id AND m.is_available=1 "
            "AND m.name LIKE ? ESCAPE '\\') OR EXISTS (SELECT 1 FROM store_tags t "
            "WHERE t.store_id=s.store_id AND t.tag LIKE ? ESCAPE '\\'))")
        parameters.extend([pattern]*6)
    for key, identifier, alias in (('district','district_id','d'),('category','category_id','cat')):
        value = query_value(query,key)
        if len(value)>80:
            raise APIError(400,'INVALID_FILTER','分类或地区参数过长。')
        if value:
            conditions.append(f'(s.{identifier}=? OR {alias}.name=?)')
            parameters.extend([value,value])
    coupon_only = enum_value(query,'couponOnly',('true','false'),'false')
    if coupon_only == 'true':
        conditions.append('EXISTS (SELECT 1 FROM coupons c WHERE c.store_id=s.store_id AND c.is_active=1 '
                          "AND c.available_stock>0 AND c.expires_on>=date('now','+8 hours'))")
    return conditions, parameters


def stores_page(connection, session, query, favorites=False):
    limit, offset = page_bounds(query,12)
    sort = enum_value(query,'sort',('recommended','rating','price'),'recommended')
    conditions, parameters = store_conditions(query)
    user_id = require_session(session) if favorites else session['user_id'] if session else None
    if favorites:
        # Saved inactive stores still belong to this customer's collection;
        # retain their isActive flag and keep the profile total consistent.
        conditions.remove('s.is_active=1')
        conditions.append('EXISTS (SELECT 1 FROM favorites f WHERE f.user_id=? AND f.store_id=s.store_id)')
        parameters.append(user_id)
    where = 'WHERE '+' AND '.join(conditions)
    ordering = {'recommended':'s.store_id','rating':'average_rating DESC,s.store_id',
                'price':'s.price_per_person_cents,s.store_id'}[sort]
    with read_snapshot(connection):
        total = connection.execute('SELECT count(*)'+STORE_FROM+where,parameters).fetchone()[0]
        # The base WHERE is applied before these store-specific indexed review
        # subqueries. No global store_summary aggregate or all-review Python scan.
        rows = connection.execute(STORE_SELECT+STORE_FROM+where+' ORDER BY '+ordering+' LIMIT ? OFFSET ?',
                                  [user_id]+parameters+[limit,offset]).fetchall()
        return page_result([store_object(connection,row) for row in rows],total,limit,offset)


def coupons_page(connection, query):
    limit, offset = page_bounds(query,12)
    store_id = query_value(query,'storeId')
    if len(store_id)>80:
        raise APIError(400,'INVALID_FILTER','门店参数过长。')
    conditions, parameters = ['s.is_active=1','c.is_active=1'], []
    if store_id:
        require_store(connection,store_id)
        conditions.append('c.store_id=?')
        parameters.append(store_id)
    where = 'WHERE '+' AND '.join(conditions)
    with read_snapshot(connection):
        total = connection.execute('SELECT count(*)'+COUPON_FROM+where,parameters).fetchone()[0]
        rows = connection.execute(COUPON_SELECT+COUPON_FROM+where+' ORDER BY c.coupon_id LIMIT ? OFFSET ?',
                                  parameters+[limit,offset]).fetchall()
        return page_result([coupon_object(connection,row) for row in rows],total,limit,offset)


def review_object(row):
    return {'id':row['review_id'],'storeId':row['store_id'],'userId':row['user_id'],
            'userName':row['display_name'],'rating':row['rating'],'comment':row['comment'],
            'createdAt':iso(row['created_at']),'updatedAt':iso(row['updated_at']),
            'storeName':row['store_name'],'storeDistrict':row['store_district'],'storeImage':row['store_image']}


def get_review(connection, review_id):
    row = connection.execute(REVIEW_SELECT+'WHERE r.review_id=?',(review_id,)).fetchone()
    if row is None:
        raise APIError(404,'REVIEW_NOT_FOUND','这条点评不存在。')
    return review_object(row)


def reviews_page(connection, session, query, store_id=None, own=False):
    limit, offset = page_bounds(query,10)
    rating = enum_value(query,'rating',('all','1','2','3','4','5'),'all')
    sort = enum_value(query,'sort',('new','rating'),'new')
    user_id = require_session(session) if own else session['user_id'] if session else None
    conditions, parameters = [], []
    if store_id is not None:
        require_store(connection,store_id)
        conditions.append('r.store_id=?')
        parameters.append(store_id)
    if own:
        conditions.append('r.user_id=?')
        parameters.append(user_id)
    if rating != 'all':
        conditions.append('r.rating=?')
        parameters.append(int(rating))
    where = 'WHERE '+' AND '.join(conditions) if conditions else ''
    ordering = ('r.created_at DESC,r.review_id' if sort=='new'
                else 'r.rating DESC,r.created_at DESC,r.review_id')
    with read_snapshot(connection):
        total = connection.execute('SELECT count(*) FROM reviews r '+where,parameters).fetchone()[0]
        rows = connection.execute(REVIEW_SELECT+where+' ORDER BY '+ordering+' LIMIT ? OFFSET ?',
                                  parameters+[limit,offset]).fetchall()
        extra = {}
        if store_id is not None:
            own_row = connection.execute(REVIEW_SELECT+'WHERE r.store_id=? AND r.user_id=?',
                                         (store_id,user_id)).fetchone() if user_id else None
            extra['ownReview'] = review_object(own_row) if own_row else None
        return page_result([review_object(row) for row in rows],total,limit,offset,**extra)


def order_object(row):
    return {'id':row['order_id'],'userId':row['user_id'],'couponId':row['coupon_id'],
            'storeId':row['store_id'],'storeName':row['store_name'],'storeDistrict':row['store_district'],
            'storeImage':row['store_image'],'title':row['title_snapshot'],'price':row['price_paid_cents']/100,
            'originalPrice':row['original_price_cents_snapshot']/100,'code':row['redeem_code'],
            'status':row['status'],'purchasedAt':iso(row['purchased_at']),
            'expiresAt':row['expires_on_snapshot'],'redeemedAt':iso(row['redeemed_at'])}


def get_order(connection, order_id, user_id=None):
    where, parameters = 'WHERE w.order_id=?', [order_id]
    if user_id is not None:
        where += ' AND w.user_id=?'
        parameters.append(user_id)
    row = connection.execute(ORDER_SELECT+where,parameters).fetchone()
    if row is None:
        raise APIError(404,'ORDER_NOT_FOUND','没有找到你的这笔订单。')
    return order_object(row)


def orders_page(connection, session, query, merchant=False):
    user_id = require_session(session)
    limit, offset = page_bounds(query,10)
    status = enum_value(query,'status',('all','unused','redeemed','expired'),'all')
    parameters = [user_id]
    extra_join = ''
    if merchant:
        if not connection.execute('SELECT 1 FROM store_staff WHERE user_id=? AND is_active=1 LIMIT 1',
                                  (user_id,)).fetchone():
            raise APIError(403,'FORBIDDEN','你没有商户工作台权限。')
        # Start from the staff/user scope so SQLite can use idx_staff_user,
        # then idx_coupons_store_expiry and idx_orders_coupon. A correlated
        # EXISTS alone would scan every customer's order before filtering.
        extra_join = 'JOIN store_staff ss ON ss.store_id=w.store_id '
        conditions = ['ss.user_id=?','ss.is_active=1']
        store_id = query_value(query,'storeId')
        if len(store_id)>80:
            raise APIError(400,'INVALID_FILTER','门店参数过长。')
        if store_id:
            if not connection.execute('SELECT 1 FROM store_staff WHERE user_id=? AND store_id=? AND is_active=1',
                                      (user_id,store_id)).fetchone():
                raise APIError(403,'FORBIDDEN','你没有这家门店的工作台权限。')
            conditions.append('w.store_id=?')
            parameters.append(store_id)
    else:
        conditions = ['w.user_id=?']
    if status != 'all':
        conditions.append('w.status=?')
        parameters.append(status)
    where = 'WHERE '+' AND '.join(conditions)
    with read_snapshot(connection):
        total = connection.execute('SELECT count(*) FROM wallet w '+extra_join+where,parameters).fetchone()[0]
        rows = connection.execute(ORDER_SELECT+extra_join+where+' ORDER BY w.purchased_at DESC,w.order_id LIMIT ? OFFSET ?',
                                  parameters+[limit,offset]).fetchall()
        return page_result([order_object(row) for row in rows],total,limit,offset)


def state(connection, session):
    """Compact bootstrap; bulk collections must use their scoped page routes."""
    user_id = session['user_id'] if session else None
    summary = {'favorites':0,'reviews':0,'orders':{'all':0,'unused':0,'redeemed':0,'expired':0}}
    with read_snapshot(connection):
        result = {key:[] for key in ('stores','coupons','reviews','orders','favorites','merchantOrders')}
        result.update({'user':user_object(connection,user_id) if user_id else None,
                       'csrfToken':session['csrf_token'] if session else None,'summary':summary,
                       'categories':[{'id':r[0],'name':r[1]} for r in connection.execute(
                           'SELECT category_id,name FROM categories ORDER BY category_id')],
                       'districts':[{'id':r[0],'name':r[1]} for r in connection.execute(
                           'SELECT district_id,name FROM districts ORDER BY district_id')],
                       'featuredStore':None,'featuredCoupon':None})
        if user_id:
            summary['favorites'] = connection.execute('SELECT count(*) FROM favorites WHERE user_id=?',
                                                       (user_id,)).fetchone()[0]
            summary['reviews'] = connection.execute('SELECT count(*) FROM reviews WHERE user_id=?',
                                                     (user_id,)).fetchone()[0]
            for row in connection.execute('SELECT status,count(*) AS n FROM wallet WHERE user_id=? GROUP BY status',
                                          (user_id,)):
                summary['orders'][row['status']] = row['n']
                summary['orders']['all'] += row['n']
        featured = connection.execute('SELECT store_id FROM stores WHERE is_active=1 '
                                      'ORDER BY store_id LIMIT 1').fetchone()
        if featured:
            row = connection.execute(STORE_SELECT+STORE_FROM+'WHERE s.store_id=?',(user_id,featured[0])).fetchone()
            result['featuredStore'] = store_object(connection,row)
            result['featuredCoupon'] = result['featuredStore']['coupon']
        return result


def toggle_favorite(connection, session, payload):
    fields(payload, ('storeId',))
    user_id = require_session(session)
    store_id = text(payload['storeId'],'门店编号',1,80)
    with operations.transaction(connection):
        if not connection.execute('SELECT 1 FROM stores WHERE store_id = ?', (store_id,)).fetchone():
            raise APIError(404,'STORE_NOT_FOUND','这家门店不存在。')
        if connection.execute('SELECT 1 FROM favorites WHERE user_id = ? AND store_id = ?', (user_id,store_id)).fetchone():
            connection.execute('DELETE FROM favorites WHERE user_id = ? AND store_id = ?', (user_id,store_id))
            saved = False
        else:
            connection.execute('INSERT INTO favorites (user_id,store_id) VALUES (?,?)',(user_id,store_id))
            saved = True
    return {'storeId':store_id,'saved':saved}


def personal_export(connection, session):
    user_id = require_session(session)
    # Explicit export intentionally includes all of this customer's records,
    # independent of whichever pages the browser has loaded.
    with read_snapshot(connection):
        return {'user':user_object(connection,user_id),
                'orders':[order_object(row) for row in connection.execute(
                    ORDER_SELECT+'WHERE w.user_id=? ORDER BY w.purchased_at DESC,w.order_id',(user_id,))],
                'favorites':[r[0] for r in connection.execute('SELECT store_id FROM favorites WHERE user_id=? '
                                                            'ORDER BY created_at DESC,store_id',(user_id,))],
                'reviews':[review_object(row) for row in connection.execute(
                    REVIEW_SELECT+'WHERE r.user_id=? ORDER BY r.created_at DESC,r.review_id',(user_id,))],
                'metadata':{'exportedAt':iso(int(time.time())),'scope':'current-user','payment':'simulated'}}


RULE_MESSAGES = {
    'INVALID_KEY':(400,'请提供有效的购买重试标识。'), 'RETRY_CONFLICT':(409,'这个购买请求已用于另一项优惠。'),
    'USER_NOT_FOUND':(401,'用户不存在，请重新登录。'), 'COUPON_NOT_FOUND':(404,'这项优惠不存在。'),
    'NOT_AVAILABLE':(409,'这项优惠暂时不能购买。'), 'EXPIRED':(409,'优惠券已过期或不在有效期间。'),
    'SOLD_OUT':(409,'这项优惠已售罄。'), 'FORBIDDEN':(403,'你没有权限执行这项操作。'),
    'WRONG_STORE':(409,'这张券属于其他门店。'), 'ALREADY_REDEEMED':(409,'这张券已核销，不能重复使用。'),
    'CODE_NOT_FOUND':(404,'没有找到这个券码。'), 'INVALID_CODE':(400,'请输入有效券码。'),
    'INVALID_RATING':(400,'评分必须为 1–5 的整数。'), 'INVALID_COMMENT':(400,'点评需为 1–500 个字符。'),
    'STORE_NOT_FOUND':(404,'这家门店不存在。'), 'REVIEW_NOT_FOUND':(404,'这条点评不存在。'),
    'REVIEW_EXISTS':(409,'你已点评这家店，可以修改已有点评。'),
}


def map_rule(error):
    status, message = RULE_MESSAGES.get(error.code,(400,'操作不符合数据库规则。'))
    return APIError(status,error.code,message)
