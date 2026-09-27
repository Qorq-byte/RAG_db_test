# Windows 安装包 v0.1.1 验收

用户于 2026-09-27 明确同意更新安装包。本版基于源码提交 `fb83b7b191d68d536630b6c23fa843e031deb7fb` 构建，版本准备代码已推送至 GitHub。

## 内容

包含 v0.1.0 之后已完成的模型密钥保存、实时问答与进度、会话选择删除、提问集合显示与切换、切换集合保留会话、导入任务和日志、概览统计刷新及嵌入连接修复。侧栏图标/数字醒目调整尚待用户澄清，不计入本版已完成功能。

项目配置、源码版本、锁文件项目版本、安装程序版本及产物名称统一为 0.1.1。保留正式应用 AppId 以供原位升级。构建只收集包内资源，不打包仓库根目录的用户 `config.toml`、`.env` 或知识库。

## 构建环境与检查

- 发布前修复源码全量 **475 项通过，0 失败、0 跳过**，详见[嵌入连接回归汇总](2026-09-27-embedding-connectivity-regression.json)。
- 版本与安装版启动入口 **4 passed in 35.41s**；不是另一次全量运行。
- 冻结代码逐项核对通过：GUI 和 CLI 各 **101 个 ragdb 模块**的代码对象与当前源码编译结果一致（仅归一化构建路径）。
- 构建产物及安装目录内的 `RAGDB-CLI.exe --self-test` 均通过：依赖导入、离线资源、固定检索评估、隔离索引读取和备份恢复。
- 依赖按 `uv.lock` 固定，Python 3.11.15、PyInstaller 6.22.3、Inno Setup 6.7.3。
- 首次同步开发环境时，`ragdb-gui.exe` 被运行中的程序占用；未终止该程序，改用 `.data/release-011-venv` 独立环境构建。构建脚本新增 `-EnvironmentPath` 参数。

复现命令：

```powershell
./scripts/build_windows.ps1 -EnvironmentPath "D:/python/RAG_db_test/.data/release-011-venv"
```

## 安装验证边界

本机已经存在正式 v0.1.0 安装。为避免改写用户的安装登记，安装验证使用同一 `dist/RAGDB` 内容、相同安装规则，但以独立测试 AppId 和输出名编译验证安装程序，安装到项目 `.data/` 目录。正式发布安装程序保留原 AppId。

检查包括安装后 GUI/CLI 哈希与发布内容一致、CLI 版本和独立自检、覆盖安装及卸载后的合成配置/数据保留、原有正式安装登记未变化。此验证不等同于在用户真实知识库上执行升级。

安装、覆盖安装、原生 Windows GUI 定时退出、卸载的退出码均为 **0**。测试配置及合成数据哈希保持不变，正式安装登记保持不变。验证时清空 `PYTHONPATH`，PATH 仅保留 Windows 系统目录。仓库用户原有 `config.toml` 和 `tests/integration/test_collection_cli.py` 哈希与开始时一致。

本地证据：`.data/release-011-build.log`、`.data/release-011-package.xml`、`.data/release-011-archive-check.json` 和 `.data/release-011-install/` 下的编译、安装、覆盖安装、自检、卸载及结果记录。

## 发布记录

已发布 [GitHub Release v0.1.1](https://github.com/Qorq-byte/RAG_db_test/releases/tag/v0.1.1)，设置为 Latest，非草稿。远端标签精确指向上方构建提交。v0.1.0 保留。

| 文件 | 大小（字节） | SHA256 |
| --- | ---: | --- |
| [RAGDB-0.1.1-windows-x64-setup.exe](https://github.com/Qorq-byte/RAG_db_test/releases/download/v0.1.1/RAGDB-0.1.1-windows-x64-setup.exe) | 406211317 | `4b408f9a334d795f7356537efb864e4687f5b2031dd904eb7cf4ffc6c3ecf60b` |
| [SHA256SUMS.txt](https://github.com/Qorq-byte/RAG_db_test/releases/download/v0.1.1/SHA256SUMS.txt) | 101 | `29adb7c616c89848d13293abaee513f77a77e862638e166ff669cbbab7431d7c` |

两项 GitHub 资产均为 `uploaded`，远端大小和服务端 SHA256 与本地文件完全一致；发布后再次核对通过。约 387.4 MiB 的安装包未签名，不包含模型权重、Ollama 服务、OCR 外部程序或 API Key。
