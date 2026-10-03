# LocalDeal 本地全栈演示

[English project overview](README.md)

GitHub 仓库 [fljt-ai/localdeal-5003](https://github.com/fljt-ai/localdeal-5003) 已创建，本地使用 `main` 分支；完整源码上传及远程检查仍待完成。协作方式见 [组员修改说明](CONTRIBUTING.md)，上传步骤见 [GitHub 发布指南](docs/GITHUB-PUBLISH.md)，成员姓名及实际贡献待填写到 [贡献记录](docs/CONTRIBUTIONS.md)。

LocalDeal 是一个可在电脑上运行的餐饮门店、点评与数字优惠券课程项目。网页已经连接 Python HTTP 后端与 SQLite 数据库，支持密码登录、注册、收藏、点评、模拟购买，以及获授权商户的核销。所有门店和示例账号均为虚构资料；购买使用模拟支付。

## 启动应用

需要 **Python 3.10 或以上**，无需安装第三方 Python 包、Node.js 或前端构建工具。

1. 解压已准备的源码包，保持 `frontend`、`backend`、`database` 等文件夹在同一项目目录。完整上传后，也可从 [GitHub 仓库](https://github.com/fljt-ai/localdeal-5003) 下载源码。
2. 在 macOS 上双击项目根目录的 **`start.command`**，保持打开的终端窗口运行。首次启动等待终端显示启动地址。
3. 在浏览器打开 **[http://127.0.0.1:8787](http://127.0.0.1:8787)**。
4. 使用完毕后，在终端按 **Control+C** 停止服务。

请通过上述地址使用应用；直接双击 `frontend/index.html` 无法连接登录和数据库接口。

也可以在终端进入本项目目录，运行：

```sh
python3 -B run.py
```

完整上传后，也可先克隆仓库，再在该目录执行启动命令：

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
| Harbor Bites 商户 | `harbor.owner@example.com` | 中环、尖沙咀两家分店的订单与核销 |
| Little Dumpling 商户 | `dumpling.owner@example.com` | 铜锣湾、中环两家分店的订单与核销 |
| Daily Grind 商户 | `coffee.owner@example.com` | 尖沙咀、铜锣湾两家分店的订单与核销 |

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

测试使用临时数据库，不修改应用当前保存的资料。2026-10-03 验证结果为核心数据库 18 项、HTTP 应用 26 项全部通过；已实际重启服务并确认业务数据保留。具体范围见 [应用验证记录](database/docs/VALIDATION.md) 与 [前端验证记录](frontend/docs/FRONTEND-CHECKS.md)。

前端行为检查可选用 Node.js 18 或以上运行，无需安装 npm 包：

```sh
node frontend/tests/http-api.test.js
node frontend/tests/app-state.test.js
```

仓库包含 GitHub Actions 配置，上传后可在 **Actions** 页面检查 Python 3.10/3.14 与 Node 22 的实际运行结果。本机检查通过不代表 GitHub 检查已经执行。

发现页、优惠、点评、个人收藏、券包和商户订单均按页读取；搜索、地区、类别、评分与订单状态筛选由数据库处理。每页默认 12 家门店或 10 条点评/订单，页面显示完整总数，评分仍来自门店全部点评。初始化只读取摘要和推荐卡片，个人资料导出仍包含本人的全部记录。

2026-10-03 已完成索引对照及分页前后的三档模拟数据评价，最大一档有 100,000 条点评及 50,000 个订单。首页返回体积从约 28.64 MiB 降到约 11.04 KiB；同范围的数据组装与 JSON 编码中位耗时从约 325.22 ms 降到 2.79 ms。这些是本机模拟读取，排除网络及浏览器时间。原始测量、可复现脚本与图表见 [性能评价](evaluation/README.md)。

## 当前范围

这是运行在本机回环地址的课程演示，已实现最小密码认证、服务端会话和门店权限检查，尚未实现邮箱验证、密码找回、真实支付及公开部署。Python 官方说明 `http.server` 不适合生产环境；本项目不把该服务器作为线上部署方案。[Python HTTP server 文档](https://docs.python.org/3/library/http.server.html)

源码、结构说明和演示指南可用作分析参考；GitHub 仓库已创建，完整上传、远程检查和老师访问验证仍待完成。演示视频和最终课程报告仍未完成。
