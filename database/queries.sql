-- READ-ONLY examples. HKD amounts are integer cents; divide only for display.
PRAGMA foreign_keys = ON;

-- 1. Discovery: category + district filter; scores come from actual reviews.
SELECT store_id, name, district, category, price_per_person_cents / 100.0 AS price_hkd,
       average_rating, review_count
FROM store_summary
WHERE is_active = 1 AND district_id = 'central' AND category_id = 'cat-western'
ORDER BY average_rating DESC, store_id;

-- 2. Menu in display order.
SELECT name, description, price_cents / 100.0 AS price_hkd
FROM menu_items WHERE store_id = 's1' AND is_available = 1 ORDER BY position;

-- 3. Latest reviews. User name is joined rather than copied into each review.
SELECT r.review_id, u.display_name, r.rating, r.comment,
       datetime(r.created_at, 'unixepoch', '+8 hours') AS created_at_hk
FROM reviews r JOIN users u ON u.user_id = r.user_id
WHERE r.store_id = 's1' ORDER BY r.created_at DESC, r.review_id LIMIT 10;

-- 4. Saleable offers, with current inventory and full-day Hong Kong expiry.
SELECT coupon_id, store_name, title, price_cents / 100.0 AS price_hkd, available_stock, expires_on
FROM coupon_catalog WHERE is_purchasable = 1 ORDER BY price_cents, coupon_id;

-- 5. A customer's wallet: the backend must resolve the customer from the session.
SELECT order_id, store_name, title_snapshot, price_paid_cents / 100.0 AS price_hkd,
       redeem_code, status, expires_on_snapshot
FROM wallet WHERE user_id = 'u-demo' ORDER BY purchased_at DESC, order_id;

-- 6. Merchant sales summary. These are SIMULATED order amounts, not real revenue.
SELECT s.store_id, s.name, count(o.order_id) AS simulated_orders,
       coalesce(sum(o.price_paid_cents), 0) / 100.0 AS simulated_order_value_hkd,
       count(r.order_id) AS redeemed_orders
FROM stores s LEFT JOIN coupons c ON c.store_id = s.store_id
LEFT JOIN orders o ON o.coupon_id = c.coupon_id
LEFT JOIN redemptions r ON r.order_id = o.order_id
WHERE s.merchant_id = 'merchant-harbor' GROUP BY s.store_id ORDER BY s.store_id;

-- 7. Favorites are a many-to-many relation.
SELECT s.store_id, s.name, s.average_rating FROM favorites f
JOIN store_summary s ON s.store_id = f.store_id
WHERE f.user_id = 'u-demo' ORDER BY f.created_at DESC, s.store_id;

-- 8. Inspect the query plan; do not infer speed from this tiny sample alone.
EXPLAIN QUERY PLAN
SELECT review_id, rating, comment FROM reviews
WHERE store_id = 's1' ORDER BY created_at DESC, review_id LIMIT 10;

EXPLAIN QUERY PLAN
SELECT order_id FROM orders WHERE user_id = 'u-demo' ORDER BY purchased_at DESC, order_id LIMIT 20;

-- 9. Both checks should be clean: no rows for foreign keys, "ok" for integrity.
PRAGMA foreign_key_check;
PRAGMA integrity_check;
