# ragdb

面向个人学习资料的本地 RAG 知识库命令行工具。它可将本地文件、网页和公开 GitHub 仓库导入知识集合，并通过语义检索与关键词检索返回带出处的结果。

## 要求与安装

- Python 3.11（项目不支持 3.12+）
- [uv](https://docs.astral.sh/uv/)
- Git（仅导入公开 GitHub 仓库时需要）

克隆项目后安装依赖：

```powershell
uv sync
```

所有示例均通过 `uv run ragdb` 运行；也可在激活环境后使用 `ragdb`。

## 配置

从示例开始：

```powershell
Copy-Item config.example.toml config.toml
```

`config.toml` 可配置以下区域：

- `storage`：数据目录、SQLite 文件名和 Chroma 数据目录。
- `embedding`：本地或云端嵌入模型、批大小和云端 Base URL。
- `chunking`：文本切分大小与重叠字符数。
- `retrieval`：向量、关键词和最终结果的数量，以及 RRF 参数。
- `crawl`：网页抓取深度、页数、速率、超时和 User-Agent。
- `rerank`：是否启用重排序、模型与批大小。
- `ocr`：可选本机 Tesseract OCR 的开关、路径、语言与渲染 DPI。
- `chat`：本地 Ollama 或 OpenAI 兼容云端问答模型及其上下文预算。

默认使用本地嵌入模型 `BAAI/bge-small-zh-v1.5`。首次实际导入或检索时，底层库可能下载该模型；`ragdb doctor` 不会下载模型。

如使用 OpenAI 兼容的云端嵌入，在 `config.toml` 中设置：

```toml
[embedding]
provider = "cloud"
cloud_model = "text-embedding-3-small"
cloud_base_url = "https://api.openai.com/v1"
```

将密钥放在 `.env`（不提交到仓库）或环境变量中，而不是 TOML 文件：

```text
RAGDB_EMBEDDING__CLOUD_API_KEY=your-secret-key
RAGDB_CHAT__CLOUD_API_KEY=your-secret-key
```

可通过全局选项选择另一份配置：

```powershell
uv run ragdb --config .\my-config.toml doctor
```

## 快速开始

创建集合：

```powershell
uv run ragdb collection create ai-notes --description "AI 学习资料"
```

导入一个文件、整个目录或手工文本：

```powershell
uv run ragdb ingest file .\notes\attention.md --collection ai-notes --tag transformer --course NLP
uv run ragdb ingest directory .\papers --collection ai-notes
uv run ragdb ingest text "RAG 将检索结果注入生成提示词。" --collection ai-notes --title "学习笔记"
```

检索并按元数据过滤：

```powershell
uv run ragdb search "注意力机制如何工作？" --collection ai-notes --tag transformer
uv run ragdb search "向量检索" --collection ai-notes --date-from 2026-01-01
```

## 检索增强问答

问答严格依据当前集合的检索证据作答，并显示来源编号。默认调用本机 Ollama；也可将 `chat.provider` 改为 `cloud`，并通过环境变量配置 `RAGDB_CHAT__CLOUD_API_KEY`。

```powershell
uv run ragdb chat ask "RAG 的检索与生成如何协作？" --collection ai-notes
uv run ragdb chat ask "请再举一个例子" --collection ai-notes --session <SESSION_ID>
uv run ragdb chat session list --collection ai-notes
uv run ragdb chat session show <SESSION_ID> --collection ai-notes
uv run ragdb chat session delete <SESSION_ID> --collection ai-notes
```

会话只属于一个知识集合；删除集合会同时删除其会话。没有检索到足够证据时，系统不会调用模型，而会明确说明无法依据知识库回答。

## 学习内容生成

可依据集合内检索证据生成摘要、提纲、学习笔记、练习题或知识卡片；使用 `--source-id` 可限定单一资料。生成结果和来源快照会持久化保存。

```powershell
uv run ragdb generate summary "Transformer 核心思想" --collection ai-notes
uv run ragdb generate outline "课程复习提纲" --collection ai-notes
uv run ragdb generate notes "注意力机制" --collection ai-notes --source-id <SOURCE_ID>
uv run ragdb generate quiz "RAG 基础" --collection ai-notes
uv run ragdb generate cards "关键术语" --collection ai-notes
uv run ragdb artifact list --collection ai-notes
uv run ragdb artifact show <ARTIFACT_ID> --collection ai-notes
uv run ragdb artifact delete <ARTIFACT_ID> --collection ai-notes
```

管理集合和资料来源：

```powershell
uv run ragdb collection list
uv run ragdb collection info ai-notes
uv run ragdb source list --collection ai-notes
uv run ragdb source show <SOURCE_ID>
```

删除集合或来源会删除其索引；不使用 `--yes` 时会要求确认：

```powershell
uv run ragdb source delete <SOURCE_ID>
uv run ragdb collection delete ai-notes
```

## 网页、仓库与目录同步

抓取网页并导入指定集合：

```powershell
uv run ragdb crawl https://example.com/article --collection ai-notes
```

导入公开 GitHub 仓库：

```powershell
uv run ragdb repo https://github.com/owner/repository --collection ai-notes
```

监听本地目录。监听在当前终端前台运行，按 `Ctrl+C` 停止：

```powershell
uv run ragdb watch start .\notes --collection ai-notes
```

查看说明或重建某个集合的本地资料索引：

```powershell
uv run ragdb watch status
uv run ragdb reindex --collection ai-notes
```

## 环境诊断

执行：

```powershell
uv run ragdb doctor
```

该命令按检查项输出“通过”、“警告”或“失败”，并在警告或失败时给出修复建议。它会检查 Python 版本、配置解析、数据目录权限、SQLite FTS5、ChromaDB、Git、本地嵌入依赖，以及启用云端嵌入时的模型、Base URL 和密钥配置。

诊断不会下载模型、调用云端 API、创建知识库索引或修改已有资料。仅出现“失败”时命令以非零状态退出；只有“警告”时仍以 0 退出。

扫描 PDF 可启用本机 Tesseract；例如本项目安装位置为：

```toml
[ocr]
enabled = true
executable_path = "D:/Dinstall/Tesseract-OCR/tesseract.exe"
languages = "chi_sim+eng"
```

嵌入供应商或模型变更后，系统会拒绝混用已有索引并提示重建：

```powershell
uv run ragdb reindex --collection ai-notes
```

可查看目录批量导入的历史任务和操作日志：

```powershell
uv run ragdb task list --collection ai-notes
uv run ragdb task show <TASK_ID>
uv run ragdb log list --collection ai-notes
```

## 数据与隐私

默认数据保存在 `.data/`，其中包含 SQLite、Chroma 索引和仓库导入缓存；该目录已被 Git 忽略。使用云端嵌入时，待嵌入的文本会发送至你配置的服务。请勿将 `.env`、API Key 或本地知识库数据提交到版本控制。

## 桌面工作台

先进入项目目录并同步依赖，再启动 PySide6 桌面应用：

```powershell
cd <项目目录>
uv sync
uv run ragdb-gui
```

如果当前终端不在项目目录（例如显示 `PS C:\Windows\system32>`），可显式指定项目路径：

```powershell
uv run --project <项目目录> ragdb-gui
```

也可使用模块入口启动：

```powershell
uv run python -m ragdb.desktop.app
```

工作台采用可折叠的分组导航，并支持跟随系统、浅色和深色主题。它包含概览、集合与资料导入、可追溯检索、持久化问答、学习产物、任务日志和环境诊断；检索结果与回答引用可在右侧详情栏核验。耗时导入、检索及模型调用在后台执行；API Key 仍需通过 `.env` 或环境变量配置。
