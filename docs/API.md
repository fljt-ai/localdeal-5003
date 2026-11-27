# LocalDeal HTTP API

本文对应 `backend/server.py`、`backend/service.py` 与 `frontend/src/http-api.js` 的当前实现。默认根地址为 `http://127.0.0.1:8787`，服务仅绑定本机回环地址。前端由同一服务提供，没有跨域 API 配置。

## 格式与会话

成功响应统一为：

```json
{"data": {"example": "value"}}
```

失败响应使用相应 HTTP 状态码与稳定错误代码：

```json
{"error": {"code": "UNAUTHENTICATED", "message": "请先登录。"}}
```

写入请求必须使用 JSON 对象、`Content-Type: application/json` 及 `X-LocalDeal-Request: 1`。除登录和注册外，所有写入还必须携带有效会话 Cookie 和 `X-CSRF-Token`。即使是退出或删除请求，也发送空对象 `{}`。未知字段、重复 JSON 键、非有限数值以及超过 16 KiB 的请求正文均会被拒绝；浏览器负责发送内容长度。

所有请求的 `Host` 必须为当前端口的 `127.0.0.1` 或 `localhost`。写请求如包含 `Origin`，必须与 `http://` 加该 `Host` 完全一致；登录和注册也要通过这些检查以及自定义请求头检查。服务器不提供跨域 CORS 许可。

登录或注册建立固定有效期为一天的服务端会话，响应同时返回用户与 `csrfToken`，并设置 `localdeal_session` Cookie：`Path=/; HttpOnly; SameSite=Strict; Max-Age=86400`。本地 HTTP 版本没有设置 `Secure`。浏览器适配层使用 `credentials: "same-origin"` 自动携带 Cookie；CSRF 令牌仅保留在页面内存，密码和令牌不会写入 `localStorage`。退出只销毁当前会话，重新登录会换发随机凭据。

## 公开读取

| 方法与路径 | 参数或作用 | `data` 内容 |
| --- | --- | --- |
| `GET /api/health` | 服务状态 | `{status:"ok", databaseVersion:2}` |
| `GET /api/state` | 初始化摘要 | 见下方 bootstrap 结构 |
| `GET /api/auth/session` | 当前会话 | `{user, csrfToken}`；访客两项为空 |
| `GET /api/stores` | 可选 `q`、`district`、`category`、`couponOnly`、`sort`、`limit`、`offset` | 活跃门店分页；默认有推荐分数与原因 |
| `GET /api/group-match` | `members` 为 JSON 数组（2–8 个 `{budget,category}`），可选 `district`、`limit`、`offset` | 全员预算和共同地区匹配的门店分页 |
| `GET /api/stores/:id` | 单家门店 | 门店对象；不存在为 404 |
| `GET /api/stores/:id/menu` | 门店菜单 | 可售菜单项目数组 |
| `GET /api/stores/:id/reviews` | 可选 `rating`、`sort`、`limit`、`offset` | 点评分页，另含 `ownReview` |
| `GET /api/coupons` | 可选 `storeId`、`limit`、`offset` | 优惠分页 |
| `GET /api/coupons/:id` | 单个优惠 | 优惠对象；不存在为 404 |

`q` 最多 100 个字符，查询门店名称、英文名、类别名称、地区名称、可售菜单名称及标签；搜索中的 `%`、`_` 和反斜杠按文字处理。`district` 与 `category` 可以使用对应编号或名称。`couponOnly=true` 只保留有可购买优惠的门店，默认 `false`。`sort` 为 `recommended`、`rating` 或 `price`：推荐按 SQL 分数降序，评分按平均分降序，人均价格按金额升序；同分或同价时按门店编号升序。收藏分页的默认排序仍按门店编号。推荐卡片除了标准字段，还含 `recommendation:{score,personalized,reasons,components}`，分数及分项均为 0–100。筛选在 SQL 中先限定门店，评分从符合条件门店的全部点评计算，与当前点评页无关。

聚餐接口的每位成员预算必须是 1–10000 港元整数，类别使用有效类别编号或空字符串（不限），共同地区使用有效地区编号或空字符串。拒绝不符合约定的输入（400/INVALID_GROUP），不储存成员输入。每张卡片的 `groupMatch` 含 `matchedMembers,memberCount,worstScore,meanScore,budgetLimit`；分页附加 `memberCount,budgetLimit`。完整模型见 [智能功能设计](SMART-FEATURES.md)。

