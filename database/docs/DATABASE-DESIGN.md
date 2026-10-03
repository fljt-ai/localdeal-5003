# LocalDeal database design notes

These notes explain the LocalDeal database and support the student's own analysis. `schema.sql` defines the unchanged core v1 schema: 15 tables, 19 foreign keys and 3 views. The full application v2 applies `migration_v2.sql` to add the `sessions` table, giving 16 tables and 20 foreign keys. `er-diagram.svg` shows core v1 only; `ER-DIAGRAM.md` shows the complete v2 Mermaid diagram. These notes are reference material rather than a finished coursework report.

## Scope

The core database models customers, merchant ownership, store staff, discovery, menus, reviews, favourites, coupon offers, purchases and redemption. The full application connects the browser through a minimal Python standard-library HTTP server to SQLite. Password authentication, server-managed same-origin session cookies, CSRF checks and user/store authorization are implemented in `backend/`. Payment is simulated. The server binds to `127.0.0.1`; static frontend files and API routes share the same origin.

## Relations and keys

| Relation | Key and relationship | Responsibility |
| --- | --- | --- |
| `users` | Primary key `user_id`; unique email | Customer and staff identities; `password_hash` stores a password credential, while `NULL` disables password login |
| `merchants` | Primary key `merchant_id`; `owner_user_id` references `users` | Merchant ownership |
| `categories` | Primary key `category_id` | Reusable store category names |
| `districts` | Primary key `district_id` | Reusable Hong Kong district names |
| `stores` | Primary key `store_id`; foreign keys to `merchants`, `categories`, `districts` | Store identity, contact and descriptive information |
| `store_staff` | Composite primary key (`store_id`, `user_id`); both columns are foreign keys | Staff membership, role and active flag per store |
| `menu_items` | Primary key `menu_item_id`; foreign key to `stores`; unique (`store_id`, `position`) | Individual menu items, integer-cent prices and display order |
| `tags` | Primary key `tag` | Reusable discovery labels; the label text itself is the natural key |
| `store_tags` | Composite primary key (`store_id`, `tag`); unique (`store_id`, `position`) | Many-to-many relationship between stores and tags, retaining display order |
| `coupons` | Primary key `coupon_id`; foreign key to `stores` | Current offer details, price, stock and calendar expiry |
| `coupon_terms` | Composite primary key (`coupon_id`, `position`) | Ordered individual terms attached to an offer |
| `reviews` | Primary key `review_id`; foreign keys to `stores` and `users`; unique (`store_id`, `user_id`) | One current review per user per store |
| `favorites` | Composite primary key (`user_id`, `store_id`) | Many-to-many saved-store relationship |
| `orders` | Primary key `order_id`; foreign keys to `users` and `coupons`; unique redemption code; unique (`user_id`, `idempotency_key`) | Immutable purchase record and historical offer snapshots |
| `redemptions` | Primary key `order_id`, also a foreign key to `orders`; staff user references `users` | At most one redemption event per order |
| `sessions` (v2) | Primary key `token_hash`; `user_id` references `users` with `ON DELETE CASCADE` | Server-managed login sessions, CSRF tokens and expiry |

A merchant can operate several stores, a store can offer several menu items and coupons, and a user can buy several orders. A coupon can appear in many orders. An order has either zero or one redemption record. Staff membership is attached to a store, allowing the same user to work at more than one store. In v2, a user can have zero or many sessions; each session belongs to exactly one user.

Selected functional dependencies clarify the keys used in the normalization discussion:

| Determinant | Dependent facts |
| --- | --- |
| `user_id` | Email, display name, credential hash and creation time |
| `store_id` | Merchant, category, district and store descriptive attributes |
| (`store_id`, `user_id`) in `store_staff` | Staff role and active flag for that store membership |
| (`coupon_id`, `position`) in `coupon_terms` | The term at that position |
| (`store_id`, `tag`) in `store_tags` | Display position; (`store_id`, `position`) is also an alternate key |
| (`store_id`, `user_id`) in `reviews` | The single review's identifier, rating, comment and timestamps |
| `coupon_id` | Current store, offer details, current prices, stock and expiry |
| `order_id` | Buyer, source coupon, sale-time snapshots, code, retry key and purchase time |
| `order_id` in `redemptions` | Redeeming staff member and redemption time |
| `token_hash` in `sessions` (v2) | User identity, CSRF token, creation time and expiry time |

Email, redemption code and (`user_id`, `idempotency_key`) also act as alternate keys under their declared uniqueness constraints. These dependencies describe this prototype's business rules; a changed policy, such as allowing several reviews per user per store, would require reconsidering the corresponding key and constraints.

