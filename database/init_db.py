#!/usr/bin/env python3
"""Create a new LocalDeal database without replacing an existing file.

Python standard library only. Seed dates can be re-anchored for later demos.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent
HK = timezone(timedelta(hours=8))


def sql_literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def cents(value):
    amount = Decimal(str(value)) * 100
    if amount != amount.to_integral_value() or amount < 0:
        raise ValueError('Money must be nonnegative, with at most two decimal places')
    return int(amount)


def generate_seed_sql(demo_date=None):
    """Translate fictional frontend rows into normalized relations."""
    seed = json.loads((ROOT / 'data/frontend-seed.json').read_text(encoding='utf-8'))
    baseline = date(2026, 10, 2)
    anchor = demo_date or baseline
    offset = anchor - baseline
    anchor_time = int(datetime.combine(anchor, datetime.min.time(), HK).timestamp())

    def epoch(value):
        instant = datetime.fromisoformat(value.replace('Z', '+00:00')) + offset
        return int(instant.timestamp())

    def shifted_day(value):
        return (date.fromisoformat(value) + offset).isoformat()

    lines = [
        '-- LocalDeal fictional demo data. No real users or payments.',
        '-- Calendar anchor: ' + anchor.isoformat() + ' (Asia/Hong_Kong).',
        '-- Fresh DB only; historical orders are already included in inventory counts.',
        'PRAGMA foreign_keys = ON;', 'BEGIN IMMEDIATE;',
    ]

    def insert(table, columns, values):
        lines.append('INSERT INTO ' + table + ' (' + ', '.join(columns) + ') VALUES ('
                     + ', '.join(sql_literal(v) for v in values) + ');')

    for user in seed['users']:
        insert('users', ('user_id','email','display_name','password_hash','created_at'),
               (user['id'], user['email'].lower(), user['name'], None, anchor_time - 60*86400))

    brands = [
        ('merchant-harbor', 'u-harbor', 'Harbor Bites', 'harbor.owner@example.com', ['s1','s2']),
        ('merchant-dumpling', 'u-dumpling', 'Little Dumpling', 'dumpling.owner@example.com', ['s3','s4']),
        ('merchant-coffee', 'u-coffee', 'Daily Grind', 'coffee.owner@example.com', ['s5','s6']),
    ]
    brand_by_store = {}
    for merchant_id, owner_id, name, email, branches in brands:
        insert('users', ('user_id','email','display_name','password_hash','created_at'),
               (owner_id, email, name + ' Owner', None, anchor_time - 60*86400))
        insert('merchants', ('merchant_id','owner_user_id','name','contact_email','created_at'),
               (merchant_id, owner_id, name, email, anchor_time - 60*86400))
        for store_id in branches:
            brand_by_store[store_id] = (merchant_id, owner_id)

    category_ids = {'西式餐厅':'cat-western','亚洲料理':'cat-asian','咖啡烘焙':'cat-coffee'}
    district_ids = {'中环':'central','尖沙咀':'tsim-sha-tsui','铜锣湾':'causeway-bay'}
    for name, identifier in category_ids.items():
        insert('categories', ('category_id','name'), (identifier,name))
    for name, identifier in district_ids.items():
        insert('districts', ('district_id','name'), (identifier,name))
    for tag in sorted({tag for store in seed['stores'] for tag in store['tags']}):
        insert('tags', ('tag',), (tag,))
    for store in seed['stores']:
        merchant_id, owner_id = brand_by_store[store['id']]
        insert('stores', ('store_id','merchant_id','category_id','district_id','name','english_name',
                         'address','hours','description','price_per_person_cents','image_path','created_at'),
               (store['id'], merchant_id, category_ids[store['category']], district_ids[store['district']],
                store['name'], store['englishName'], store['address'], store['hours'], store['description'],
                cents(store['pricePerPerson']), store['image'], anchor_time - 60*86400))
        insert('store_staff', ('store_id','user_id','role'), (store['id'],owner_id,'owner'))
        for position, tag in enumerate(store['tags'], 1):
            insert('store_tags', ('store_id','tag','position'), (store['id'],tag,position))
        for position, item in enumerate(store['menu'], 1):
            insert('menu_items', ('menu_item_id','store_id','name','description','price_cents','position'),
                   (item['id'],store['id'],item['name'],item['description'],cents(item['price']),position))

    sold = Counter(order['couponId'] for order in seed['orders'])
    for coupon in seed['coupons']:
        insert('coupons', ('coupon_id','store_id','title','description','original_price_cents','price_cents',
                          'total_stock','available_stock','expires_on','created_at'),
               (coupon['id'],coupon['storeId'],coupon['title'],coupon['description'],cents(coupon['originalPrice']),
                cents(coupon['price']),coupon['stock']+sold[coupon['id']],coupon['stock'],
                shifted_day(coupon['expiresAt']),anchor_time - 60*86400))
        for position, term in enumerate(coupon['terms'], 1):
            # Payment is still simulated, but state is now in SQLite, not a browser.
            if '本演示不收取费用' in term:
                term = '课程演示不收取费用；购买和核销保存至本地演示数据库。'
            insert('coupon_terms', ('coupon_id','position','term'), (coupon['id'],position,term))
    for review in seed['reviews']:
        created = epoch(review['createdAt'])
        insert('reviews', ('review_id','store_id','user_id','rating','comment','created_at','updated_at'),
               (review['id'],review['storeId'],review['userId'],review['rating'],review['comment'],created,created))
    for favorite in seed['favorites']:
        insert('favorites', ('user_id','store_id','created_at'),
               (favorite['userId'],favorite['storeId'],anchor_time - 86400))
    for order in seed['orders']:
        insert('orders', ('order_id','user_id','coupon_id','title_snapshot','price_paid_cents',
                         'original_price_cents_snapshot','expires_on_snapshot','redeem_code','idempotency_key','purchased_at'),
               (order['id'],order['userId'],order['couponId'],order['title'],cents(order['price']),
                cents(order['originalPrice']),shifted_day(order['expiresAt']),order['code'],
                'seed-' + order['id'],epoch(order['purchasedAt'])))
        if order['status'] == 'redeemed':
            insert('redemptions', ('order_id','staff_user_id','redeemed_at'),
                   (order['id'],brand_by_store[order['storeId']][1],epoch(order['redeemedAt'])))
    lines.extend(['COMMIT;', ''])
    return '\n'.join(lines)


def create_database(path, demo_date=None):
    """Exclusive creation means an existing database is never overwritten."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb'):
        pass
    connection = None
    try:
        connection = sqlite3.connect(path)
        connection.execute('PRAGMA foreign_keys = ON')
        connection.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))
        connection.executescript(generate_seed_sql(demo_date))
        violations = connection.execute('PRAGMA foreign_key_check').fetchall()
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        if violations or integrity != 'ok':
            raise RuntimeError('Database verification failed')
        connection.close()
        connection = None
    except BaseException:
        if connection is not None:
            connection.close()
        path.unlink(missing_ok=True)
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description='Create a NEW LocalDeal SQLite demo database.')
    parser.add_argument('--path', type=Path, default=ROOT / 'localdeal.db')
    parser.add_argument('--demo-date', type=date.fromisoformat,
                        default=datetime.now(HK).date(), help='YYYY-MM-DD; defaults to today in Hong Kong')
    args = parser.parse_args()
    try:
        created = create_database(args.path, args.demo_date)
    except FileExistsError:
        parser.exit(1, 'Existing database preserved. Use --path with a NEW filename.\n')
    print('Created:', created)
    print('Seed anchor:', args.demo_date.isoformat(), '(Asia/Hong_Kong)')
    print('15 tables; 3 views; foreign-key and integrity checks passed.')


if __name__ == '__main__':
    main()
