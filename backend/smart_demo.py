"""Optional clearly fictional, richer demo data; never modify an existing DB."""
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import os
import random
import tempfile

from database import operations
from .database import initialize_database


def create_smart_demo(path):
    path=Path(path).resolve()
    if path.exists():
        return path
    path.parent.mkdir(parents=True,exist_ok=True)
    rng=random.Random(5003)
    now=datetime.now(operations.HK)
    with tempfile.TemporaryDirectory(prefix='localdeal-smart-seed-',dir=path.parent) as directory:
        staged=Path(directory)/'smart.db'
        initialize_database(staged)
        with closing(operations.connect(staged)) as db, operations.transaction(db):
            buyers=[f'u-smart-{i:02}' for i in range(36)]
            created=int((now-timedelta(days=60)).timestamp())
            db.executemany('INSERT INTO users(user_id,email,display_name,created_at) VALUES (?,?,?,?)',
                [(uid,f'{uid}@example.com',f'Fictional diner {i+1}',created) for i,uid in enumerate(buyers)])
            serial=0
            targets={'c1':27,'c2':15,'c3':25,'c4':12,'c5':14,'c6':18}
            for coupon in db.execute('SELECT * FROM coupons ORDER BY coupon_id').fetchall():
                cid,store=coupon['coupon_id'],coupon['store_id']
                staff=db.execute('SELECT user_id FROM store_staff WHERE store_id=? AND is_active=1 ORDER BY user_id',(store,)).fetchone()[0]
                n=min(targets[cid],coupon['available_stock'])
                for i in range(n):
                    serial+=1
                    # Include recent and older dates to make both windows useful;
                    # generate only historical records, all within valid snapshots.
                    days_ago=1+i%7 if i<n//2 else 8+(i*3)%22
                    purchase=now-timedelta(days=days_ago,hours=rng.randint(0,8))
                    expiry=purchase.date()+timedelta(days=7 if i%4==0 else 21)
                    ordered=int(purchase.timestamp())
                    oid=f'o-smart-{serial:04}'
                    db.execute('''INSERT INTO orders(order_id,user_id,coupon_id,title_snapshot,price_paid_cents,
                      original_price_cents_snapshot,expires_on_snapshot,redeem_code,idempotency_key,purchased_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?)''',(oid,buyers[(serial*7)%len(buyers)],cid,coupon['title'],
                       coupon['price_cents'],coupon['original_price_cents'],expiry.isoformat(),
                       f'LD-SMART-{serial:04}',f'smart-fixture-{serial:04}',ordered))
                    if i%3!=0:
                        redeemed=int((purchase+timedelta(hours=6)).timestamp())
                        db.execute('INSERT INTO redemptions(order_id,staff_user_id,redeemed_at) VALUES (?,?,?)',
                            (oid,staff,redeemed))
                changed=db.execute('UPDATE coupons SET available_stock=available_stock-? WHERE coupon_id=? AND available_stock>=?',(n,cid,n)).rowcount
                assert changed==1
                for i in range(8):
                    message=('Fictional demo review: enjoyable meal and good value.' if i%3 else 'Fictional demo review: pleasant food, some room for improvement.')
                    reviewed=int((now-timedelta(days=1+i*3,hours=2)).timestamp())
                    db.execute('INSERT INTO reviews(review_id,store_id,user_id,rating,comment,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                        (f'r-smart-{store}-{i}',store,buyers[i],rng.choice((3,4,4,5,5)),message,reviewed,reviewed))
            assert not db.execute('SELECT 1 FROM coupons c WHERE total_stock-available_stock != (SELECT count(*) FROM orders o WHERE o.coupon_id=c.coupon_id)').fetchone()
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        # Publish the completed file without replacing any concurrently created
        # destination. Both paths are on the same filesystem.
        try:
            os.link(staged,path)
        except FileExistsError:
            pass
    return path
