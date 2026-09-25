# 桌面模型设置最终验收记录（2026-09-25）

## 用户指定模型后的增量验收

用户指定本地 Ollama 嵌入和 `deepseek-flash` 问答/学习生成模型。Ollama 嵌入适配器与桌面配置已分别推送：`72b1c2c`、`9eb9876`。以下为在隔离环境中完成的真实增量验收；既有 5.2 的 198 项为实施前基线。

- 本机 Ollama `embeddinggemma:latest` 对固定合成文本的 `/api/embed` 请求成功，返回 1 个 768 维向量。
- 隔离合成集合从 `BAAI/bge-small-zh-v1.5` 重建切换到 Ollama `embeddinggemma:latest`：1 个切片，切换前后各检索到 1 条结果；重启后活动提供商仍为 Ollama，检索仍成功。测试数据目录已清理。
- 另一个隔离合成集合中，用未安装的模型触发真实 Ollama 服务错误；随后在真实向量生成后的进度回调请求取消，再重试成功。错误与取消后旧活动 profile 和检索结果均保持可用，重试后新 profile 生效；临时目录已清理。
- 最终全量回归：`.\.venv\Scripts\python.exe -m pytest -q`，**208 passed in 30.50s**。
- 已由 [DeepSeek 官方文档](https://api-docs.deepseek.com/)核实 `deepseek-flash` 的 OpenAI 兼容 Base URL 为 `https://api.deepseek.com`；仓库的非敏感 `config.toml` 已配置该地址与模型。密钥通过系统凭据库存储，固定短文本真实连接测试通过。
- 隔离合成集合的 Ollama 检索、DeepSeek 真实问答（回答 57 字符、1 条引用）和学习摘要（131 字符）均通过；重启后活动嵌入、聊天模型及系统凭据恢复成功。合成测试数据已清理。项目当前数据目录有 0 个集合，活动嵌入已初始化为 Ollama。
- `ragdb doctor` 最初因忽略系统凭据而误报缺少密钥；修复后实际运行退出码 0。凭据未写入仓库、TOML 或验收日志。用户已将云端嵌入改为本地 Ollama 嵌入，因此云端嵌入不再是本轮选定模型的验收项。

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

以下表格记录用户指定最终模型前的初始矩阵（2026-09-25 10:07–10:09，Asia/Shanghai）；后续选定模型的真实结果以上方“用户指定模型后的增量验收”为准。所有索引操作均使用新建隔离数据目录和合成资料，测试后已删除目录。

| 验收项 | 服务与模型 | 状态与证据 |
| --- | --- | --- |
| 本地问答 | Ollama 0.24.0；本机仅安装 `embeddinggemma:latest` | **待验证**。`ollama list` 成功，但没有可用于聊天的模型，故未做真实问答及重启检查。 |
| 云端问答 | 服务与模型未指定；无 `RAGDB_CHAT__CLOUD_API_KEY` 或 `.env` | **待验证**。未发送请求；需用户指定服务、模型、测试凭据和可能计费请求的授权。 |
| 本地嵌入 | `BAAI/bge-small-zh-v1.5` → `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | **通过**。`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`；隔离集合导入 1 条合成资料，初始检索 1 条命中；候选模型真实连接测试通过，全局重建 1 个切片并切换活动模型，切换后检索仍有 1 条命中。模型均已在本机缓存。 |
| 云端嵌入 | 服务与模型未指定；无 `RAGDB_EMBEDDING__CLOUD_API_KEY` 或 `.env` | **待验证**。未发送请求；需用户指定兼容服务、模型、测试凭据和发送合成资料的授权。 |
| 失败与取消 | 自动化故障注入；增量使用真实 Ollama | **通过**。见 5.2 回归及上方增量验收；Ollama 服务错误、取消和重试均在隔离合成集合中通过。 |
| 密钥隔离 | 自动化凭据替身 | **自动化通过，真实系统凭据待验证**。见 5.2 回归；没有用于实际服务的测试凭据。 |

首次 `ollama list` 在沙箱中因 Ollama 日志目录 ACL 无法启动；授权环境重试成功。Ollama 列表没有聊天模型，因此不以列表成功代替聊天接口联调。自动化替身的通过结果也不计作真实服务通过。

## 5.4 阶段交付判断

已推送步骤：5.1 `7cea17f`（使用指南）、5.2 `ac159b6`（自动化与兼容性验收）、5.3 的真实本地嵌入部分 `b093d6c`。本报告与状态同步作为下一项独立提交推送到 `codex/desktop-model-settings-acceptance`。

阶段 5 **已完成**。用户最终选择的 Ollama 嵌入、`deepseek-flash` 问答/学习生成及系统凭据恢复均通过真实联调；失败、取消和重试路径也在隔离合成集合中验证。合并前最终自动化回归 216 passed，实际 `ragdb doctor` 退出码 0。用户已明确授权合并主线。

## 5.5 合并前复核（用户授权合并后）

- 代码基线：`023496a`，已推送 `codex/desktop-model-settings-acceptance`。复核修正 `doctor` 显式空密钥被系统旧凭据掩盖的问题；4 项新增用例先复现失败，修正后通过。
- 补充旧版本地/云端 profile 在 SQLite 重开后的兼容验证，覆盖 legacy 与指纹命名空间；确认初始化不会替换旧活动配置。Ollama 响应测试实际验证非有限数值和同批维度不一致。
- 定向回归：23 passed in 2.21s；最终全量 `.\.venv\Scripts\python.exe -m pytest -q`：**216 passed in 33.45s**；实际 `.\.venv\Scripts\ragdb.exe doctor`：退出码 0。
- 主任务复核 provider 使用路径、配置指纹、桌面后台流程和凭据诊断，未发现剩余合并阻塞项。两名独立审查代理因额度限制未完成，不计作独立审查通过。
- 已跟踪文件扫描未发现密钥形式的文本；用户原有 CLI 测试文件及两份前端草稿的 SHA-256 与复核前一致。未重新发送真实模型请求，真实联调证据沿用上方已完成记录。
