# 桌面模型设置最终验收记录（2026-09-25）

## 5.2 自动化与兼容性验收

执行基线：`7cea17f`（阶段 5.1 文档）；测试修正包含在本步骤提交。Windows、Python 3.11，使用仓库现有 `.venv`。

| 项目 | 操作与结果 |
| --- | --- |
| 全量回归 | `.\.venv\Scripts\python.exe -m pytest -q`：**198 passed in 54.07s**。 |
| 桌面设置定向回归 | `.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_model_settings_page.py`：**14 passed in 4.88s**。 |
| CLI 帮助 | `.\.venv\Scripts\ragdb.exe --help`：退出码 0，命令组齐全；当前 PowerShell 捕获中的中文存在终端编码显示问题。 |
| 受控桌面启动 | 在隔离临时数据目录以 `QT_QPA_PLATFORM=offscreen`、`RAGDB_GUI_TEST_EXIT_MS=700` 启动 `python -m ragdb.desktop.app`：退出码 0。 |
| Windows 原生渲染 | 隔离数据目录中创建窗口，打开模型设置页，`window.grab()` 成功（1920×1200），系统可见 356 个字体族。进程退出时 Chroma 文件句柄使临时目录自动清理报错；进程结束后已清理，渲染检查本身通过。 |

自动化覆盖默认配置、v1/v3 数据库升级、活动嵌入 profile 的保留与 TOML 不一致时恢复、云端密钥隔离、外部覆盖字段锁定、连接测试不修改索引，以及重建成功、取消、故障回滚、重试和关闭窗口保护。主要证据见 `tests/integration/database/test_embedding_profile.py`、`tests/integration/test_embedding_rebuild.py`、`tests/unit/test_model_settings.py` 和 `tests/unit/test_model_settings_page.py`。

首次全量回归在第 181 项发现 Qt 异步进度测试偶发失败：工作线程已开始，但单次 `processEvents()` 尚未处理排队信号。测试改为在 5 秒内处理事件直至收到进度，再运行定向及全量回归，均通过。未发现对应产品行为缺陷。

原计划命令 `uv run pytest -q` 未能完成：默认 uv 用户缓存被沙箱 ACL 拒绝；改用工作区缓存后，离线环境无法下载构建依赖 `hatchling`。上述现有虚拟环境运行同一测试集成功。最初的非授权 pytest 运行也因临时目录 ACL 报错；授权环境重跑通过。这些失败均不计为产品测试通过或失败。

## 5.3 真实服务联调

待执行；服务、模型与凭据条件按实施计划逐项核对。自动化替身结果不计作真实服务通过。
