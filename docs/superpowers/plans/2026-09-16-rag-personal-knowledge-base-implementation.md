# RAG 个人知识库实施计划

## 1. 实施目标

本计划把已批准的第一阶段设计拆分为 8 个可独立验证的里程碑。每个里程碑使用独立功能分支，完成测试后提交并通过 Pull Request 合并到 `main`。

第一阶段结束时，Windows 用户应能通过 `ragdb` 命令创建多个知识集合，导入约定的全部资料来源，增量维护 ChromaDB 与 SQLite 索引，并执行带完整出处的混合检索。

## 2. 技术基线

- Python：3.11.15。
- 环境与依赖：`uv`。
- CLI：Typer + Rich。
- 配置：Pydantic Settings，读取 `config.toml` 和 `.env`。
- 向量存储：ChromaDB 持久化客户端。
- 资料目录与关键词检索：Python `sqlite3` + SQLite FTS5。
- 本地嵌入：Sentence Transformers，默认使用可配置的中英双语轻量模型。
- 云端嵌入：OpenAI 兼容接口，模型名、Base URL 和密钥均可配置。
- 文档解析：PyMuPDF、python-docx、python-pptx，以及项目内的文本和代码解析器。
- 网页：HTTPX + Trafilatura；遵守 `robots.txt`。
- 目录监听：Watchdog。
- 测试：pytest。

依赖版本在首次搭建时依据 Python 3.11 的实际兼容结果锁入 `uv.lock`，不在设计文档中预先写死。

## 3. 目标目录结构

```text
RAG_db_test/
├── pyproject.toml
├── uv.lock
├── README.md
├── config.example.toml
├── .env.example
├── .gitignore
├── docs/
│   └── superpowers/
│       ├── specs/
│       └── plans/
├── src/ragdb/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── logging.py
│   ├── domain/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   └── ports.py
│   ├── application/
│   │   ├── collections.py
│   │   ├── ingestion.py
│   │   ├── search.py
│   │   ├── sources.py
│   │   └── diagnostics.py
│   └── infrastructure/
│       ├── database/
│       ├── vectorstore/
│       ├── embeddings/
│       ├── parsers/
│       ├── chunking/
│       ├── retrieval/
│       ├── web/
│       ├── github/
│       └── watcher/
└── tests/
    ├── unit/
    ├── integration/
    ├── fixtures/
    └── samples/
```

## 4. 领域约定

在实现前固定以下跨模块契约：

- `Collection`：知识集合，使用 UUID 作为内部标识，名称仅用于展示。
- `Source`：一份可追踪的原始资料，保存来源、哈希、状态和用户元数据。
- `Document`：解析器输出的标准化文档，可包含多个有位置标记的内容单元。
- `Chunk`：进入检索索引的最小文本单元，拥有稳定 ID、位置和版本代次。
- `IngestionTask`：一次导入或同步任务，记录成功、跳过、更新与失败项。
- `SearchHit`：统一检索结果，包含文本、来源、各阶段评分和排序原因。

解析器、嵌入模型、向量库和重排序器都通过 `domain/ports.py` 中的协议接口接入。应用服务只能依赖这些协议和领域模型，不能直接依赖第三方库。

## 5. 里程碑一：项目骨架

分支：`feature/project-bootstrap`

### 任务 1.1：初始化 Python 包

新增或修改：

- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `.gitignore`
- `src/ragdb/__init__.py`
- `src/ragdb/__main__.py`
- `tests/unit/test_package.py`

实现内容：

- 创建 `src` 布局的可安装包。
- 设置 Python 约束为 `>=3.11,<3.12`。
- 注册 `ragdb = "ragdb.cli:app"` 命令入口。
- 将 `.venv/`、`.data/`、`.env`、缓存、日志和临时仓库加入忽略规则。
- 添加最小包导入测试和版本测试。

验证命令：

```powershell
uv sync
uv run python -m ragdb --help
uv run pytest tests/unit/test_package.py
```

