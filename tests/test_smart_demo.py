"""Verify the optional dataset and preserve pre-existing local data."""
from contextlib import closing
import hashlib
from pathlib import Path
import tempfile
import unittest

from backend.database import initialize_database
from backend.insights import merchant_analytics
from backend.smart_demo import create_smart_demo
from database.operations import connect


class SmartDemoTests(unittest.TestCase):
    def test_optional_demo_contains_valid_history_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            ordinary=Path(directory)/'ordinary.db'
            initialize_database(ordinary)
            original=hashlib.sha256(ordinary.read_bytes()).digest()
            create_smart_demo(ordinary)
            self.assertEqual(hashlib.sha256(ordinary.read_bytes()).digest(),original)
            rich=Path(directory)/'rich.db'
            create_smart_demo(rich)
            with closing(connect(rich)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM orders').fetchone()[0],114)
                self.assertEqual(db.execute('SELECT count(*) FROM reviews').fetchone()[0],78)
                self.assertFalse(db.execute('SELECT 1 FROM coupons c WHERE total_stock-available_stock != (SELECT count(*) FROM orders o WHERE o.coupon_id=c.coupon_id)').fetchone())
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
                a=merchant_analytics(db,{'user_id':'u-harbor'},{'storeId':['s1'],'days':['30']})
                self.assertGreaterEqual(a['sold'],27)
                self.assertGreater(sum(d['sold']>0 for d in a['trend']),5)
                self.assertEqual(a['offers'][0]['stock'],3)
                self.assertTrue(a['offers'][0]['lowStock'])
                self.assertGreater(a['redeemed'],0)
                self.assertGreater(a['expired'],0)
            original=hashlib.sha256(rich.read_bytes()).digest()
            create_smart_demo(rich)
            self.assertEqual(hashlib.sha256(rich.read_bytes()).digest(),original)
