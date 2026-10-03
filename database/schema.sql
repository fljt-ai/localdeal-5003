-- LocalDeal schema v1. Run once in a NEW SQLite database.
-- Enable foreign keys separately on EVERY connection, before any transaction.
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE users (
    user_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(user_id)) BETWEEN 1 AND 80),
    email TEXT NOT NULL COLLATE NOCASE UNIQUE
        CHECK (email = trim(email) AND email LIKE '%_@_%._%'
               AND instr(email, ' ') = 0 AND length(email) <= 254),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 60),
    -- NULL means credentials have not been provisioned. NOT a working login.
    password_hash TEXT CHECK (password_hash IS NULL OR length(password_hash) >= 30),
    created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(created_at) = 'integer' AND created_at >= 0)
);

CREATE TABLE merchants (
    merchant_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(merchant_id)) BETWEEN 1 AND 80),
    owner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 100),
    contact_email TEXT NOT NULL CHECK (contact_email LIKE '%_@_%._%'),
    created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(created_at) = 'integer' AND created_at >= 0)
);

CREATE TABLE categories (
    category_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(category_id)) BETWEEN 1 AND 80),
    name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) BETWEEN 1 AND 60)
);

CREATE TABLE districts (
    district_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(district_id)) BETWEEN 1 AND 80),
    name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) BETWEEN 1 AND 60)
);

CREATE TABLE stores (
    store_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(store_id)) BETWEEN 1 AND 80),
    merchant_id TEXT NOT NULL REFERENCES merchants(merchant_id) ON DELETE RESTRICT,
    category_id TEXT NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,
    district_id TEXT NOT NULL REFERENCES districts(district_id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    english_name TEXT NOT NULL CHECK (length(trim(english_name)) BETWEEN 1 AND 120),
    address TEXT NOT NULL CHECK (length(trim(address)) BETWEEN 1 AND 250),
    hours TEXT NOT NULL CHECK (length(trim(hours)) BETWEEN 1 AND 250),
    description TEXT NOT NULL CHECK (length(trim(description)) BETWEEN 1 AND 2000),
    price_per_person_cents INTEGER NOT NULL
        CHECK (typeof(price_per_person_cents) = 'integer' AND price_per_person_cents >= 0),
    image_path TEXT NOT NULL CHECK (length(trim(image_path)) BETWEEN 1 AND 500),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (typeof(is_active) = 'integer' AND is_active IN (0,1)),
    created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(created_at) = 'integer' AND created_at >= 0)
);

CREATE TABLE store_staff (
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    role TEXT NOT NULL CHECK (role IN ('owner','manager','staff')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (typeof(is_active) = 'integer' AND is_active IN (0,1)),
    PRIMARY KEY (store_id, user_id)
);

CREATE TABLE menu_items (
    menu_item_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(menu_item_id)) BETWEEN 1 AND 80),
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    description TEXT NOT NULL CHECK (length(description) <= 1000),
    price_cents INTEGER NOT NULL CHECK (typeof(price_cents) = 'integer' AND price_cents >= 0),
    position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 1),
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (typeof(is_available) = 'integer' AND is_available IN (0,1)),
    UNIQUE (store_id, position)
);

CREATE TABLE tags (
    tag TEXT PRIMARY KEY NOT NULL CHECK (tag = trim(tag) AND length(tag) BETWEEN 1 AND 60)
);

CREATE TABLE store_tags (
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    tag TEXT NOT NULL REFERENCES tags(tag) ON DELETE RESTRICT,
    position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 1),
    PRIMARY KEY (store_id, tag),
    UNIQUE (store_id, position)
);

CREATE TABLE coupons (
    coupon_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(coupon_id)) BETWEEN 1 AND 80),
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE RESTRICT,
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 160),
    description TEXT NOT NULL CHECK (length(trim(description)) BETWEEN 1 AND 2000),
    original_price_cents INTEGER NOT NULL
        CHECK (typeof(original_price_cents) = 'integer' AND original_price_cents >= 0),
    price_cents INTEGER NOT NULL
        CHECK (typeof(price_cents) = 'integer' AND price_cents >= 0 AND price_cents <= original_price_cents),
    total_stock INTEGER NOT NULL CHECK (typeof(total_stock) = 'integer' AND total_stock >= 0),
    available_stock INTEGER NOT NULL
        CHECK (typeof(available_stock) = 'integer' AND available_stock BETWEEN 0 AND total_stock),
    expires_on TEXT NOT NULL CHECK (
        length(expires_on) = 10 AND expires_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date(expires_on, '+0 days') IS NOT NULL AND date(expires_on, '+0 days') = expires_on
    ),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (typeof(is_active) = 'integer' AND is_active IN (0,1)),
    created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(created_at) = 'integer' AND created_at >= 0)
);

