# LocalDeal SQLite 数据库

这里包含 LocalDeal 的核心数据库结构、种子数据、查询及业务操作。完整应用已通过 Python 标准库 HTTP 后端连接前端和 SQLite，使用密码登录、同源会话 Cookie 与服务端权限检查；购买使用模拟支付。

## 两个结构版本

| 版本 | 定义 | 范围 |
| --- | --- | --- |
| 核心 v1 | `schema.sql` | 15 张表、19 个外键、3 个只读视图；独立数据库教学与测试 |
| 完整应用 v2 | `schema.sql` + `migration_v2.sql` | 16 张表、20 个外键、相同 3 个视图；新增后端 `sessions` 表 |

`schema.sql` 保留核心 v1 定义。`docs/er-diagram.svg` 只展示核心 15 张表；[Mermaid 关系图](docs/ER-DIAGRAM.md) 展示应用 v2 的全部 16 张表。

## 启动与查看数据库

全新交付 ZIP 不包含 `.db` 文件。从项目根目录运行 `python3 run.py`，或在本目录运行：

```sh
python3 ../run.py
```

第一次启动会自动创建 `database/localdeal.db`，按当天香港日期初始化示例数据，再迁移至 v2。以后启动保留数据；已有 v1 文件会原子迁移至 v2，保留门店、点评、收藏、库存、订单和核销记录，并添加会话表及示例账号凭据，不重新导入种子。应用默认网址为 `http://127.0.0.1:8787`，完整流程见[项目运行说明](../README.md)。

启动后，可在 DB Browser for SQLite 选择 **Open Database／打开数据库**，打开本目录的 `localdeal.db`。在「数据库结构」查看表、索引、触发器及视图；在「浏览数据」查看记录；在「执行 SQL」打开 `queries.sql`，逐段运行查询。`store_summary`、`coupon_catalog` 和 `wallet` 提供页面所需的组合数据。

种子包含 9 个虚构用户（6 个顾客、3 个商户负责人）、3 个商户、6 家门店、18 个菜单项目、6 个优惠、30 条点评和 3 个订单，其中 1 个订单已有核销记录。优惠和券包状态按查看时的香港日期派生。

如需编辑数据，可先复制数据库。每个新连接均须在事务开始前启用外键；该设置不随文件永久启用。[SQLite 外键说明](https://www.sqlite.org/foreignkeys.html)

```sql
PRAGMA foreign_keys = ON;
PRAGMA foreign_keys;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

上述结果依次应为 `1`、`ok`，以及没有外键违规记录。

## 独立创建核心 v1 副本

`init_db.py` 独立创建核心 v1 数据库，不启动后端，也不应用会话迁移。全部 Python 文件使用标准库。在本目录运行：

```sh
python3 init_db.py --path localdeal-core-demo.db
```

目标路径必须尚不存在；程序拒绝覆盖已有文件。默认路径为本目录的 `localdeal.db`，因此正常应用已创建该文件时，应使用新的 `--path`。

程序读取 `schema.sql`，并将 `data/frontend-seed.json` 规范化为种子 SQL；不读取 `seed.sql`。默认基准为运行当天的香港日期，相关事件与到期日整体平移。要重现指定日期，可创建另一个新副本：

```sh
python3 init_db.py --path localdeal-fixed-core.db --demo-date 2026-10-02
```

交付文件中只有 `seed.sql` 固定以 **2026-10-02** 为演示基准。也可在 DB Browser 新建空数据库，依次执行 `schema.sql` 和 `seed.sql`，得到固定日期的核心 v1 副本；不要在已有数据库上重复导入。要把核心副本用于完整应用，在项目根目录运行 `python3 run.py --db database/localdeal-core-demo.db`，启动时会保留数据并迁移至 v2。

核心数据库测试在临时文件中运行，不修改应用数据库：

```sh
python3 -m unittest discover -s tests -v
```

## 密码与会话

`users.password_hash` 可为 `NULL`，表示该账号不能通过密码登录。v1 种子不带登录凭据。首次迁移至 v2 时，后端仅为用户编号与邮箱均匹配的 9 个虚构种子账号填入原本为空的密码散列；共同的公开演示密码为 `LocalDealDemo!2026`，现有非空散列保留。后续启动不会再次设置密码。

密码使用 PBKDF2-HMAC-SHA256、600,000 次迭代及每次独立生成的 16 字节随机盐，保存格式为 `pbkdf2_sha256$600000$salt_hex$digest_hex`；不保存明文密码。

完整应用的 `sessions` 包含 `token_hash`（SHA-256 十六进制主键）、`user_id`（用户外键）、`csrf_token`（64 位小写十六进制）、`created_at` 和 `expires_at`（UTC Unix 秒）。会话寿命为一天（86,400 秒）；数据库保存 Cookie 令牌的散列。浏览器收到 `localdeal_session` Cookie，属性为 `Path=/`、`HttpOnly`、`SameSite=Strict`、`Max-Age=86400`。受保护的写入同时校验会话、CSRF 令牌与业务权限。

## 金额、时间与业务操作

港币金额保存为整数分；`7900` 表示 HK$79.00。优惠到期日为香港日历日期 `YYYY-MM-DD`，当天整日有效；购买、点评、核销及会话事件保存 UTC Unix 秒。电邮检查仅做基本格式检查，SQLite `NOCASE` 的大小写折叠限于 ASCII。[SQLite 数据类型与排序说明](https://www.sqlite.org/datatype3.html)

后端从有效会话取得用户身份，再调用 `operations.py` 的购买、核销和点评函数。购买使用数据库价格、库存和有效期，并在同一事务中扣库存与写订单；用户与 `idempotency_key` 组合保证购买重试返回原订单。核销检查当前用户是否为对应门店的有效员工及券状态。直接插入 `orders` 不会自动扣库存，应用购买必须使用业务操作。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `localdeal.db` | 首次应用启动生成的 v2 数据库；不包含在全新 ZIP 中 |
| `schema.sql` | 核心 v1 的 15 张表、约束、索引、触发器与视图 |
| `migration_v2.sql` | 新增会话表与索引，设置结构版本为 2 |
| `seed.sql` | 固定日期的核心种子 SQL，供全新空数据库手动导入 |
| `data/frontend-seed.json` | 虚构初始种子参考，不读取浏览器用户资料 |
| `init_db.py` | 创建新的核心 v1 文件，拒绝覆盖 |
| `queries.sql` | 搜索、菜单、点评、优惠和券包查询示例 |
| `operations.py` | 事务购买、核销、点评和券包操作 |
| `tests/test_database.py` | 核心数据库测试 |
| `../backend/database.py` | 应用初始化、v1 → v2 原子迁移与种子账号凭据设置 |
| `../backend/auth.py` | 密码散列和随机会话凭据 |
| `../backend/server.py` | 本机 HTTP 接口、Cookie 与请求校验 |
| `docs/DATABASE-DESIGN.md` | 关系结构、规范化与应用扩展说明 |
| `docs/er-diagram.svg` | 核心 v1 的 15 表矢量图 |
| `docs/ER-DIAGRAM.md` | 完整应用 v2 的 16 表 Mermaid 图 |
| `docs/VALIDATION.md` | 核心数据库验证记录与范围 |

请结合代码、查询和课程要求理解设计，并按课程规定说明辅助工具的使用。
