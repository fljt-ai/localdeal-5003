# 将 LocalDeal 发布到 GitHub

## 当前状态

本地项目按 `main` 分支整理，源码、使用说明、忽略规则和自动检查配置已准备好。在线仓库 [fljt-ai/localdeal-5003](https://github.com/fljt-ai/localdeal-5003) 已创建，并在设置页及仓库首页验证为私有；根目录 7 个文件已上传，完整源码上传及远程检查仍待完成。

GitHub Actions 检查配置已经包含在源码中；配置存在不代表它已在 GitHub 上运行。首次上传后，应在仓库的 **Actions** 页面查看真实执行结果。

## 1. 确定仓库信息

仓库已创建为 **`fljt-ai/localdeal-5003`**。上传和交付前核对以下信息：

- **所属账号**：当前仓库所有者为 `fljt-ai`，组员使用自己的 GitHub 账号协作。
- **可见性**：已验证为 `Private`，仅针对本 LocalDeal 仓库；后续上传保持私有。
- **老师访问方式**：最终报告中的链接必须让老师能够打开源码和下载文件。需先确认老师使用的 GitHub 账号与访问安排，再另行授权并验证。

确认组员账号后，所有者可在 **Settings → Collaborators → Add people** 发出邀请，组员接受后才能访问私有仓库。个人账号的私有仓库协作者拥有读取和修改权限，不能仅授予只读协作者权限，因此老师访问也应先确认安排。邀请不会因为上传源码而自动发生。参考 [GitHub 邀请协作者](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository) 和 [个人仓库权限](https://docs.github.com/en/enterprise-cloud%40latest/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository)。

本项目中的演示账号、商户和订单均为虚构数据。源码包含公开演示密码，运行中的个人数据库和会话文件不会上传。

## 2. 创建空仓库（已完成）

登录 GitHub，在右上角菜单选择 **New repository**，选择所属账号、填写仓库名和可见性。因为本地已有项目文件，创建时**不要自动添加 README、`.gitignore` 或 license**。点击 **Create repository** 后，复制页面上的仓库地址。这与 GitHub 官方关于导入已有项目的步骤一致。[创建仓库说明](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)

实际仓库页面为 [https://github.com/fljt-ai/localdeal-5003](https://github.com/fljt-ai/localdeal-5003)，Git 地址为 `https://github.com/fljt-ai/localdeal-5003.git`。

## 3. 连接并上传本地代码

当前采用 GitHub 网页私有上传，确认可见性为 `Private` 后按目录保留源码路径，包括 `.github/workflows/checks.yml`、根目录 `.gitignore` 和 `database/.gitignore`。使用仅含已跟踪文件的源码包，不上传运行中的数据库、会话文件或 `.git` 文件夹；上传一个 ZIP 文件不会自动展开成源码目录。

如果以后使用命令行上传，需要 Git 登录授权。仅在本地没有 `origin` 时添加远程地址，再上传 `main`：

```sh
git remote add origin https://github.com/fljt-ai/localdeal-5003.git
git remote -v
git push -u origin main
```

如果本地已经有 `origin`，先核对它指向哪个仓库，再决定是否调整。如果远程仓库已有内容，先检查两边的历史并处理差异；不要强制推送覆盖现有工作。连接和上传步骤参考 [GitHub：上传本地代码](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

## 4. 上传后检查

1. 确认仓库首页显示 README，且前端、后端、SQL、测试和评价文件齐全。
2. 确认 **Actions** 中本次提交的检查完成，并查看失败时的具体原因。
3. 从 **Code → Download ZIP** 下载，解压到新的目录，按 [README](../README.md) 启动。首次启动会建立该目录自己的示例数据库。
4. 使用公开演示账号检查登录、搜索、点评、模拟购买和对应商户核销。
5. 确认仓库可见性保持 **Private**，并用老师应有的访问方式检查仓库链接及授权。

仓库发布源码，应用仍按 README 在本机运行；在线可浏览源码的链接不是网站部署地址。

## 5. 放入课程报告

最终 `XXXX-report.pdf` 的交付链接部分需要包含：

- 实际 GitHub 仓库链接：[fljt-ai/localdeal-5003](https://github.com/fljt-ai/localdeal-5003)，待完整上传及老师访问验证后作为交付链接。
- 已录制的 5–8 分钟演示视频链接，并确认老师能够播放。

报告还需要真实的组员姓名、本科专业及贡献记录，见 [贡献记录模板](CONTRIBUTIONS.md)。实际仓库地址已确定；视频链接、完整源码上传和远程检查尚未完成，不能将其标记为已完成交付。