## Normalization reasoning

The design separates entities and repeating relationships rather than storing nested lists in one row. Menu items, tags, offer terms and staff memberships each have their own rows. This supports first normal form and makes individual values queryable and enforceable.

For relations with composite keys, attributes describe the entire relationship. For example, a staff member's role is specific to both the user and the store, and a coupon term belongs to a particular coupon and position. Store or user descriptions are not copied into these junction relations. This avoids partial dependencies and supports second normal form.

Category, district, merchant and user details reside in their own relations. Stores reference their category, district and merchant; reviews reference their author. Orders reference a coupon, from which the current store relationship can be obtained. There is no additional `store_id` or stored status in an order, avoiding conflicting representations of the same relationship or event state. These choices reduce update anomalies and support third normal form under the prototype's stated business dependencies.

Purchase snapshots are a deliberate historical modelling choice. An order records `title_snapshot`, `price_paid_cents`, `original_price_cents_snapshot` and `expires_on_snapshot`. These values describe that purchase event, not the current offer, so later edits to a coupon must not rewrite an existing purchase. The immutable record preserves what the customer purchased while retaining `coupon_id` as its source relationship. The `coupons_keep_store` trigger also prevents a sold coupon from moving to another store; this keeps the store inferred through the coupon stable.

## Constraints and integrity

Primary keys identify records. Composite keys prevent duplicate memberships, store tags, favourites and ordered coupon terms. Unique constraints prevent duplicate email identities, repeated reviews for a store/user pair, duplicate redemption codes and repeated purchases for the same user/idempotency key. The primary key of `redemptions` prevents a second redemption record for one order.

