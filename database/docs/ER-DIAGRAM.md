# LocalDeal 数据库关系图

[查看核心 v1 的 15 表矢量关系图（不含 sessions）](er-diagram.svg)。现有 SVG 仅对应 `schema.sql`：15 张表、19 个外键及 3 个只读视图；完整应用 v2 在此基础上执行 `migration_v2.sql`，新增会话表，合计 16 张表与 20 个外键。

每条线表示真实外键；所有子记录都必须关联一个父记录。父记录可以没有子记录，因此普通关系用 `1 → 0..N`；订单可以没有核销记录，且最多只有一条，即 `1 → 0..1`。`PK` 表示主键，`FK` 表示外键，`UQ` 表示唯一约束；`password_hash` 是唯一可空字段。

以下 Mermaid 源码展示完整应用 v2 的 16 张表。SVG 保留核心 v1 范围；应用新增的用户与会话关系在下图中展示。

```mermaid
erDiagram
    users {
        TEXT user_id PK
        TEXT email UQ
        TEXT display_name
        TEXT password_hash "nullable"
        INTEGER created_at
    }
    sessions {
        TEXT token_hash PK "SHA-256; 64 lowercase hex"
        TEXT user_id FK
        TEXT csrf_token "64 lowercase hex"
        INTEGER created_at "UTC Unix seconds"
        INTEGER expires_at "UTC Unix seconds"
    }
    merchants {
        TEXT merchant_id PK
        TEXT owner_user_id FK
        TEXT name
        TEXT contact_email
        INTEGER created_at
    }
    categories {
        TEXT category_id PK
        TEXT name UQ
    }
    districts {
        TEXT district_id PK
        TEXT name UQ
    }
    stores {
        TEXT store_id PK
        TEXT merchant_id FK
        TEXT category_id FK
        TEXT district_id FK
        TEXT name
        TEXT english_name
        TEXT address
        TEXT hours
        TEXT description
        INTEGER price_per_person_cents
        TEXT image_path
        INTEGER is_active
        INTEGER created_at
    }
    store_staff {
        TEXT store_id PK,FK
        TEXT user_id PK,FK
        TEXT role
        INTEGER is_active
    }
    menu_items {
        TEXT menu_item_id PK
        TEXT store_id FK
        TEXT name
        TEXT description
        INTEGER price_cents
        INTEGER position
        INTEGER is_available
    }
    tags {
        TEXT tag PK
    }
    store_tags {
        TEXT store_id PK,FK
        TEXT tag PK,FK
        INTEGER position
    }
    coupons {
        TEXT coupon_id PK
        TEXT store_id FK
        TEXT title
        TEXT description
        INTEGER original_price_cents
        INTEGER price_cents
        INTEGER total_stock
        INTEGER available_stock
        TEXT expires_on
        INTEGER is_active
        INTEGER created_at
    }
    coupon_terms {
        TEXT coupon_id PK,FK
        INTEGER position PK
        TEXT term
    }
    reviews {
        TEXT review_id PK
        TEXT store_id FK
        TEXT user_id FK
        INTEGER rating
        TEXT comment
        INTEGER created_at
        INTEGER updated_at
    }
    favorites {
        TEXT user_id PK,FK
        TEXT store_id PK,FK
        INTEGER created_at
    }
    orders {
        TEXT order_id PK
        TEXT user_id FK
        TEXT coupon_id FK
        TEXT title_snapshot
        INTEGER price_paid_cents
        INTEGER original_price_cents_snapshot
        TEXT expires_on_snapshot
        TEXT redeem_code UQ
        TEXT idempotency_key
        INTEGER purchased_at
    }
    redemptions {
        TEXT order_id PK,FK
        TEXT staff_user_id FK
        INTEGER redeemed_at
    }
    users ||--o{ sessions : has_sessions
    users ||--o{ merchants : owns
    merchants ||--o{ stores : operates
    categories ||--o{ stores : classifies
    districts ||--o{ stores : locates
    stores ||--o{ store_staff : authorizes
    users ||--o{ store_staff : assigned_to
    stores ||--o{ menu_items : offers
    stores ||--o{ store_tags : has
    tags ||--o{ store_tags : labels
    stores ||--o{ coupons : issues
    coupons ||--o{ coupon_terms : defines
    stores ||--o{ reviews : receives
    users ||--o{ reviews : writes
    stores ||--o{ favorites : saved_in
    users ||--o{ favorites : saves
    users ||--o{ orders : buys
    coupons ||--o{ orders : purchased_as
    orders ||--o| redemptions : redeemed_once
    users ||--o{ redemptions : redeems_as_staff
```

需要保留的复合约束：

- `store_staff` 主键为 `(store_id, user_id)`；`favorites` 主键为 `(user_id, store_id)`。
- `tags.tag` 是自然文本主键；`store_tags` 主键为 `(store_id, tag)`，且 `(store_id, position)` 唯一，保持标签显示顺序。
- `menu_items` 的 `(store_id, position)` 唯一；`coupon_terms` 主键为 `(coupon_id, position)`，保持菜单和条款顺序。
- `reviews` 的 `(store_id, user_id)` 唯一；`orders` 的 `redeem_code` 及 `(user_id, idempotency_key)` 分别唯一。
- `redemptions.order_id` 同时为主键和外键，因此每笔订单最多核销一次。`staff_user_id` 关联用户；触发器另外检查该用户是优惠券对应门店的有效员工。
- v2 `sessions.user_id` 关联用户且删除用户时级联删除会话；`created_at` 为非负整数，`expires_at > created_at`，两个令牌字段均要求 64 位小写十六进制。索引为 `idx_sessions_user` 与 `idx_sessions_expiry`。

`sessions.token_hash` 保存原始 Cookie 令牌的 SHA-256 散列，原始令牌不存入数据库；`csrf_token` 为 32 随机字节的十六进制表示。会话按 UTC Unix 秒记录，创建后一天（86,400 秒）过期。`users.password_hash = NULL` 表示不能密码登录；首次 v2 迁移为 9 个匹配的虚构种子账号设置公开演示密码的 PBKDF2-HMAC-SHA256 散列（600,000 次迭代、16 字节随机盐），保留已有非空散列。

金额字段以整数港币分保存。`created_at`、`updated_at`、`purchased_at`、`redeemed_at` 以 Unix 秒保存；`expires_on` 和 `expires_on_snapshot` 是香港日历日期，到最后一日结束前有效。订单保存购买时的标题、金额及到期日快照；已核销、已过期、未使用状态由 `wallet` 视图推导。

三个只读视图为 `store_summary`、`coupon_catalog`、`wallet`，不作为实体卡片绘制。图展示关系和关键约束，核心字段检查、删除规则及历史不可变触发器以 `schema.sql` 为准；应用会话结构以 `migration_v2.sql` 为准，会话创建与有效期规则见 `../../backend/auth.py` 和 `../../backend/service.py`。
