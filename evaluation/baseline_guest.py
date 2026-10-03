"""Read-only guest assembly snapshot from the pre-pagination LocalDeal service.

Only public read functions are preserved, with their original SQL and fields.
The guest_state wrapper is the guest-only branch of former state(None).
This module is an evaluation baseline, never an application endpoint.
Original backend/service.py SHA-256: 3db881f55b2ede64dc88789e7555b9375adb40014bdfcbd144d78a4095bc04cf
"""
from datetime import datetime, timezone


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace('+00:00', 'Z') if epoch is not None else None


def store_objects(connection, store_ids=None):
    rows = connection.execute('SELECT * FROM store_summary ORDER BY store_id').fetchall()
    stores = []
    menus = {}
    tags = {}
    for row in connection.execute('SELECT * FROM menu_items WHERE is_available = 1 ORDER BY store_id,position'):
        menus.setdefault(row['store_id'],[]).append({'id':row['menu_item_id'],'name':row['name'],
                                                   'description':row['description'],'price':row['price_cents']/100})
    for row in connection.execute('SELECT * FROM store_tags ORDER BY store_id,position'):
        tags.setdefault(row['store_id'],[]).append(row['tag'])
    for row in rows:
        identifier = row['store_id']
        if store_ids is not None and identifier not in store_ids:
            continue
        stores.append({'id':identifier,'name':row['name'],'englishName':row['english_name'],
                       'category':row['category'],'district':row['district'],'address':row['address'],
                       'hours':row['hours'],'description':row['description'],
                       'pricePerPerson':row['price_per_person_cents']/100,'image':row['image_path'],
                       'tags':tags.get(identifier,[]),'menu':menus.get(identifier,[]),
                       'averageRating':row['average_rating'],'reviewCount':row['review_count'],
                       'isActive':bool(row['is_active'])})
    return stores


def coupon_objects(connection, store_id=None):
    terms = {}
    for row in connection.execute('SELECT * FROM coupon_terms ORDER BY coupon_id,position'):
        terms.setdefault(row['coupon_id'],[]).append(row['term'])
    sql = 'SELECT * FROM coupon_catalog'
    params = ()
    if store_id is not None:
        sql += ' WHERE store_id = ?'
        params = (store_id,)
    return [{'id':r['coupon_id'],'storeId':r['store_id'],'title':r['title'],'description':r['description'],
             'originalPrice':r['original_price_cents']/100,'price':r['price_cents']/100,
             'stock':r['available_stock'],'expiresAt':r['expires_on'],
             'terms':terms.get(r['coupon_id'],[]),'isPurchasable':bool(r['is_purchasable'])}
            for r in connection.execute(sql+' ORDER BY coupon_id',params)]


def review_objects(connection, store_id=None):
    sql = 'SELECT r.*,u.display_name FROM reviews r JOIN users u ON u.user_id = r.user_id'
    params = ()
    if store_id is not None:
        sql += ' WHERE r.store_id = ?'
        params = (store_id,)
    return [{'id':r['review_id'],'storeId':r['store_id'],'userId':r['user_id'],'userName':r['display_name'],
             'rating':r['rating'],'comment':r['comment'],'createdAt':iso(r['created_at']),
             'updatedAt':iso(r['updated_at'])} for r in connection.execute(sql+' ORDER BY r.created_at DESC,r.review_id',params)]

def guest_state(connection):
    connection.execute('BEGIN')
    try:
        result = {'stores':store_objects(connection),'coupons':coupon_objects(connection),
                  'reviews':review_objects(connection),'orders':[], 'favorites':[],
                  'user':None,'merchantOrders':[],'csrfToken':None}
        connection.execute('COMMIT')
        return result
    except BaseException:
        connection.execute('ROLLBACK')
        raise