所有分页接口的 `data` 使用统一结构：

```json
{"items": [], "total": 0, "limit": 12, "offset": 0, "hasMore": false}
```

`total` 是符合筛选及权限范围的完整数量，`items` 仅含当前页。`limit` 必须为 1–50，`offset` 必须为 0–1000000 的整数，默认起点为 0。门店、优惠和收藏默认每页 12 条；点评、个人订单和商户订单默认每页 10 条。重复的同名筛选参数及无效分页参数会被拒绝。页内记录与数量在同一读事务中取得，避免同时发生写入时两者来自不同快照。超出总量的合法起点返回空页。

初始化响应的 `data` 为：

```text
{
  user: null | {id, name, email, merchantStoreIds: [...]},
  csrfToken: null | "64 个十六进制字符",
  summary: {favorites: 0, reviews: 0,
            orders: {all: 0, unused: 0, redeemed: 0, expired: 0}},
  categories: [{id, name}, ...], districts: [{id, name}, ...],
  featuredStore: null | 门店卡片,
  featuredCoupon: null | featuredStore.coupon,
  stores: [], coupons: [], reviews: [],
  favorites: [], orders: [], merchantOrders: []
}
```

`summary` 只统计当前用户的收藏、本人点评和个人券包；访客计数全为 0。旧的六个数据数组保留为空值以兼容初始化结构，登录后也不会装入完整列表。页面应按需要调用分页接口。`featuredStore` 为第一家活跃门店的卡片；没有活跃门店时为空，没有可购买优惠时 `featuredCoupon` 为空。

门店卡片保留名称、类别、地区、地址、人均价格、照片等字段，包含 `averageRating`、`reviewCount`、`isActive`、当前用户的 `isFavorite` 和 `coupon`。卡片最多带三个标签，`menu` 为空数组；`GET /api/stores/:id` 才读取该店的完整标签及可售菜单。`coupon` 是本店价格最低的可购买优惠，同价按优惠编号选择，没有则为空。优惠对象含 `stock`、`expiresAt`、`terms`、服务端计算的 `isPurchasable`，以及 `storeName`、`storeDistrict`、`storeImage`。优惠列表读取活跃门店的活跃优惠，售罄或过期记录仍以不可购买状态返回。价格字段是港币元，到期日是 `YYYY-MM-DD`，事件日期是 UTC ISO 8601 字符串。

门店点评支持 `rating=all/1/2/3/4/5` 与 `sort=new/rating`。默认 `all`、`new`；最新排序按建立时间降序、点评编号升序，评分排序先按评分降序，再用建立时间和编号消除并列。该分页额外返回 `ownReview`：当前登录用户在此店的已有点评或空值，即使自己的点评不在本页或不符合评分筛选也会返回。`total` 只统计符合当前筛选的点评。门店不存在返回 404。

访客仅有公开资料，`user` 与 `csrfToken` 为空。已登录用户的收藏、券包和本人点评通过独立私有接口读取；商户台账通过单独授权的接口读取。客户端不能通过提交用户编号来选择买家身份。

## 认证与资料

| 方法与路径 | JSON 正文 | 结果 |
| --- | --- | --- |
| `POST /api/auth/register` | `{name, email, password}` | 201；建立顾客账号和会话，返回 `{user,csrfToken}` |
| `POST /api/auth/login` | `{email, password}` | 200；验证密码并建立会话，返回 `{user,csrfToken}` |
| `POST /api/auth/logout` | `{}` | 200；返回 `{loggedOut:true}` 并清除 Cookie |
| `PATCH /api/users/me` | `{name}` | 200；修改当前用户昵称并返回用户对象 |

昵称为 1–60 个字符，邮箱转换为小写并做基本格式检查，密码为 12–128 个字符。数据库中 `password_hash` 为空的账号不能登录。新注册账号不获得员工或商户角色；个人资料接口也不能修改邮箱、密码、用户编号或商户权限。

登录按来源地址和邮箱组合限速；注册按来源地址统一限速。一个五分钟窗口最多接收十次尝试，超出返回 `429 / RATE_LIMITED`；登录成功清除此组合的计数。限速状态仅存在当前服务进程中。

