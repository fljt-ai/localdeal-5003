# LocalDeal 本地全栈演示

[English project overview](README.md)

GitHub 仓库 [fljt-ai/localdeal-5003](https://github.com/fljt-ai/localdeal-5003) 已于 2026-11-26 改为公开。11 月升级版增加推荐、聚餐匹配、经营分析、事务并发评价及中英文界面，见 [智能功能设计](docs/SMART-FEATURES.md)。协作见 [组员修改说明](CONTRIBUTING.md)，成员姓名及真实贡献待填写到 [贡献记录](docs/CONTRIBUTIONS.md)。

公开仓库可以直接读取或下载。组员需要直接修改时，仓库所有者可在 **Settings → Collaborators → Add people** 邀请其 GitHub 账号。提交前核对老师可访问最终版本。步骤见 [GitHub 邀请说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)。

LocalDeal 是一个可在电脑上运行的餐饮门店、点评与数字优惠券课程项目。网页已经连接 Python HTTP 后端与 SQLite 数据库，支持密码登录、注册、收藏、点评、模拟购买，以及获授权商户的核销。所有门店和示例账号均为虚构资料；购买使用模拟支付。

新版重点：登录后按兴趣、评分、地区和有效折扣生成有解释的推荐；聚餐匹配支持 2–8 位成员，预算必须全部满足，按最低满意度优先排序；商户经营看板计算 7/30 日销售和核销、分店排行、库存补充建议和每日统计。所有功能使用现有 SQLite 表查询。实际效果：[推荐](docs/images/personalized-recommendation.png) · [聚餐](docs/images/group-match.png) · [商户看板](docs/images/merchant-analytics.png)。

## 启动应用

默认使用英文界面。右上角语言下拉框可以选择 **English / 简体中文**，无需重新登录；刷新后自动保留语言选择。示例门店、菜单、优惠、提示、推荐与看板全部按选择显示，用户填写的昵称和点评保留原文。常用英文搜索词（例如 coffee、burger、Central）可转换为相应的数据库关键词。

需要 **Python 3.10 或以上**。推荐安装 FastAPI、Pydantic 与 Uvicorn（无需 Node.js 或前端构建工具）。如果暂时无法安装依赖，也可以使用原兼容后端，全部餐饮业务功能仍能正常运行。

1. 解压源码包；也可从 [GitHub 仓库](https://github.com/fljt-ai/localdeal-5003) 下载。双语言升级版包含 `frontend/src/i18n.js`。保持 `frontend`、`backend`、`database` 等文件夹在同一项目目录。
2. macOS 可用 `start.command`，Windows 可用 `start-windows.cmd`；若系统提示脚本不能直接打开，请按下面的命令行步骤启动。保持终端窗口运行，等待显示启动地址。
3. 在浏览器打开 **[http://127.0.0.1:8787](http://127.0.0.1:8787)**。
4. 使用完毕后，在终端按 **Control+C** 停止服务。

请通过上述地址使用应用；直接双击 `frontend/index.html` 无法连接登录和数据库接口。

也可以在终端进入本项目目录，运行：

```sh
python3 -B run.py
```

推荐录制视频或组员体验时使用新架构与丰富示例模式：

```sh
python3 -m pip install -r requirements.txt
python3 -B run.py --engine fastapi --smart-demo
```

第一次运行创建独立的 `database/localdeal-smart.db`，包含 18 家虚构门店、18 项优惠、114 笔订单和 126 条点评。已存在的数据库不会重建，也不会修改普通启动的 `database/localdeal.db`；如已使用旧丰富数据库，可加 `--db database/localdeal-smart-expanded.db` 创建新演示库。Windows 把 `python3` 换成 `py -3` 即可。FastAPI 启动后打开 [Swagger 接口文档](http://127.0.0.1:8787/docs)，无需连接外部 CDN。

商户在工作台可以调整尚未售出的优惠券库存，只有授权门店的所有者和经理可操作；同时修改总发行库存以保留已销售数量。切换用户账号后聚餐筛选及结果自动清空。

无法安装依赖时可以运行 `python3 -B run.py --engine legacy --smart-demo`；默认自动选择已安装的 FastAPI 或兼容后端。Docker Desktop 用户也可在项目根目录运行 `docker compose up --build`，本机访问同一地址，数据保留在命名卷。`docker compose down` 停止服务。

也可克隆当前公开仓库，再在该目录执行启动命令：

```sh
git clone https://github.com/fljt-ai/localdeal-5003.git
cd localdeal-5003
python3 -B run.py
```

若 8787 已被其他程序占用，可以运行 `python3 -B run.py --port 8788`，再访问终端显示的新地址。`--db` 可指定另一份数据库路径，`--verbose` 可显示请求方法、路径及结果。

## 示例账号

以下账号的公开示例密码均为 **`LocalDealDemo!2026`**。应用默认以访客身份打开。

| 角色 | 邮箱 | 可体验内容 |
| --- | --- | --- |
| 顾客 Alex | `alex@example.com` | 收藏、点评、自己的券包与模拟购买 |
| Harbor Bites 商户 | `harbor.owner@example.com` | 授权门店订单、库存调整与核销 |
| Little Dumpling 商户 | `dumpling.owner@example.com` | 授权门店订单、库存调整与核销 |
| Daily Grind 商户 | `coffee.owner@example.com` | 授权门店订单、库存调整与核销 |

也可注册独立顾客账号。昵称为 1–60 个字符，密码为 12–128 个字符；昵称可以在个人中心修改。新注册的顾客账号没有商户权限。

完整演示步骤见 [演示指南](docs/DEMO-GUIDE.md)，包括用顾客账号购买后，换成对应商户账号核销。

## 数据会保留下来

首次启动自动创建 **`database/localdeal.db`**，按当天香港日期生成示例资料，再升级到应用结构 v2。已有 v1 数据库会增加会话表并迁移为 v2，保留既有点评、收藏、订单和核销记录；已存在的密码哈希也不会被覆盖。重新启动使用同一数据库，不会恢复初始资料，页面也没有重置功能。

全新示例包含 9 个用户、3 个商户、6 家门店、18 个菜单项、6 个优惠、30 条点评、3 个订单、1 条核销记录和 2 条收藏。示例订单覆盖待使用、已核销和已过期；以后日期变化时，状态按实际香港日期推导。

交付的源码压缩包不包含运行中的 `.db` 或会话记录，第一次运行会建立自己的示例数据库。备份自己的资料时，先停止服务，再复制 `database/localdeal.db`。

## 项目文件

| 路径 | 内容 |
| --- | --- |
| `run.py`、`start.command` | 本机启动入口 |
| `frontend/` | 页面、样式、图片和同源 HTTP 适配层 |
| `backend/` | HTTP 路由、认证、会话、数据组装及数据库升级 |
| `database/` | SQL 核心模型、v2 会话迁移、示例数据与事务操作 |
| `database/docs/ER-DIAGRAM.md` | 当前完整 16 表关系的 Mermaid 源码 |
| `database/docs/er-diagram.svg` | 原 v1 核心 15 表的矢量关系图，不包含会话表 |
| `docs/API.md` | 请求格式、权限、接口与错误 |
| `docs/ARCHITECTURE.md` | 架构、模型版本、密码与会话设计 |
| `docs/DEMO-GUIDE.md` | 面向演示的操作顺序 |
| `database/tests/`、`tests/` | 核心数据库及完整 HTTP 应用测试 |
| `evaluation/` | 独立模拟数据生成、索引对照实验、实际测量及报告图表 |

v1 核心模型有 **15 表 / 3 视图**，应用 v2 增加 `sessions` 后共有 **16 表 / 3 视图**。金额在数据库中保存为整数港币分，接口与页面显示港币元；事件时间保存为 Unix 秒，到期日按香港日历计算。

## 运行检查

在项目根目录执行：

```sh
python3 -B -m unittest discover -s database/tests -v
python3 -B -m unittest discover -s tests -v
```

测试使用临时数据库，不修改应用当前保存的资料。安装 `requirements-dev.txt` 后可额外运行 FastAPI 接口测试。验证内容及架构升级见 [架构升级](docs/ARCHITECTURE-UPGRADE.md)、[智能功能设计](docs/SMART-FEATURES.md) 及 [应用验证记录](database/docs/VALIDATION.md)。

前端行为检查可选用 Node.js 18 或以上运行，无需安装 npm 包：

```sh
node frontend/tests/http-api.test.js
node frontend/tests/app-state.test.js
```

仓库包含 Python 3.10/3.14 在 Ubuntu 和 Windows 上的测试以及 Node 22 的 GitHub Actions 配置。实际结果以 [Actions 页面](https://github.com/fljt-ai/localdeal-5003/actions) 上对应提交为准。

发现页、优惠、点评、个人收藏、券包和商户订单均按页读取；搜索、地区、类别、评分与订单状态筛选由数据库处理。每页默认 12 家门店或 10 条点评/订单，页面显示完整总数，评分仍来自门店全部点评。初始化只读取摘要和推荐卡片，个人资料导出仍包含本人的全部记录。

2026-11-27 增加推荐评分后重新测量三档数据；最大规模首页由约 28.64 MiB 降至 13.24 KiB，组装与编码中位数由 339.94 ms 降至 27.25 ms。新推荐比旧编号排序耗时高，但返回量仍受分页控制。事务实验 15 次、每次 100 个模拟买家和 10 张券，均只售出 10 张且无超卖。详见 [性能评价](evaluation/README.md)。这些是本机实验，不是实际网络或生产承载能力。

## 当前范围

这是运行在本机回环地址的课程演示，已实现最小密码认证、服务端会话和门店权限检查，尚未实现邮箱验证、密码找回、真实支付及公开部署。Python 官方说明 `http.server` 不适合生产环境；本项目不把该服务器作为线上部署方案。[Python HTTP server 文档](https://docs.python.org/3/library/http.server.html)

源码、结构说明和演示指南可用作分析参考。此次架构升级实测推荐、聚餐账号隔离、经营分析、库存增加与减少以及 Swagger 接口查询。远程检查结果以 GitHub Actions 对应提交为准；演示视频、成员实际贡献与最终课程报告仍待完成。