Foreign keys prevent relationships to missing parent rows. Every application connection must explicitly execute `PRAGMA foreign_keys = ON` before a transaction; enabling it on one connection does not enable it globally. Verification should include `PRAGMA foreign_key_check`.[SQLite foreign-key documentation](https://www.sqlite.org/foreignkeys.html)

Checks cover local value rules such as valid ratings, nonnegative integer-cent prices, stock and boolean flags. A basic email shape check is only an input sanity check, not complete RFC validation. SQLite's built-in `NOCASE` collation folds ASCII letters, so case-insensitive uniqueness does not provide complete Unicode or internationalized-email handling.[SQLite datatype and collation documentation](https://www.sqlite.org/datatype3.html)

Triggers prevent updating or deleting purchase and redemption history. The `orders_no_replace` insert guard rejects collisions on an existing order identifier, redemption code or user/idempotency pair. `redemptions_no_replace` rejects an existing order's redemption, also protecting history against replacement-style inserts. Before inserting a redemption, SQL checks that `staff_user_id` belongs to an active `store_staff` membership for the purchased coupon's store, that redemption is not earlier than purchase, and that it occurs within the purchased expiry date. Store ownership is represented separately: owning a merchant does not automatically create a staff membership.

## Money and time

All prices use integer Hong Kong dollar cents. HK$79.00 is stored as `7900`, preserving exact arithmetic without floating-point rounding. User-facing output formats this value as dollars; persisted calculations use cents.

Expiry is a Hong Kong calendar date in `YYYY-MM-DD` form. The offer remains valid throughout that date and expires at the start of the following Hong Kong day. Event times, including purchase and redemption, are UTC Unix timestamps in seconds. This separates an event instant from a calendar-day business rule. An order's expiry snapshot governs that purchased voucher even if the current offer later changes.

## Purchase and redemption transactions

A purchase must validate the user and offer, read the current price and expiry, check stock, create the order snapshot and reduce stock as one transaction. `purchase_coupon()` coordinates these steps. A retry using the same user's idempotency key returns the original purchase when its coupon matches; using that key for a different coupon is rejected. Stock reduction is conditional on stock remaining positive; failure rolls back the whole operation. Arbitrary direct SQL insertion into `orders` does not automatically decrement coupon stock or prove that its snapshots match the current offer, so application purchases must use the transaction operation.

`redeem_coupon()` checks the order, its purchased expiry and active staff authorization for the supplied store. It normalizes the code to uppercase and rejects a voucher belonging to a different store. The redemption event is inserted once, with a staff identity and UTC timestamp. The database's unique order key makes duplicate redemption fail atomically. Both purchase and redemption read the current time inside the operation rather than accepting a caller-provided business timestamp.

SQLite permits multiple readers but one writer at a time. `BEGIN IMMEDIATE` acquires a write transaction before dependent reads and writes; it can fail with a busy error when another writer holds the database. The application must handle failure and commit or roll back explicitly.[SQLite transaction documentation](https://www.sqlite.org/lang_transaction.html)

Database rules and operation checks complement each other. The implemented backend resolves a trusted user identity from a valid server-side session before calling database operations; it does not accept a client-supplied buyer or staff identity. Review updates and deletion check the author. Merchant order lists and redemption are limited to active `store_staff` memberships. The frontend receives only the current user’s favourites and wallet; merchant order data is restricted to that user’s authorized stores.

## Views

| View | Purpose |
| --- | --- |
| `store_summary` | Readable store listings with category, district and review summaries |
| `coupon_catalog` | Current coupon information joined to its store |
| `wallet` | Purchase records joined to their store and redemption information, with a derived voucher state |

Views provide convenient read models without duplicating the source records. Wallet state can be derived from whether a redemption exists and whether the purchased expiry has passed. Storing a separate order status would allow contradictory states, such as a recorded redemption alongside an `unused` flag.

## Initialization and version migration

The fresh application ZIP contains source and seeds, without a `.db` file. `run.py` calls `backend/database.py`: when the default `database/localdeal.db` is absent, initialization first creates the core v1 database using the current Hong Kong day, then applies the v2 migration. Later starts preserve all existing records. An existing v1 file is migrated with `BEGIN IMMEDIATE`; the session schema, selected seed password hashes and version update commit together or roll back together. Version 2 skips migration, and unsupported versions are rejected without resetting the file.

Core `init_db.py` remains independently usable. It creates a new v1 file, reads `schema.sql` and translates `data/frontend-seed.json` through `generate_seed_sql()`; it does not read `seed.sql`, apply authentication migration or overwrite an existing path. Its default date is the current Hong Kong day, with relative event times and expiry dates shifted together. A specified `--demo-date` and new `--path` provide reproducible fixtures. Only the supplied `seed.sql` has a fixed 2026-10-02 anchor; manual import of it after `schema.sql` is for a new empty core database.

The seed contains 9 fictional users (6 customers and 3 merchant owners), 3 merchants, 6 stores, 18 menu items, 6 coupons, 30 reviews, 3 orders and 1 redemption. The stock translation adds already purchased quantities to each offer's `total_stock`, while preserving the seed's remaining `available_stock`.

## Password credentials and sessions

A `NULL` `users.password_hash` disables password login. On the first v1-to-v2 migration, the backend fills only previously `NULL` hashes for the exact user ID/email pairs of all nine fictional seed users. Their shared public demonstration password is `LocalDealDemo!2026`; existing non-null hashes are preserved, and later v2 starts do not reprovision them. New registrations store a derived credential directly.

`backend/auth.py` uses PBKDF2-HMAC-SHA256 with 600,000 iterations and a fresh 16-byte random salt for each hash. The persisted format is `pbkdf2_sha256$600000$salt_hex$digest_hex`; verification uses a constant-time digest comparison. Plaintext passwords are not persisted.

The v2 `sessions` relation has exactly five columns:

| Column | Definition |
| --- | --- |
| `token_hash` | Non-null TEXT primary key; 64 lowercase hex characters containing SHA-256 of the raw session token |
| `user_id` | Non-null TEXT foreign key to `users.user_id`, `ON DELETE CASCADE` |
| `csrf_token` | Non-null TEXT containing 64 lowercase hex characters |
| `created_at` | Non-null INTEGER UTC Unix seconds, at least zero |
| `expires_at` | Non-null INTEGER UTC Unix seconds, greater than `created_at` |

Indexes cover `user_id` and `expires_at`. A raw token is generated from 32 random bytes and sent only as the `localdeal_session` Cookie; the database stores its SHA-256 hash. The CSRF token comes from 32 random bytes encoded as 64 hexadecimal characters. Sessions expire one day (86,400 seconds) after creation. Login or registration replaces an old presented session, creates a fresh token and removes expired session records; logout deletes the current record.

The Cookie is set with `Path=/`, `HttpOnly`, `SameSite=Strict` and `Max-Age=86400`. The frontend uses same-origin credentials and holds the CSRF token in memory. Protected writes require a valid session, `X-CSRF-Token`, JSON content and the application request header; the local HTTP server also validates Host and any supplied Origin. Login and registration establish a session without requiring an existing CSRF token.

## Verification scope

Core database tests use temporary files and do not modify the running application database. Read `schema.sql`, `operations.py` and `tests/test_database.py` together to distinguish SQL constraints from application checks. Backend and browser integration validation belongs to the full application's test records; no test pass count is asserted here.

Account recovery, real payment confirmation and deployment infrastructure remain outside this local course demonstration. The implemented HTTP adapter, password authentication, merchant authorization and version migration are part of the current application.