## 个人分页

以下接口需要有效会话；未登录返回 `401 / UNAUTHENTICATED`。

| 方法与路径 | 参数 | `data` 内容 |
| --- | --- | --- |
| `GET /api/users/me/favorites` | 门店查询参数及 `limit`、`offset` | 当前用户收藏的门店卡片分页 |
| `GET /api/users/me/reviews` | 可选 `rating`、`sort`、`limit`、`offset` | 当前用户本人点评分页 |

收藏页保留已收藏但当前停用的门店，并通过 `isActive` 标注，未额外筛选时其完整数量与初始化摘要一致；普通门店发现页只显示活跃门店。本人点评使用与公开门店点评相同的评分筛选和稳定排序，但范围固定为会话用户。点评对象包括门店编号、作者编号与显示名、评分、内容、建立及更新时间，另有 `storeName`、`storeDistrict`、`storeImage`，无需读取全部门店才能显示本人记录。

## 点评与收藏

| 方法与路径 | JSON 正文 | 结果 |
| --- | --- | --- |
| `POST /api/stores/:id/reviews` | `{rating, comment}` | 201；返回新增点评 |
| `PATCH /api/reviews/:id` | `{rating, comment}` | 200；返回修改后的点评 |
| `DELETE /api/reviews/:id` | `{}` | 200；返回 `{deleted:true}` |
| `POST /api/favorites/toggle` | `{storeId}` | 200；返回 `{storeId,saved}` |

评分为 1–5 的整数。后端允许 1–500 个字符的非空点评，当前页面要求 5–500 个字符。每位用户在每家店只能保留一条点评，修改与删除只允许作者本人进行。页面上的“写点评”会识别自己的已有记录并进入编辑；昵称更新后，点评显示名称通过用户关联读取最新值。

## 购买、券包与核销

| 方法与路径 | 参数或 JSON 正文 | 结果 |
| --- | --- | --- |
| `POST /api/orders` | `{couponId,idempotencyKey}` | 返回购买订单；新购买通常 201，已有重试记录 200 |
| `GET /api/orders` | 可选 `status=all/unused/redeemed/expired`、`limit`、`offset` | 当前用户订单分页 |
| `GET /api/orders/:id` | 自己的订单编号 | 当前用户单笔订单；其他人的订单也返回 404 |
| `GET /api/merchant/orders` | 可选 `storeId`、`status=all/unused/redeemed/expired`、`limit`、`offset` | 授权门店的买家订单分页 |
| `GET /api/merchant/analytics` | 必填授权 `storeId`，可选 `days=7/30` | 选定门店统计、日期趋势、授权分店排行、优惠库存与当前点评趋势 |
| `POST /api/orders/redeem` | `{code,storeId}` | 200；返回已核销订单 |

订单对象为：

```text
{id, userId, couponId, storeId, storeName, storeDistrict, storeImage,
 title, price, originalPrice,
 code, status, purchasedAt, expiresAt, redeemedAt}
```

`redeemedAt` 在未核销时为空。`status` 由服务端 `wallet` 视图推导为 `unused`、`redeemed` 或 `expired`；已核销优先于已过期。日期按香港 UTC+8 计算，到期日当天结束前仍有效。

个人和商户订单默认 `status=all`，按购买时间降序、订单编号升序稳定排序。商户接口仅返回当前用户有有效 `store_staff` 关系的门店订单，包括这些门店其他买家的记录；数量也限定在同一授权范围。省略 `storeId` 表示全部授权门店，指定未授权门店或使用没有员工权限的顾客账号会返回 `403 / FORBIDDEN`。订单列表、单笔读取、购买和核销响应均提供上述门店展示字段。

购买只接受优惠编号和 1–128 字符的请求标识，不接受客户端价格、用户编号或到期日。服务器在同一写事务中检查用户、门店和优惠可用性、剩余库存与有效期，减少一份库存并记录购买。订单永久保存购买时的标题、实付金额、原价和到期日快照；后来修改优惠不会改写购买历史。模拟支付不会连接支付服务或收取真实款项。