### 任务 1.2：配置、日志和 CLI 外壳

新增或修改：

- `src/ragdb/config.py`
- `src/ragdb/logging.py`
- `src/ragdb/cli.py`
- `config.example.toml`
- `.env.example`
- `tests/unit/test_config.py`
- `tests/unit/test_cli.py`

实现内容：

- 定义存储、嵌入、分块、检索、抓取和重排序配置模型。
- 配置优先级为：CLI 临时参数、环境变量、`config.toml`、默认值。
- 敏感字段只允许来自环境变量，并在日志中脱敏。
- 建立所有计划命令组的 CLI 外壳，未实现命令返回清晰状态。
- 提供中文帮助文本和统一退出码。

里程碑验收：全新环境可通过 `uv sync` 安装，`ragdb --help` 正常显示中文命令结构，配置测试通过。

## 6. 里程碑二：集合与存储

分支：`feature/collections-storage`

### 任务 2.1：领域模型和端口

新增：

- `src/ragdb/domain/models.py`
- `src/ragdb/domain/enums.py`
- `src/ragdb/domain/errors.py`
- `src/ragdb/domain/ports.py`
- `tests/unit/domain/test_models.py`

实现不可变标识、状态枚举、元数据验证和各基础设施协议。模型只保存业务含义，不导入 ChromaDB、SQLite 或 Typer。

### 任务 2.2：SQLite 资料目录

新增：

- `src/ragdb/infrastructure/database/schema.py`
- `src/ragdb/infrastructure/database/repository.py`
- `src/ragdb/infrastructure/database/fts.py`
- `tests/integration/database/test_repository.py`
- `tests/integration/database/test_fts.py`

数据库表至少包含 `collections`、`sources`、`chunks`、`ingestion_tasks`、`task_items` 和 `operation_logs`，并建立 `chunks_fts` 虚拟表。使用 `PRAGMA user_version` 管理轻量模式升级，不引入独立迁移框架。

### 任务 2.3：ChromaDB 适配器

新增：

- `src/ragdb/infrastructure/vectorstore/chroma_store.py`
- `tests/integration/vectorstore/test_chroma_store.py`

集合显示名不直接作为 ChromaDB 名称，而是映射到稳定 UUID。实现批量写入、按资料和代次删除、元数据筛选、向量查询和测试用临时持久化目录。

### 任务 2.4：集合命令

新增或修改：

- `src/ragdb/application/collections.py`
- `src/ragdb/cli.py`
- `tests/integration/test_collection_cli.py`

完成 `collection create|list|info|delete`。删除操作要求确认，并同时清理 SQLite 与 ChromaDB 数据。

里程碑验收：可创建多个独立集合；重启进程后集合仍存在；删除一个集合不影响其他集合。

## 7. 里程碑三：本地资料导入

分支：`feature/document-ingestion`

### 任务 3.1：解析器注册表

新增：

- `src/ragdb/infrastructure/parsers/registry.py`
- `src/ragdb/infrastructure/parsers/text.py`
- `src/ragdb/infrastructure/parsers/markdown.py`
- `src/ragdb/infrastructure/parsers/pdf.py`
- `src/ragdb/infrastructure/parsers/word.py`
- `src/ragdb/infrastructure/parsers/powerpoint.py`
- `src/ragdb/infrastructure/parsers/code.py`
- `tests/unit/parsers/`
- `tests/samples/`

每个解析器输出统一 `Document`，并尽可能保留标题、页码、幻灯片、代码语言和行号。PDF 解析器检测文本密度并返回“建议 OCR”状态；OCR 实现保持可选依赖。

### 任务 3.2：结构化分块

新增：

- `src/ragdb/infrastructure/chunking/strategy.py`
- `src/ragdb/infrastructure/chunking/text.py`
- `src/ragdb/infrastructure/chunking/code.py`
- `tests/unit/chunking/`

