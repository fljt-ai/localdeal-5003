# 将 LocalDeal 发布到 GitHub

## 当前状态

在线仓库 [fljt-ai/localdeal-5003](https://github.com/fljt-ai/localdeal-5003) 首次通过网页上传完整 65 个文件，2026-11-26 已在首页验证为 Public。2026-11-27 的智能功能及双语言升级版已在本地验证。公开阅读不需要邀请；直接写入需要授权；以在线最新提交判断下载版本。

2026-10-03，源码提交 [0fe0b27](https://github.com/fljt-ai/localdeal-5003/commit/0fe0b2781bda8a83fb6eed4a09afe9810fc895a4) 的首次 [Project checks #1](https://github.com/fljt-ai/localdeal-5003/actions/runs/37096568279) 已成功完成。该结果仅对应此提交；后续文档或代码提交的结果以 [Actions 页面](https://github.com/fljt-ai/localdeal-5003/actions) 为准。

## 1. 确定仓库信息

仓库已创建为 **`fljt-ai/localdeal-5003`**。上传和交付前核对以下信息：

- **所属账号**：当前仓库所有者为 `fljt-ai`，组员使用自己的 GitHub 账号协作。
- **可见性**：已验证为 `Public`，仅针对本 LocalDeal 仓库；注意公开源码任何人都可以下载。
- **老师访问方式**：最终报告中的链接必须让老师能够打开最终源码和下载文件；公开阅读无需提供写权限。

确认组员账号后，所有者可在 **Settings → Collaborators → Add people** 发出写权限邀请。公开读者无需邀请。参考 [GitHub 邀请协作者](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)。

本项目中的演示账号、商户和订单均为虚构数据。源码包含公开演示密码，运行中的个人数据库和会话文件不会上传。

## 2. 创建空仓库（已完成）

登录 GitHub，在右上角菜单选择 **New repository**，选择所属账号、填写仓库名和可见性。因为本地已有项目文件，创建时**不要自动添加 README、`.gitignore` 或 license**。点击 **Create repository** 后，复制页面上的仓库地址。这与 GitHub 官方关于导入已有项目的步骤一致。[创建仓库说明](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)

实际仓库页面为 [https://github.com/fljt-ai/localdeal-5003](https://github.com/fljt-ai/localdeal-5003)，Git 地址为 `https://github.com/fljt-ai/localdeal-5003.git`。

## 3. 上传记录与后续修改

首次源码已通过 GitHub 网页私有上传，保留了全部 65 个文件的路径，包括 `.github/workflows/checks.yml`、根目录 `.gitignore` 和 `database/.gitignore`。上传使用仅含已跟踪文件的源码目录，不包含运行中的数据库、会话文件或 `.git` 文件夹。

Git 命令行认证尚未配置，原始本地仓库与网页上传产生的 Git 历史不同。后续通过终端修改时，应先配置有访问权限的 GitHub 认证，重新克隆远程仓库后修改；若继续使用原始本地仓库，需明确核对并协调两边历史，避免强制推送覆盖在线内容：

```sh
git clone https://github.com/fljt-ai/localdeal-5003.git
cd localdeal-5003
```

克隆应放在新的目录，保留原始本地文件；进入新克隆后按 [协作说明](../CONTRIBUTING.md) 修改和提交。相关说明见 [GitHub：上传本地代码](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

## 4. 上传后检查

1. 确认仓库首页显示 README，且前端、后端、SQL、测试和评价文件齐全。
2. 确认 **Actions** 中本次提交的检查完成，并查看失败时的具体原因。
3. 从 **Code → Download ZIP** 下载，解压到新的目录，按 [README](../README.md) 启动。首次启动会建立该目录自己的示例数据库。
4. 使用公开演示账号检查登录、搜索、点评、模拟购买和对应商户核销。
5. 确认仓库首页为 **Public**，核对老师可访问最终提交和视频链接。

仓库发布源码，应用仍按 README 在本机运行；在线可浏览源码的链接不是网站部署地址。

## 5. 放入课程报告

最终 `XXXX-report.pdf` 的交付链接部分需要包含：

- 实际 GitHub 仓库链接：[fljt-ai/localdeal-5003](https://github.com/fljt-ai/localdeal-5003)，源码已上传，提交前仍需配置并验证老师访问。
- 已录制的 5–8 分钟演示视频链接，并确认老师能够播放。

报告还需要真实的组员姓名、本科专业及贡献记录，见 [贡献记录模板](CONTRIBUTIONS.md)。源码上传与首次自动检查已完成；老师访问、视频链接及最终报告仍待完成。
