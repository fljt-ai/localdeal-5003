# LocalDeal 前端 HTTP 接口

页面通过 `src/http-api.js` 请求同源后端。请按项目根目录 README 启动应用。

## 请求与会话

- 成功返回 `{ "data": ... }`；失败返回 `{ "error": { "code": "...", "message": "..." } }` 和相应 HTTP 状态码。
- 请求发送 `Accept: application/json`，使用 `credentials: "same-origin"`、`cache: "no-store"`；浏览器自动携带后端管理的会话 Cookie。
- 写入发送 `Content-Type: application/json`、`X-LocalDeal-Request: 1`；内存中已有令牌时发送 `X-CSRF-Token`。密码和令牌不写入 `localStorage`。
- 登录、注册、会话及启动响应可以更新 CSRF 令牌；退出或收到 `401` 后清空令牌。
- 令牌更新受会话代次及请求序号保护；旧响应不能清除或替换新登录的令牌。当前会话失效时，页面清理私人数据，重新读取启动信息并提供登录窗口。
- 请求超时 15 秒。连接和超时错误标为 `NETWORK_ERROR`；接口层不自动重试，页面提供重试按钮和表单。

## 精简启动数据

`GET /api/state` 返回当前 `user`、`csrfToken`、`summary`、分类 `categories`、地区 `districts`、`featuredStore` 和 `featuredCoupon`。

```json
{
  "summary": {
    "favorites": 2,
    "reviews": 2,
    "orders": {"all": 3, "unused": 1, "redeemed": 1, "expired": 1}
  }
}
```

兼容字段 `stores`、`coupons`、`reviews`、`orders`、`favorites`、`merchantOrders` 均为空数组。页面不从这些数组加载数据；导航、个人中心及券包的数字来自服务器的完整记录计数。

`user.merchantStoreIds` 是商户获授权的门店编号。普通顾客不显示商户入口，服务器独立检查权限。访客的个人计数为零。

## 分页读取

以下列表返回 `{ items, total, limit, offset, hasMore }`。`total` 是符合筛选条件的全部记录数，`items` 仅为当前页；每次最多 50 条。

| 方法和路径 | 参数与页面用法 |
| --- | --- |
| `GET /api/stores` | `q`、`district`、`category`、`couponOnly`、`sort`、`limit`、`offset`；发现页每页 12 家 |
| `GET /api/stores/:id` | 单店详情；包含当前菜单、标签、完整点评统计及店内优惠 |
| `GET /api/coupons` | `storeId`（可选）、`limit`、`offset`；优惠页每页 12 条 |
| `GET /api/coupons/:id` | 单张优惠；打开购买窗口前重新读取库存及有效状态 |
| `GET /api/stores/:id/reviews` | `rating=all/1/2/3/4/5`、`sort=new/rating`、`limit`、`offset`；每页 10 条 |
| `GET /api/users/me/reviews` | 本人点评，每页 10 条 |
| `GET /api/users/me/favorites` | 本人收藏门店，个人中心每页 12 家；发现页侧栏最多 3 家 |
| `GET /api/orders` | 本人订单；`status=all/unused/redeemed/expired`；每页 10 条 |
| `GET /api/merchant/orders` | 获授权门店的订单；`storeId`、`status`、`limit`、`offset`；每页 10 条 |

地区及类别接受编号或名称；前端使用启动数据中的编号。门店排序为 `recommended`、`rating` 或 `price`；优惠筛选参数为字符串 `true`/`false`。

新版发现页推荐卡片提供 `recommendation` 分数、四个分项与理由。`getGroupMatch({members,district,limit,offset})` 将成员数组序列化为 JSON 查询参数；响应包含分页和 `groupMatch`。`getMerchantAnalytics({storeId,days})` 读取授权门店汇总、7/30 天趋势、库存和排行。详细定义见 [API 文档](../../docs/API.md) 与 [智能功能设计](../../docs/SMART-FEATURES.md)。

门店卡包含 `averageRating`、`reviewCount`、`isFavorite` 和嵌套 `coupon`（可能为空）。门店列表不加载菜单。单张优惠含服务端计算的 `isPurchasable`；优惠、点评及订单列表同时提供 `storeName`、`storeDistrict`、`storeImage`，因此无需下载所有门店再关联。

单店点评分页额外提供 `ownReview`，独立于当前页及星级筛选。用户即使没有在这一页看到自己的点评，也能直接修改已有点评。门店平均分和总点评数取自服务器全部记录，不以这一页的点评重新计算。

## 写入与导出

| 方法 | 路径 | JSON 正文／作用 |
| --- | --- | --- |
| `GET` | `/api/auth/session` | 当前用户与 CSRF 令牌 |
| `POST` | `/api/auth/login` | `{ email, password }`；建立会话 |
| `POST` | `/api/auth/register` | `{ name, email, password }`；注册顾客账号并建立会话 |
| `POST` | `/api/auth/logout` | `{}`；销毁会话 |
| `PATCH` | `/api/users/me` | `{ name }`；修改本人昵称 |
| `POST` | `/api/favorites/toggle` | `{ storeId }`；切换本人收藏 |
| `POST` | `/api/stores/:id/reviews` | `{ rating, comment }`；新增本人点评 |
| `PATCH` | `/api/reviews/:id` | `{ rating, comment }`；修改本人点评 |
| `DELETE` | `/api/reviews/:id` | `{}`；删除本人点评 |
| `POST` | `/api/orders` | `{ couponId, idempotencyKey }`；模拟购买一张券 |
| `POST` | `/api/orders/redeem` | `{ code, storeId }`；获授权商户核销 |
| `GET` | `/api/export` | 用户主动导出完整个人数据；不受页面分页限制 |

注册确认密码仅在页面检查，不发送后端。价格、买家身份和商户权限由服务器确定。登录／注册以外的写入需要有效会话，点评修改和删除还要求作者身份；核销要求对应门店的员工授权。

写入成功后重新读取精简启动数据及当前页面，使计数、收藏、评分、库存和状态更新。个人导出只包含本人资料、收藏、订单、点评及导出元数据；页面不会在后台自动请求完整导出。`subscribe()` 仅为兼容入口，不提供实时推送。

## 页面请求与重试

搜索输入延迟 300 毫秒后提交服务器；筛选和排序变化从第一页开始。每个读取批次有递增编号，过时的路由或搜索响应不会覆盖新页面。页面只持有当前页，门店／优惠编号缓存最多各 64 条，点评缓存最多 32 条；用户切换及成功写入后清理缓存再加载。

异步购买／点评窗口会检查发起时的页面及账号，迟到的读取不会重开已经离开的窗口。核销期间锁定门店选择，成功提示只属于发起核销的门店。

购买窗口生成一次 `idempotencyKey`，同一窗口的重试沿用该标识，关闭后重新打开生成新标识。服务器以“当前用户 + 标识”识别重试：同一优惠返回原订单，不重复扣库存；同一标识用于另一优惠返回 `409 / RETRY_CONFLICT`。首次购买在同一事务中核对库存及有效期、扣库存、写订单。全部支付为模拟支付。