重试使用当前用户与 `idempotencyKey` 的组合：同一优惠返回原订单，不再扣库存；相同标识用于另一个优惠返回 `409 / RETRY_CONFLICT`。不同用户可以使用相同标识。页面在打开购买窗口时创建一次标识，并在该窗口的网络重试中保持它；再次主动打开窗口则产生新标识，可以有意重复购买。同一请求标识已经建立订单后，即使优惠随后售罄，正确重试仍可读取原订单。

核销身份由会话取得，不能提交另一名员工的编号。后端检查员工在所选门店的有效 `store_staff` 关系、券所属门店、购买快照有效期及是否已经核销，记录一条带员工与时间的核销事件。每个订单最多一条核销记录，SQL 触发器也检查门店授权与时间边界。商户负责人身份与员工授权是两个关系，不能仅凭拥有商户名称取得核销权限。

经营分析与订单过滤独立：`days` 默认为 7，含当日；使用香港日历日期与订单购买时金额快照，计算 `sold,gross,redeemed,expired,unused,redemptionRate,todaySold,todayGross`。无销售时核销率为空。`trend` 包含日期、销售张数、金额和累计金额；`offers` 包含销量排行、当前库存、低库存与补充建议；`branches` 仅当前员工的授权门店，`ratingTrend` 统计当前点评按发表日的均分及数量。两个排行最多各 50 条。不含买家信息。没有对应门店员工权限返回 403。

## 个人导出

`GET /api/export` 需要登录，返回 `{user,orders,favorites,reviews,metadata}`。它明确导出当前用户的全部记录，不受页面分页、筛选或已加载内容限制。订单、收藏和点评在 SQL 中使用当前用户条件读取；不包含其他人的个人券包、商户订单台账、密码哈希、会话凭据或 CSRF 令牌。`metadata` 说明导出时间、`scope:"current-user"` 与 `payment:"simulated"`。

## 常见错误

| HTTP 状态 | 代码举例 | 含义 |
| --- | --- | --- |
| 400 | `INVALID_FIELDS`、`INVALID_INPUT`、`INVALID_EMAIL`、`INVALID_PASSWORD`、`INVALID_JSON` | 字段、输入或 JSON 不符合约定 |
| 400 | `INVALID_KEY`、`INVALID_CODE`、`INVALID_RATING`、`INVALID_COMMENT` | 请求标识、券码或点评值无效 |
| 400 | `INVALID_PAGINATION`、`INVALID_QUERY`、`INVALID_SEARCH`、`INVALID_SORT`、`INVALID_STATUS` | 分页、重复参数或筛选排序无效 |
| 401 | `UNAUTHENTICATED`、`INVALID_CREDENTIALS` | 没有有效会话或密码验证失败 |
| 403 | `INVALID_HOST`、`INVALID_ORIGIN`、`REQUEST_HEADER_REQUIRED`、`CSRF_FAILED` | 请求来源或会话校验未通过 |
| 403 | `FORBIDDEN` | 没有点评作者或门店员工权限 |
| 404 | `STORE_NOT_FOUND`、`COUPON_NOT_FOUND`、`ORDER_NOT_FOUND`、`CODE_NOT_FOUND`、`REVIEW_NOT_FOUND` | 找不到资源，或资源不在当前用户范围 |
| 409 | `EMAIL_EXISTS`、`REVIEW_EXISTS`、`RETRY_CONFLICT` | 唯一身份、单店点评或重试标识冲突 |
| 409 | `SOLD_OUT`、`NOT_AVAILABLE`、`EXPIRED`、`WRONG_STORE`、`ALREADY_REDEEMED` | 购买或核销不满足业务规则 |
| 413 / 415 | `BODY_TOO_LARGE` / `JSON_REQUIRED` | 正文超过限制，或请求不是 JSON |
| 429 | `RATE_LIMITED` | 短时间内尝试过多 |
| 503 | `DATABASE_BUSY` | 等待数据库写锁超时，可稍后重试 |
| 500 | `DATABASE_ERROR`、`INTERNAL_ERROR` | 服务器未完成操作；不向客户端输出内部异常细节 |

前端请求有 15 秒超时，不自动重试。购买发生连接中断或超时时，应重试当前窗口中的同一请求；页面初始化失败可使用“重新连接”。业务错误应按说明修正输入或切换账号，而非不断重复确认。