CREATE TABLE coupon_terms (
    coupon_id TEXT NOT NULL REFERENCES coupons(coupon_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 1),
    term TEXT NOT NULL CHECK (length(trim(term)) BETWEEN 1 AND 1000),
    PRIMARY KEY (coupon_id, position)
);

CREATE TABLE reviews (
    review_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(review_id)) BETWEEN 1 AND 80),
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    rating INTEGER NOT NULL CHECK (typeof(rating) = 'integer' AND rating BETWEEN 1 AND 5),
    comment TEXT NOT NULL CHECK (length(trim(comment)) BETWEEN 1 AND 500),
    created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(created_at) = 'integer' AND created_at >= 0),
    updated_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(updated_at) = 'integer' AND updated_at >= created_at),
    UNIQUE (store_id, user_id)
);

CREATE TABLE favorites (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(created_at) = 'integer' AND created_at >= 0),
    PRIMARY KEY (user_id, store_id)
);

-- One order purchases one coupon; repeated purchases are separate orders.
-- Snapshot fields are sale-time facts and remain unchanged when the offer changes.
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(order_id)) BETWEEN 1 AND 80),
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    coupon_id TEXT NOT NULL REFERENCES coupons(coupon_id) ON DELETE RESTRICT,
    title_snapshot TEXT NOT NULL CHECK (length(trim(title_snapshot)) BETWEEN 1 AND 160),
    price_paid_cents INTEGER NOT NULL CHECK (typeof(price_paid_cents) = 'integer' AND price_paid_cents >= 0),
    original_price_cents_snapshot INTEGER NOT NULL CHECK (
        typeof(original_price_cents_snapshot) = 'integer' AND original_price_cents_snapshot >= price_paid_cents
    ),
    expires_on_snapshot TEXT NOT NULL CHECK (
        length(expires_on_snapshot) = 10
        AND expires_on_snapshot GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date(expires_on_snapshot, '+0 days') IS NOT NULL
        AND date(expires_on_snapshot, '+0 days') = expires_on_snapshot
    ),
    redeem_code TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (
        redeem_code = upper(trim(redeem_code)) AND length(redeem_code) BETWEEN 8 AND 64
        AND redeem_code NOT GLOB '*[^A-Z0-9-]*'
    ),
    idempotency_key TEXT NOT NULL CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 128),
    purchased_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(purchased_at) = 'integer' AND purchased_at >= 0),
    CHECK (date(purchased_at, 'unixepoch', '+8 hours') IS NOT NULL
           AND expires_on_snapshot >= date(purchased_at, 'unixepoch', '+8 hours')),
    UNIQUE (user_id, idempotency_key)
);

-- The order_id primary key permits at most one redemption per purchased coupon.
CREATE TABLE redemptions (
    order_id TEXT PRIMARY KEY NOT NULL REFERENCES orders(order_id) ON DELETE RESTRICT,
    staff_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    redeemed_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
        CHECK (typeof(redeemed_at) = 'integer' AND redeemed_at >= 0)
);

CREATE INDEX idx_merchants_owner ON merchants(owner_user_id);
CREATE INDEX idx_stores_merchant ON stores(merchant_id);
CREATE INDEX idx_stores_district_category ON stores(district_id, category_id, is_active);
CREATE INDEX idx_stores_category ON stores(category_id);
CREATE INDEX idx_staff_user ON store_staff(user_id, is_active);
CREATE INDEX idx_store_tags_tag ON store_tags(tag);
CREATE INDEX idx_coupons_store_expiry ON coupons(store_id, is_active, expires_on);
CREATE INDEX idx_reviews_store_created ON reviews(store_id, created_at DESC, review_id);
CREATE INDEX idx_reviews_user ON reviews(user_id);
CREATE INDEX idx_favorites_store ON favorites(store_id);
CREATE INDEX idx_orders_user_purchased ON orders(user_id, purchased_at DESC, order_id);
CREATE INDEX idx_orders_coupon ON orders(coupon_id);
CREATE INDEX idx_redemptions_staff_time ON redemptions(staff_user_id, redeemed_at DESC);