普通文本优先沿标题、段落和句子边界分块；代码优先沿文件、类和函数边界分块。限制字符或令牌近似长度，并保留可配置重叠。稳定 Chunk ID 由资料 ID、内容哈希、位置和分块配置共同生成。

### 任务 3.3：哈希与本地导入服务

新增或修改：

- `src/ragdb/application/ingestion.py`
- `src/ragdb/application/sources.py`
- `src/ragdb/cli.py`
- `tests/integration/ingestion/test_local_ingestion.py`

完成单文件、目录和手动文本导入。目录导入使用明确的扩展名允许列表，忽略隐藏目录、依赖目录和超大文件。内容哈希未变化则跳过，变化则创建新代次。

里程碑验收：所有本地格式均有代表性样例；中文路径可正常导入；重复导入不会产生重复资料或切片。

## 8. 里程碑四：嵌入与索引

分支：`feature/embeddings-indexing`

### 任务 4.1：嵌入模型适配器

新增：

- `src/ragdb/infrastructure/embeddings/local.py`
- `src/ragdb/infrastructure/embeddings/openai_compatible.py`
- `src/ragdb/infrastructure/embeddings/factory.py`
- `tests/unit/embeddings/`

本地适配器延迟加载模型，并支持 CPU 批处理和归一化；云端适配器支持可配置 Base URL、模型和超时。测试使用替身模型，不下载真实权重，也不调用真实 API。

### 任务 4.2：可恢复索引事务

新增或修改：

- `src/ragdb/application/ingestion.py`
- `src/ragdb/infrastructure/database/repository.py`
- `src/ragdb/infrastructure/vectorstore/chroma_store.py`
- `tests/integration/ingestion/test_index_lifecycle.py`

实现按资料代次更新：先生成并写入新代次向量，再在 SQLite 事务中切换当前代次，最后清理旧向量。中断时保留上一代有效索引，并在下次启动时清理孤立代次。

### 任务 4.3：进度与任务记录

完成批量进度、失败隔离、恢复提示以及成功/跳过/更新/失败汇总。嵌入失败不得删除已有有效索引。

里程碑验收：本地与云端适配器可通过配置切换；模拟中断后旧索引仍可查询；恢复后可完成更新。

## 9. 里程碑五：混合检索

分支：`feature/hybrid-search`

### 任务 5.1：双路召回与融合

新增：

- `src/ragdb/infrastructure/retrieval/vector.py`
- `src/ragdb/infrastructure/retrieval/keyword.py`
- `src/ragdb/infrastructure/retrieval/fusion.py`
- `src/ragdb/application/search.py`
- `tests/unit/retrieval/`
- `tests/integration/search/test_hybrid_search.py`

向量召回使用 ChromaDB；关键词召回使用 FTS5 的 BM25 排序；两路结果通过 RRF 融合并按 Chunk ID 去重。过滤条件必须同时应用于两条召回路径。

### 任务 5.2：可选重排序

新增：

- `src/ragdb/infrastructure/retrieval/reranker.py`
- `tests/unit/retrieval/test_reranker.py`

定义重排序端口并提供 Sentence Transformers CrossEncoder 适配器。默认关闭且不预加载模型；模型名称、候选数量和批大小可配置。

### 任务 5.3：检索命令与出处

完成 `ragdb search`，输出原文、高亮、路径或 URL、页码/幻灯片/代码行、召回方式和评分。支持标签、课程、作者、日期和资料类型筛选。

里程碑验收：固定测试语料能证明语义召回与精确术语召回均生效；RRF 顺序可重复；每条结果都能定位到原始资料。

## 10. 里程碑六：网页与 GitHub 导入

分支：`feature/web-github-import`

### 任务 6.1：受限网页抓取

新增：

- `src/ragdb/infrastructure/web/crawler.py`
- `src/ragdb/infrastructure/web/robots.py`
- `src/ragdb/infrastructure/web/extractor.py`
- `tests/unit/web/`
- `tests/integration/web/test_crawl.py`

