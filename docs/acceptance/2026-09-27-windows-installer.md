# Windows 安装包验收

## 产物

- 文件：`dist/RAGDB-0.1.0-windows-x64-setup.exe`
- 大小：407,221,776字节（约388.4MiB）。
- SHA256：`c7bc959087d956125f69c7b6ab78042cc8daa59dabc181f53f4d888ef2da3f95`
- 校验文件：`dist/SHA256SUMS.txt`。
- Python 3.11、PyInstaller 6.22.3、Inno Setup 6.7.3；Python依赖固定在uv.lock。

安装为当前用户，不要求管理员权限，默认程序目录 `%LOCALAPPDATA%/Programs/RAGDB`。包括独立GUI、CLI、Python运行库、文档解析与本地嵌入依赖、全部离线界面资源和内置评估集。配置与数据默认位于 `%LOCALAPPDATA%/RAGDB`；保留命令行相对文件路径在调用者目录的语义。模型权重、Ollama服务、OCR外部程序和API密钥不包含在安装包中。

## 验证

- 最终全量 **374 passed in 352.69s**，无失败、错误或跳过。一个警告来自故意构造重复ZIP条目的拒绝测试。
- 最终独立EXE自检通过：Qt/文档解析/本地模型依赖导入、离线资源、固定检索评估、隔离读取子进程和备份恢复。
- 独立程序使用本机缓存BGE模型实际检索：Recall@3=1、MRR@3=1、nDCG@3=0.994983。无模型下载，固定合成资料，不代表用户资料总体质量。
- 安装包真实安装到项目独立测试目录，退出0，无需重启。
- 从安装目录移除项目Python路径后执行 `RAGDB-CLI.exe --self-test`，通过。
- 原生Windows Qt启动，隔离用户配置、定时退出，退出0，确认配置使用用户目录的绝对数据路径。
- 卸载测试退出0，程序被移除，测试用户配置保留。安装/卸载日志存于本地忽略目录 `.data/`。
- 已检查冻结代码包含最新备份活动向量完整性校验；用户原有测试与4份设计草稿哈希未变。

## 构建故障与修复

首次PyInstaller构建从工具PATH误收集Poppler ICU 78。Qt6Core需要Windows ICU的20个无后缀符号，外来DLL仅导出带版本后缀符号，导致WinError127。独立子进程对照：预载外来ICU失败，使用Windows系统ICU成功。构建spec排除误收集的 `icuuc.dll` 与 `icudt78.dll`；构建脚本限制PATH以防外部工具污染。未复制系统DLL。

## 复现构建

安装[官方Inno Setup](https://jrsoftware.org/isdl.php)，在项目目录运行：

```powershell
./scripts/build_windows.ps1 -InnoCompiler "C:/Program Files (x86)/Inno Setup 6/ISCC.exe"
```

脚本同步锁定依赖、生成GUI/CLI目录包、执行离线集成自检、编译安装程序并生成SHA256。当前包未进行代码签名。

## 上传状态

已发布 [v0.1.0 GitHub Release](https://github.com/Qorq-byte/RAG_db_test/releases/tag/v0.1.0)，标签对应构建源码提交 `1bcd53ecffcf992602b4bcd8ebe53b026f98d5f9`。用户完成官方设备登录后，使用GitHub CLI上传并发布，Release不是草稿。

- [下载Windows安装包](https://github.com/Qorq-byte/RAG_db_test/releases/download/v0.1.0/RAGDB-0.1.0-windows-x64-setup.exe)：远端状态 `uploaded`，大小407,221,776字节，GitHub返回的SHA256与上方本地产物一致。
- [下载SHA256SUMS.txt](https://github.com/Qorq-byte/RAG_db_test/releases/download/v0.1.0/SHA256SUMS.txt)：远端状态 `uploaded`，大小101字节，文件自身SHA256为 `a1b72ce6880886e3e7534b8fea13e15fa26eaa92cefd7cfb2e3f6dcdc2145ac4`，与本地一致。

安装包作为Release资产发布，不提交二进制到Git源码历史。全部本轮收尾事项已交付，历史等待授权记录保留在进度日志中。