-- A coupon with historical sales must stay associated with the same branch.
CREATE TRIGGER coupons_keep_store BEFORE UPDATE OF store_id ON coupons
WHEN NEW.store_id <> OLD.store_id AND EXISTS (SELECT 1 FROM orders WHERE coupon_id = OLD.coupon_id)
BEGIN
    SELECT RAISE(ABORT, 'A sold coupon cannot move to another store');
END;

CREATE TRIGGER orders_no_update BEFORE UPDATE ON orders
BEGIN
    SELECT RAISE(ABORT, 'Purchase history is immutable');
END;

CREATE TRIGGER orders_no_delete BEFORE DELETE ON orders
BEGIN
    SELECT RAISE(ABORT, 'Purchase history is immutable');
END;

-- Guard REPLACE as well: its implicit deletes need not run DELETE triggers.
CREATE TRIGGER orders_no_replace BEFORE INSERT ON orders
WHEN EXISTS (
    SELECT 1 FROM orders o WHERE o.order_id = NEW.order_id
        OR o.redeem_code = NEW.redeem_code
        OR (o.user_id = NEW.user_id AND o.idempotency_key = NEW.idempotency_key)
)
BEGIN
    SELECT RAISE(ABORT, 'Existing purchases cannot be replaced');
END;

CREATE TRIGGER redemptions_validate BEFORE INSERT ON redemptions
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM orders o JOIN coupons c ON c.coupon_id = o.coupon_id
        JOIN store_staff ss ON ss.store_id = c.store_id
        WHERE o.order_id = NEW.order_id AND ss.user_id = NEW.staff_user_id AND ss.is_active = 1
    ) THEN RAISE(ABORT, 'Staff is not authorized for this store') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM orders o WHERE o.order_id = NEW.order_id
        AND NEW.redeemed_at >= o.purchased_at
        AND date(NEW.redeemed_at, 'unixepoch', '+8 hours') <= o.expires_on_snapshot
    ) THEN RAISE(ABORT, 'Redemption is outside the purchase validity period') END;
END;

CREATE TRIGGER redemptions_no_update BEFORE UPDATE ON redemptions
BEGIN
    SELECT RAISE(ABORT, 'Redemption history is immutable');
END;

CREATE TRIGGER redemptions_no_delete BEFORE DELETE ON redemptions
BEGIN
    SELECT RAISE(ABORT, 'Redemption history is immutable');
END;

CREATE TRIGGER redemptions_no_replace BEFORE INSERT ON redemptions
WHEN EXISTS (SELECT 1 FROM redemptions WHERE order_id = NEW.order_id)
BEGIN
    SELECT RAISE(ABORT, 'Existing redemptions cannot be replaced');
END;

CREATE VIEW store_summary AS
SELECT s.store_id, s.merchant_id, s.name, s.english_name, s.category_id, cat.name AS category,
       s.district_id, d.name AS district, s.address, s.hours, s.description,
       s.price_per_person_cents, s.image_path, s.is_active,
       count(r.review_id) AS review_count, round(avg(r.rating), 1) AS average_rating
FROM stores s
JOIN categories cat ON cat.category_id = s.category_id
JOIN districts d ON d.district_id = s.district_id
LEFT JOIN reviews r ON r.store_id = s.store_id
GROUP BY s.store_id;

CREATE VIEW coupon_catalog AS
SELECT c.*, s.name AS store_name, s.district_id, s.category_id,
       CASE WHEN c.is_active = 1 AND s.is_active = 1 AND c.available_stock > 0
                 AND c.expires_on >= date('now', '+8 hours') THEN 1 ELSE 0 END AS is_purchasable
FROM coupons c JOIN stores s ON s.store_id = c.store_id;

CREATE VIEW wallet AS
SELECT o.order_id, o.user_id, o.coupon_id, c.store_id, s.name AS store_name,
       o.title_snapshot, o.price_paid_cents, o.original_price_cents_snapshot,
       o.redeem_code, o.purchased_at, o.expires_on_snapshot, r.redeemed_at,
       r.staff_user_id,
       CASE WHEN r.order_id IS NOT NULL THEN 'redeemed'
            WHEN o.expires_on_snapshot < date('now', '+8 hours') THEN 'expired'
            ELSE 'unused' END AS status
FROM orders o JOIN coupons c ON c.coupon_id = o.coupon_id
JOIN stores s ON s.store_id = c.store_id
LEFT JOIN redemptions r ON r.order_id = o.order_id;

PRAGMA user_version = 1;
COMMIT;
