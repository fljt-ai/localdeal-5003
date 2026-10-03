"""Independent integrity and transaction tests; all writes use temporary copies."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import init_db
import operations


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='localdeal-test-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'demo.db'
        self.today = datetime.now(operations.HK).date()
        init_db.create_database(self.path, demo_date=self.today)
        self.db = operations.connect(self.path)
        self.addCleanup(self.db.close)

    def scalar(self, sql, parameters=()):
        return self.db.execute(sql, parameters).fetchone()[0]

    def row(self, table, column, value):
        # Table and column names are test constants, never request values.
        return dict(self.db.execute(
            f'SELECT * FROM {table} WHERE {column} = ?', (value,)).fetchone())

    def rule(self, code, function, *args):
        with self.assertRaises(operations.DatabaseRuleError) as caught:
            function(self.db, *args)
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(self.db.in_transaction)

    def invalid_sql(self, sql, parameters=()):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(sql, parameters)

    def raw_order(self, identifier, coupon='c2', expires=None, purchased=None):
        offer = self.row('coupons', 'coupon_id', coupon)
        self.db.execute(
            'INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)',
            (identifier, 'u-demo', coupon, offer['title'], offer['price_cents'],
             offer['original_price_cents'], expires or offer['expires_on'],
             'LD-' + identifier.upper(), identifier, purchased or int(time.time())))
        return self.row('orders', 'order_id', identifier)

    def race(self, functions):
        barrier = threading.Barrier(len(functions))

        def worker(function):
            connection = operations.connect(self.path)
            try:
                barrier.wait(timeout=5)
                try:
                    return ('ok', function(connection))
                except operations.DatabaseRuleError as error:
                    return ('error', error.code)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            futures = [pool.submit(worker, function) for function in functions]
            return [future.result(timeout=15) for future in futures]

    def test_schema_seed_integrity_and_existing_file_preservation(self):
        self.assertEqual(self.scalar('PRAGMA foreign_keys'), 1)
        self.assertEqual(self.scalar('PRAGMA user_version'), 1)
        self.assertEqual(self.scalar('PRAGMA integrity_check'), 'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.scalar("SELECT count(*) FROM sqlite_master WHERE type='table'"), 15)
        self.assertEqual(self.scalar("SELECT count(*) FROM sqlite_master WHERE type='view'"), 3)
        for table, expected in [('users', 9), ('merchants', 3), ('stores', 6),
                                ('menu_items', 18), ('coupons', 6), ('reviews', 30),
                                ('orders', 3), ('redemptions', 1), ('favorites', 2)]:
            with self.subTest(table=table):
                self.assertEqual(self.scalar(f'SELECT count(*) FROM {table}'), expected)
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            init_db.create_database(self.path, demo_date=self.today)
        self.assertEqual(self.path.read_bytes(), before)
        missing = Path(self.directory.name) / 'missing.db'
        with self.assertRaises(sqlite3.OperationalError):
            operations.connect(missing)
        self.assertFalse(missing.exists())

    def test_unique_relationships_and_foreign_keys(self):
        statements = [
            ("INSERT INTO favorites(user_id,store_id) VALUES('u-demo','s1')", ()),
            ("INSERT INTO favorites(user_id,store_id) VALUES('missing','s1')", ()),
            ("INSERT INTO favorites(user_id,store_id) VALUES('u-demo','missing')", ()),
            ("INSERT INTO store_staff VALUES('s1','u-harbor','staff',1)", ()),
            ("INSERT INTO coupon_terms VALUES('c1',1,'duplicate position')", ()),
            ("INSERT INTO reviews(review_id,user_id,store_id,rating,comment) VALUES('duplicate','u-demo','s1',5,'Duplicate')", ()),
            ("INSERT INTO users(user_id,email,display_name) VALUES('duplicate','ALEX@EXAMPLE.COM','Duplicate')", ()),
            ("INSERT INTO store_tags VALUES('s1','missing tag',99)", ()),
        ]
        for sql, parameters in statements:
            with self.subTest(sql=sql):
                self.invalid_sql(sql, parameters)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_invalid_types_ranges_calendar_dates_and_blank_keys(self):
        statements = [
            "UPDATE coupons SET price_cents = -1 WHERE coupon_id='c1'",
            "UPDATE coupons SET price_cents = 1.5 WHERE coupon_id='c1'",
            "UPDATE coupons SET price_cents = original_price_cents + 1 WHERE coupon_id='c1'",
            "UPDATE coupons SET available_stock = -1 WHERE coupon_id='c1'",
            "UPDATE coupons SET available_stock = 1.5 WHERE coupon_id='c1'",
            "UPDATE coupons SET available_stock = total_stock + 1 WHERE coupon_id='c1'",
            "UPDATE coupons SET expires_on = '2026-02-30' WHERE coupon_id='c1'",
            "UPDATE coupons SET expires_on = '2026-13-01' WHERE coupon_id='c1'",
            "UPDATE coupons SET expires_on = '2026-2-01' WHERE coupon_id='c1'",
            "UPDATE reviews SET rating = 0 WHERE review_id='r-s1-1'",
            "UPDATE reviews SET rating = 4.5 WHERE review_id='r-s1-1'",
            "UPDATE reviews SET comment = '   ' WHERE review_id='r-s1-1'",
            "UPDATE store_staff SET is_active = 2 WHERE store_id='s1'",
            "UPDATE menu_items SET position = 0 WHERE menu_item_id='m-s1-1'",
            "INSERT INTO users(user_id,email,display_name) VALUES(NULL,'null@example.com','Null')",
            "INSERT INTO users(user_id,email,display_name) VALUES('   ','blank@example.com','Blank')",
        ]
        for sql in statements:
            with self.subTest(sql=sql):
                self.invalid_sql(sql)
        self.assertEqual(self.scalar('PRAGMA integrity_check'), 'ok')

    def test_purchase_decrements_once_and_preserves_sale_snapshots(self):
        offer = self.row('coupons', 'coupon_id', 'c2')
        order = operations.purchase_coupon(self.db, 'u-demo', 'c2', 'purchase-one')
        self.assertEqual(self.scalar("SELECT available_stock FROM coupons WHERE coupon_id='c2'"), offer['available_stock'] - 1)
        self.assertEqual(order['title_snapshot'], offer['title'])
        self.assertEqual(order['price_paid_cents'], offer['price_cents'])
        self.assertEqual(order['expires_on_snapshot'], offer['expires_on'])
        self.db.execute("UPDATE coupons SET title='Changed offer', price_cents=1, expires_on='2099-01-01' WHERE coupon_id='c2'")
        self.assertEqual(self.row('orders', 'order_id', order['order_id']), order)
        other = operations.purchase_coupon(self.db, 'u-demo', 'c2', 'purchase-two')
        self.assertNotEqual(other['order_id'], order['order_id'])
        self.assertNotEqual(other['redeem_code'], order['redeem_code'])
        self.assertEqual(other['price_paid_cents'], 1)

    def test_purchase_rejections_do_not_mutate_inventory_or_orders(self):
        old_day = (self.today - timedelta(days=1)).isoformat()
        cases = [
            ("UPDATE coupons SET available_stock=0 WHERE coupon_id='c2'", 'u-demo', 'c2', 'SOLD_OUT'),
            ("UPDATE coupons SET available_stock=24, expires_on=? WHERE coupon_id='c2'", 'u-demo', 'c2', 'EXPIRED'),
            ("UPDATE coupons SET expires_on='2099-01-01', is_active=0 WHERE coupon_id='c2'", 'u-demo', 'c2', 'NOT_AVAILABLE'),
            ("UPDATE coupons SET is_active=1 WHERE coupon_id='c2'", 'missing', 'c2', 'USER_NOT_FOUND'),
            (None, 'u-demo', 'missing', 'COUPON_NOT_FOUND'),
        ]
        for setup, user, coupon, code in cases:
            with self.subTest(code=code):
                if setup:
                    self.db.execute(setup, (old_day,) if '?' in setup else ())
                stock = self.scalar("SELECT available_stock FROM coupons WHERE coupon_id='c2'")
                count = self.scalar('SELECT count(*) FROM orders')
                self.rule(code, operations.purchase_coupon, user, coupon, 'reject-' + code)
                self.assertEqual(self.scalar('SELECT count(*) FROM orders'), count)
                self.assertEqual(self.scalar("SELECT available_stock FROM coupons WHERE coupon_id='c2'"), stock)
        self.db.execute("UPDATE stores SET is_active=0 WHERE store_id='s2'")
        self.rule('NOT_AVAILABLE', operations.purchase_coupon, 'u-demo', 'c2', 'inactive-store')
        for key in ['', '   ', 'x' * 129, None]:
            with self.subTest(key=key):
                self.rule('INVALID_KEY', operations.purchase_coupon, 'u-demo', 'c1', key)

    def test_purchase_insert_failure_rolls_back_inventory(self):
        self.db.executescript("""
            CREATE TRIGGER test_purchase_failure BEFORE INSERT ON orders
            WHEN NEW.idempotency_key = 'forced-failure'
            BEGIN SELECT RAISE(ABORT, 'injected order failure'); END;
        """)
        stock = self.scalar("SELECT available_stock FROM coupons WHERE coupon_id='c2'")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'injected order failure'):
            operations.purchase_coupon(self.db, 'u-demo', 'c2', 'forced-failure')
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.scalar("SELECT available_stock FROM coupons WHERE coupon_id='c2'"), stock)
        self.assertEqual(self.scalar("SELECT count(*) FROM orders WHERE idempotency_key='forced-failure'"), 0)
        self.db.execute('DROP TRIGGER test_purchase_failure')
        operations.purchase_coupon(self.db, 'u-demo', 'c2', 'forced-failure')
        self.assertEqual(self.scalar("SELECT available_stock FROM coupons WHERE coupon_id='c2'"), stock - 1)

    def test_idempotency_survives_sellout_expiry_and_is_scoped_per_user(self):
        order = operations.purchase_coupon(self.db, 'u-demo', 'c2', 'shared-key')
        self.db.execute("UPDATE coupons SET available_stock=0, expires_on=?, is_active=0 WHERE coupon_id='c2'", ((self.today - timedelta(days=1)).isoformat(),))
        self.assertEqual(operations.purchase_coupon(self.db, 'u-demo', 'c2', 'shared-key'), order)
        self.rule('RETRY_CONFLICT', operations.purchase_coupon, 'u-demo', 'c3', 'shared-key')
        self.assertEqual(self.scalar("SELECT available_stock FROM coupons WHERE coupon_id='c2'"), 0)
        other = operations.purchase_coupon(self.db, 'u-amy', 'c3', 'shared-key')
        self.assertNotEqual(other['order_id'], order['order_id'])
        self.assertEqual(other['user_id'], 'u-amy')
        self.assertEqual(self.scalar("SELECT count(*) FROM orders WHERE idempotency_key='shared-key'"), 2)

    def test_concurrent_last_unit_purchase_uses_independent_connections(self):
        self.db.execute("UPDATE coupons SET available_stock=1 WHERE coupon_id='c6'")
        results = self.race([
            lambda db: operations.purchase_coupon(db, 'u-demo', 'c6', 'race-one'),
            lambda db: operations.purchase_coupon(db, 'u-amy', 'c6', 'race-two'),
        ])
        self.assertEqual(sum(kind == 'ok' for kind, _ in results), 1, results)
        self.assertEqual([value for kind, value in results if kind == 'error'], ['SOLD_OUT'])
        self.assertEqual(self.scalar("SELECT available_stock FROM coupons WHERE coupon_id='c6'"), 0)
        self.assertEqual(self.scalar("SELECT count(*) FROM orders WHERE coupon_id='c6'"), 1)

    def test_redemption_normalizes_code_and_succeeds_only_once(self):
        result = operations.redeem_coupon(self.db, 'u-harbor', 's1', '  ld-harbor01  ')
        self.assertEqual(result['status'], 'redeemed')
        self.assertEqual(result['staff_user_id'], 'u-harbor')
        self.assertEqual(self.scalar("SELECT count(*) FROM redemptions WHERE order_id='o-demo-1'"), 1)
        self.rule('ALREADY_REDEEMED', operations.redeem_coupon, 'u-harbor', 's1', 'LD-HARBOR01')

    def test_redemption_staff_branch_expiry_and_future_purchase_rules(self):
        self.rule('FORBIDDEN', operations.redeem_coupon, 'u-demo', 's1', 'LD-HARBOR01')
        self.db.execute("UPDATE store_staff SET is_active=0 WHERE store_id='s1'")
        self.rule('FORBIDDEN', operations.redeem_coupon, 'u-harbor', 's1', 'LD-HARBOR01')
        self.db.execute("UPDATE store_staff SET is_active=1 WHERE store_id='s1'")
        self.rule('WRONG_STORE', operations.redeem_coupon, 'u-harbor', 's2', 'LD-HARBOR01')
        self.rule('EXPIRED', operations.redeem_coupon, 'u-coffee', 's5', 'LD-COFFEE03')
        future = self.raw_order('future-order', purchased=int(time.time()) + 3600)
        self.rule('EXPIRED', operations.redeem_coupon, 'u-harbor', 's2', future['redeem_code'])
        self.rule('CODE_NOT_FOUND', operations.redeem_coupon, 'u-harbor', 's1', 'LD-MISSING')
        self.assertEqual(self.scalar('SELECT count(*) FROM redemptions'), 1)

    def test_raw_redemption_insert_enforces_staff_and_snapshot_validity(self):
        order = self.row('orders', 'order_id', 'o-demo-1')
        self.invalid_sql('INSERT INTO redemptions VALUES(?,?,?)', ('o-demo-1', 'u-demo', int(time.time())))
        self.invalid_sql('INSERT INTO redemptions VALUES(?,?,?)', ('o-demo-1', 'u-coffee', int(time.time())))
        self.invalid_sql('INSERT INTO redemptions VALUES(?,?,?)', ('o-demo-1', 'u-harbor', order['purchased_at'] - 1))
        self.invalid_sql('INSERT INTO redemptions VALUES(?,?,?)', ('o-demo-3', 'u-coffee', int(time.time())))
        self.assertEqual(self.scalar('SELECT count(*) FROM redemptions'), 1)

    def test_redemption_insert_failure_leaves_voucher_unused(self):
        self.db.executescript("""
            CREATE TRIGGER test_redemption_failure BEFORE INSERT ON redemptions
            WHEN NEW.order_id = 'o-demo-1'
            BEGIN SELECT RAISE(ABORT, 'injected redemption failure'); END;
        """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'injected redemption failure'):
            operations.redeem_coupon(self.db, 'u-harbor', 's1', 'LD-HARBOR01')
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.scalar("SELECT status FROM wallet WHERE order_id='o-demo-1'"), 'unused')
        self.db.execute('DROP TRIGGER test_redemption_failure')
        self.assertEqual(operations.redeem_coupon(self.db, 'u-harbor', 's1', 'LD-HARBOR01')['status'], 'redeemed')

    def test_concurrent_redemption_creates_one_event(self):
        results = self.race([
            lambda db: operations.redeem_coupon(db, 'u-harbor', 's1', 'LD-HARBOR01'),
            lambda db: operations.redeem_coupon(db, 'u-harbor', 's1', 'LD-HARBOR01'),
        ])
        self.assertEqual(sum(kind == 'ok' for kind, _ in results), 1, results)
        self.assertEqual([value for kind, value in results if kind == 'error'], ['ALREADY_REDEEMED'])
        self.assertEqual(self.scalar("SELECT count(*) FROM redemptions WHERE order_id='o-demo-1'"), 1)

    def test_purchase_redemption_and_sold_coupon_branch_are_immutable(self):
        for sql in [
            "UPDATE orders SET user_id='u-amy' WHERE order_id='o-demo-1'",
            "UPDATE orders SET price_paid_cents=1 WHERE order_id='o-demo-1'",
            "DELETE FROM orders WHERE order_id='o-demo-1'",
            "UPDATE redemptions SET redeemed_at=redeemed_at+1 WHERE order_id='o-demo-2'",
            "DELETE FROM redemptions WHERE order_id='o-demo-2'",
            "UPDATE coupons SET store_id='s2' WHERE coupon_id='c1'",
            "DELETE FROM coupons WHERE coupon_id='c1'",
        ]:
            with self.subTest(sql=sql):
                self.invalid_sql(sql)
        self.assertEqual(self.scalar("SELECT user_id FROM orders WHERE order_id='o-demo-1'"), 'u-demo')
        self.assertEqual(self.scalar("SELECT store_id FROM wallet WHERE order_id='o-demo-1'"), 's1')

    def test_replace_cannot_bypass_history_guards_with_recursive_triggers_off(self):
        self.db.execute('PRAGMA recursive_triggers=OFF')
        self.assertEqual(self.scalar('PRAGMA recursive_triggers'), 0)
        original = self.row('orders', 'order_id', 'o-demo-1')
        columns = ','.join(original)
        replace = f'INSERT OR REPLACE INTO orders({columns}) VALUES({",".join("?" for _ in original)})'
        conflicts = [
            {'title_snapshot': 'Replacement'},
            {'order_id': 'new-order', 'idempotency_key': 'new-key'},
            {'order_id': 'new-order', 'redeem_code': 'LD-NEWCODE'},
        ]
        for edits in conflicts:
            with self.subTest(conflict=edits):
                changed = {**original, **edits}
                self.invalid_sql(replace, tuple(changed.values()))
                self.assertEqual(self.row('orders', 'order_id', 'o-demo-1'), original)
        redeemed = self.row('redemptions', 'order_id', 'o-demo-2')
        self.invalid_sql('INSERT OR REPLACE INTO redemptions VALUES(?,?,?)',
                         (redeemed['order_id'], redeemed['staff_user_id'], redeemed['redeemed_at'] + 1))
        self.assertEqual(self.row('redemptions', 'order_id', 'o-demo-2'), redeemed)

    def test_review_owner_crud_duplicate_rule_and_store_aggregates(self):
        before = self.row('store_summary', 'store_id', 's2')
        review = operations.save_review(self.db, 'u-demo', 's2', 1, '  New experience  ')
        self.assertEqual(review['comment'], 'New experience')
        self.rule('REVIEW_EXISTS', operations.save_review, 'u-demo', 's2', 5, 'Duplicate review')
        self.rule('FORBIDDEN', operations.save_review, 'u-amy', 's2', 5, 'Other author', review['review_id'])
        self.rule('FORBIDDEN', operations.save_review, 'u-demo', 's1', 5, 'Other store', review['review_id'])
        self.rule('FORBIDDEN', operations.delete_review, 'u-amy', review['review_id'])
        aggregate = self.row('store_summary', 'store_id', 's2')
        self.assertEqual(aggregate['review_count'], before['review_count'] + 1)
        expected = self.scalar("SELECT round(avg(rating),1) FROM reviews WHERE store_id='s2'")
        self.assertEqual(aggregate['average_rating'], expected)
        edited = operations.save_review(self.db, 'u-demo', 's2', 5, 'Updated experience', review['review_id'])
        self.assertEqual(edited['rating'], 5)
        self.assertEqual(edited['created_at'], review['created_at'])
        self.assertGreaterEqual(edited['updated_at'], edited['created_at'])
        operations.delete_review(self.db, 'u-demo', review['review_id'])
        self.assertEqual(self.row('store_summary', 'store_id', 's2')['review_count'], before['review_count'])
        self.rule('REVIEW_NOT_FOUND', operations.delete_review, 'u-demo', review['review_id'])
        for rating in [True, 0, 6, 3.5]:
            with self.subTest(rating=rating):
                self.rule('INVALID_RATING', operations.save_review, 'u-demo', 's2', rating, 'Valid comment')

    def test_wallet_user_isolation_status_precedence_and_zero_review_store(self):
        demo = operations.get_wallet(self.db, 'u-demo')
        self.assertEqual({row['status'] for row in demo}, {'unused', 'redeemed', 'expired'})
        self.assertEqual(operations.get_wallet(self.db, 'u-amy'), [])
        order = operations.purchase_coupon(self.db, 'u-amy', 'c2', 'other-user')
        self.assertEqual([row['order_id'] for row in operations.get_wallet(self.db, 'u-amy')], [order['order_id']])
        self.assertNotIn(order['order_id'], [row['order_id'] for row in operations.get_wallet(self.db, 'u-demo')])
        self.db.execute("DELETE FROM reviews WHERE store_id='s6'")
        empty = self.row('store_summary', 'store_id', 's6')
        self.assertEqual(empty['review_count'], 0)
        self.assertIsNone(empty['average_rating'])
        old_expiry = (self.today - timedelta(days=1)).isoformat()
        purchase_time = int(datetime.combine(self.today - timedelta(days=2), datetime.min.time(), operations.HK).timestamp())
        historical = self.raw_order('historic-redeemed', expires=old_expiry, purchased=purchase_time)
        self.db.execute('INSERT INTO redemptions VALUES(?,?,?)', (historical['order_id'], 'u-harbor', purchase_time + 1))
        self.assertEqual(self.scalar("SELECT status FROM wallet WHERE order_id='historic-redeemed'"), 'redeemed')

    def test_hong_kong_expiry_includes_entire_final_day(self):
        start = int(datetime.combine(self.today, datetime.min.time(), operations.HK).timestamp())
        end = start + 86400 - 1
        today_order = self.raw_order('today-order', expires=self.today.isoformat(), purchased=start)
        after_order = self.raw_order('after-order', expires=self.today.isoformat(), purchased=start)
        self.assertEqual(self.scalar("SELECT status FROM wallet WHERE order_id='today-order'"), 'unused')
        self.db.execute('INSERT INTO redemptions VALUES(?,?,?)', (today_order['order_id'], 'u-harbor', end))
        self.invalid_sql('INSERT INTO redemptions VALUES(?,?,?)', (after_order['order_id'], 'u-harbor', end + 1))
        self.assertEqual(self.scalar("SELECT status FROM wallet WHERE order_id='today-order'"), 'redeemed')
        self.assertEqual(self.scalar("SELECT status FROM wallet WHERE order_id='after-order'"), 'unused')


if __name__ == '__main__':
    unittest.main()
