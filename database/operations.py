"""Database operations for a future backend; not an HTTP server or authentication.

Callers must authenticate users and supply server-resolved IDs. Request fields
cannot establish identity. Time is always read here; prices are always read from DB.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

HK = timezone(timedelta(hours=8))


class DatabaseRuleError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def connect(path):
    """Open an existing DB; never silently create an empty database."""
    uri = Path(path).resolve().as_uri() + '?mode=rw'
    connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 5000')
    return connection


@contextmanager
def transaction(connection):
    """Serialize writes, roll back all effects on any failure."""
    if connection.in_transaction:
        raise RuntimeError('Operation requires an idle connection, not a nested transaction')
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.execute('COMMIT')
    except BaseException:
        if connection.in_transaction:
            connection.execute('ROLLBACK')
        raise


def today_hk(now):
    return datetime.fromtimestamp(now, HK).date().isoformat()


def require_user(connection, user_id):
    if not connection.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,)).fetchone():
        raise DatabaseRuleError('USER_NOT_FOUND', 'User does not exist')


def adjust_coupon_stock(connection, user_id, coupon_id, stock, expected):
    """Set unsold stock atomically; never change the number already sold."""
    if type(stock) is not int or type(expected) is not int or not 0 <= stock <= 100000 or not 0 <= expected <= 100000:
        raise DatabaseRuleError('INVALID_STOCK','Invalid stock')
    with transaction(connection):
        row=connection.execute('''SELECT c.available_stock FROM coupons c
            JOIN store_staff ss ON ss.store_id=c.store_id
            WHERE c.coupon_id=? AND ss.user_id=? AND ss.is_active=1 AND ss.role IN ('owner','manager')''',
            (coupon_id,user_id)).fetchone()
        if row is None:
            raise DatabaseRuleError('FORBIDDEN','Stock management is restricted to branch owners/managers')
        if row['available_stock']!=expected:
            raise DatabaseRuleError('STOCK_CHANGED','Stock changed since display')
        connection.execute('UPDATE coupons SET available_stock=?,total_stock=total_stock+? WHERE coupon_id=?',
                           (stock,stock-expected,coupon_id))


def purchase_coupon(connection, user_id, coupon_id, idempotency_key):
    """One unit/order. A retry key returns the same order without charging stock twice."""
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key.strip()) <= 128:
        raise DatabaseRuleError('INVALID_KEY', 'A nonempty retry key of up to 128 characters is required')
    if len(idempotency_key) > 128:
        raise DatabaseRuleError('INVALID_KEY', 'Retry key is too long')
    with transaction(connection):
        require_user(connection, user_id)
        existing = connection.execute(
            'SELECT * FROM orders WHERE user_id = ? AND idempotency_key = ?',
            (user_id, idempotency_key)).fetchone()
        if existing is not None:
            if existing['coupon_id'] != coupon_id:
                raise DatabaseRuleError('RETRY_CONFLICT', 'Retry key already belongs to a different coupon')
            return dict(existing)
        now = int(time.time())
        coupon = connection.execute(
            'SELECT c.*, s.is_active AS store_is_active FROM coupons c '
            'JOIN stores s ON s.store_id = c.store_id WHERE c.coupon_id = ?', (coupon_id,)).fetchone()
        if coupon is None:
            raise DatabaseRuleError('COUPON_NOT_FOUND', 'Coupon does not exist')
        if not coupon['is_active'] or not coupon['store_is_active']:
            raise DatabaseRuleError('NOT_AVAILABLE', 'Coupon or store is inactive')
        if coupon['expires_on'] < today_hk(now):
            raise DatabaseRuleError('EXPIRED', 'Coupon has expired')
        changed = connection.execute(
            'UPDATE coupons SET available_stock = available_stock - 1 '
            'WHERE coupon_id = ? AND available_stock > 0 AND is_active = 1 AND expires_on >= ?',
            (coupon_id, today_hk(now))).rowcount
        if changed != 1:
            raise DatabaseRuleError('SOLD_OUT', 'Coupon is sold out')
        order_id = 'o-' + uuid.uuid4().hex
        code = 'LD-' + secrets.token_hex(12).upper()
        connection.execute(
            'INSERT INTO orders (order_id,user_id,coupon_id,title_snapshot,price_paid_cents,'
            'original_price_cents_snapshot,expires_on_snapshot,redeem_code,idempotency_key,purchased_at) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)',
            (order_id,user_id,coupon_id,coupon['title'],coupon['price_cents'],coupon['original_price_cents'],
             coupon['expires_on'],code,idempotency_key,now))
        return dict(connection.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,)).fetchone())


def redeem_coupon(connection, staff_user_id, store_id, code):
    """Only active staff at the specified branch can redeem a matching valid order."""
    if not isinstance(code, str) or not code.strip():
        raise DatabaseRuleError('INVALID_CODE', 'A coupon code is required')
    normalized_code = code.strip().upper()
    with transaction(connection):
        require_user(connection, staff_user_id)
        if not connection.execute(
            'SELECT 1 FROM store_staff WHERE store_id = ? AND user_id = ? AND is_active = 1',
            (store_id,staff_user_id)).fetchone():
            raise DatabaseRuleError('FORBIDDEN', 'Staff is not authorized for this store')
        order = connection.execute(
            'SELECT o.*, c.store_id FROM orders o JOIN coupons c ON c.coupon_id = o.coupon_id '
            'WHERE o.redeem_code = ?', (normalized_code,)).fetchone()
        if order is None:
            raise DatabaseRuleError('CODE_NOT_FOUND', 'Coupon code does not exist')
        if order['store_id'] != store_id:
            raise DatabaseRuleError('WRONG_STORE', 'Coupon belongs to another store')
        if connection.execute('SELECT 1 FROM redemptions WHERE order_id = ?', (order['order_id'],)).fetchone():
            raise DatabaseRuleError('ALREADY_REDEEMED', 'Coupon has already been redeemed')
        now = int(time.time())
        if order['purchased_at'] > now or order['expires_on_snapshot'] < today_hk(now):
            raise DatabaseRuleError('EXPIRED', 'Coupon is outside its validity period')
        connection.execute('INSERT INTO redemptions (order_id,staff_user_id,redeemed_at) VALUES (?,?,?)',
                           (order['order_id'],staff_user_id,now))
        return dict(connection.execute('SELECT * FROM wallet WHERE order_id = ?', (order['order_id'],)).fetchone())


def save_review(connection, user_id, store_id, rating, comment, review_id=None):
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise DatabaseRuleError('INVALID_RATING', 'Rating must be an integer from 1 to 5')
    if not isinstance(comment, str) or not 1 <= len(comment.strip()) <= 500:
        raise DatabaseRuleError('INVALID_COMMENT', 'Comment must contain 1 to 500 characters')
    with transaction(connection):
        require_user(connection, user_id)
        if not connection.execute('SELECT 1 FROM stores WHERE store_id = ?', (store_id,)).fetchone():
            raise DatabaseRuleError('STORE_NOT_FOUND', 'Store does not exist')
        now = int(time.time())
        if review_id is not None:
            original = connection.execute('SELECT * FROM reviews WHERE review_id = ?', (review_id,)).fetchone()
            if original is None:
                raise DatabaseRuleError('REVIEW_NOT_FOUND', 'Review does not exist')
            if original['user_id'] != user_id or original['store_id'] != store_id:
                raise DatabaseRuleError('FORBIDDEN', 'Only the author can modify a review for its original store')
            connection.execute('UPDATE reviews SET rating = ?, comment = ?, updated_at = ? WHERE review_id = ?',
                               (rating,comment.strip(),max(now,original['created_at']),review_id))
        else:
            if connection.execute('SELECT 1 FROM reviews WHERE user_id = ? AND store_id = ?', (user_id,store_id)).fetchone():
                raise DatabaseRuleError('REVIEW_EXISTS', 'One review per user per store; update the existing review')
            review_id = 'r-' + uuid.uuid4().hex
            connection.execute('INSERT INTO reviews (review_id,user_id,store_id,rating,comment,created_at,updated_at) '
                               'VALUES (?,?,?,?,?,?,?)', (review_id,user_id,store_id,rating,comment.strip(),now,now))
        return dict(connection.execute('SELECT * FROM reviews WHERE review_id = ?', (review_id,)).fetchone())


def delete_review(connection, user_id, review_id):
    with transaction(connection):
        require_user(connection, user_id)
        row = connection.execute('SELECT user_id FROM reviews WHERE review_id = ?', (review_id,)).fetchone()
        if row is None:
            raise DatabaseRuleError('REVIEW_NOT_FOUND', 'Review does not exist')
        if row['user_id'] != user_id:
            raise DatabaseRuleError('FORBIDDEN', 'Only the author can delete a review')
        connection.execute('DELETE FROM reviews WHERE review_id = ?', (review_id,))


def get_wallet(connection, user_id):
    require_user(connection, user_id)
    return [dict(row) for row in connection.execute(
        'SELECT * FROM wallet WHERE user_id = ? ORDER BY purchased_at DESC, order_id', (user_id,))]