实现同域限制、URL 规范化、循环去重、`robots.txt`、速率限制、深度限制、页面上限和超时重试。集成测试使用本地 HTTP 测试服务器，不访问公网。

### 任务 6.2：公开 GitHub 仓库导入

新增：

- `src/ragdb/infrastructure/github/importer.py`
- `src/ragdb/infrastructure/github/filters.py`
- `tests/integration/github/test_public_repo_import.py`

通过系统 Git 客户端执行浅克隆，将临时副本放在 `.data/cache/repos/`。只接受公开 HTTPS URL，过滤 `.git`、依赖、构建产物、二进制文件和超大文件。测试使用本地 Git 仓库夹具。

里程碑验收：网页抓取不会越过配置域名或页面上限；仓库导入保留相对路径和代码语言；重复抓取能正确更新资料。

## 11. 里程碑七：监听与资料管理

分支：`feature/watch-management`

### 任务 7.1：目录监听

新增：

- `src/ragdb/infrastructure/watcher/service.py`
- `src/ragdb/infrastructure/watcher/state.py`
- `tests/integration/watcher/test_sync.py`

对高频文件事件进行去抖。新增和修改触发增量导入；删除触发索引清理；移动事件根据内容哈希优先识别为路径更新，避免不必要的重新嵌入。

### 任务 7.2：资料与索引维护命令

新增或修改：

- `src/ragdb/application/sources.py`
- `src/ragdb/cli.py`
- `tests/integration/test_source_cli.py`

完成 `watch start|status|stop`、`source list|show|delete` 和 `reindex`。所有删除操作写入操作日志；重建必须明确集合和嵌入配置。

里程碑验收：测试目录中的新增、修改、移动和删除最终与索引一致；停止监听后不再处理事件。

## 12. 里程碑八：诊断、文档与最终验收

分支：`feature/cli-polish`

### 任务 8.1：诊断命令

新增：

- `src/ragdb/application/diagnostics.py`
- `tests/integration/test_doctor.py`

`ragdb doctor` 检查 Python、配置、目录写权限、SQLite FTS5、ChromaDB、本地模型、云端配置、Git 和可选 OCR。每项输出通过、警告或失败，以及可执行的修复建议。

### 任务 8.2：README 和使用示例

新增或修改：

- `README.md`
- `config.example.toml`
- `.env.example`

README 覆盖安装、初始化、集合管理、各种导入方式、检索、监听、重建、配置、安全说明和常见故障。示例不得包含真实密钥或个人路径。

### 任务 8.3：最终回归

执行：

```powershell
uv sync
uv run pytest
uv run python -m ragdb doctor
uv run python -m ragdb --help
```

在一个全新的临时数据目录中完成手工验收：创建两个集合，分别导入中文文档与代码资料，重复导入并修改源文件，执行关键词、语义、过滤和重排序检索，确认每条结果均有正确出处。

## 13. 提交与 Pull Request 规则

- 每个里程碑从最新 `main` 创建对应功能分支。
- 每个提交只包含一个可说明、可验证的逻辑变化。
- 提交前运行受影响的单元和集成测试；Pull Request 前运行该里程碑全部测试。
- Pull Request 描述包含范围、验证命令、已知限制和设计文档链接。
- 不提交 `.env`、`.data/`、模型权重、抓取缓存、用户资料或生成日志。
- 合并后删除功能分支，再开始下一里程碑。

## 14. 实施顺序与停止条件

严格按里程碑一至八推进。若某个第三方依赖不兼容 Python 3.11 或 Windows，先在当前分支用最小复现确认，再选择同职责替代库；不得通过改变领域接口绕过问题。

出现以下情况时暂停并回到设计确认：

- 需要把第一阶段改为服务端或多用户系统。
- 需要导入私有 GitHub 仓库或绕过网站抓取规则。
- 需要更换 ChromaDB、SQLite 或 Python 版本。
- 需要提前加入大语言模型问答或桌面界面。
