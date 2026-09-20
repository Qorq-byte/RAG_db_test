# 搜索元数据筛选实施计划

> 设计依据：[搜索元数据筛选设计](../specs/2026-09-20-search-metadata-filters-design.md)。
>
> 提交策略：下列每个步骤完成、测试通过后各自形成一个提交并推送到 `origin/main`；不把未完成的后续步骤混入同一提交。

## 步骤 1：受控元数据的输入、规范化与切片传播

### 修改范围

- 新增 `src/ragdb/application/metadata.py`，集中定义受控字段、文本/日期规范化、导入元数据构建、搜索筛选构建及可读的参数错误。
- 修改 `src/ragdb/cli.py`：为 `ingest file`、`ingest directory`、`ingest text` 增加重复 `--tag`、`--course`、`--author`、`--date`；但暂不公开新的搜索选项。
- 修改 `src/ragdb/application/ingestion.py`：接收规范化后的资料元数据，保存至 `Source.metadata`，并在生成 `Chunk` 时合并资料级元数据与已有解析器/位置元数据。重新导入时完整替换受控字段。
- 新增/修改 `tests/unit/test_metadata.py`、`tests/unit/test_cli.py` 和 `tests/integration/ingestion/test_local_ingestion.py`。

### 验收与测试

- 验证标签去重、NFC/大小写规范化、ISO 日期解析和非法值错误。
- 验证三个导入命令都能传递受控元数据；目录导入应用同一元数据至所有资料。
- 验证资料、切片和检索结果保留预期元数据；重新导入不会残留旧的受控字段。

```powershell
uv run pytest tests/unit/test_metadata.py tests/unit/test_cli.py tests/integration/ingestion/test_local_ingestion.py
```

### 提交边界

`feat: add controlled ingestion metadata`

## 步骤 2：SQLite 与 ChromaDB 的一致筛选表达

### 修改范围

- 修改 `src/ragdb/infrastructure/database/fts.py`，将已规范化的 tags/course/author/date 条件编译为参数化 SQLite JSON 查询；每个标签产生独立存在性条件，从而实现标签交集。
- 修改 `src/ragdb/infrastructure/vectorstore/chroma_store.py`，在向量元数据中写入课程、作者、日期标量和以标签哈希派生的内部布尔字段；将同一筛选对象编译为 ChromaDB `$and` 条件。
- 仅在 `metadata.py` 暴露后端无关的筛选对象；适配器不得自行重新解释 CLI 文本。
- 修改 `tests/integration/database/test_fts.py`、`tests/integration/vectorstore/test_chroma_store.py`，必要时新增测试夹具。

### 验收与测试

- 两个后端分别证明两个请求标签必须同时存在；任何一个缺失均不返回。
- 分别验证 course、author、日期闭区间，及它们与 source ID、资料类型的 AND 组合。
- 验证无筛选时现有检索结果不变，且非法条件不会被忽略。

```powershell
uv run pytest tests/integration/database/test_fts.py tests/integration/vectorstore/test_chroma_store.py
```

### 提交边界

`feat: filter retrieval by controlled metadata`

## 步骤 3：搜索 CLI、端到端回归与文档同步

### 修改范围

- 修改 `src/ragdb/cli.py`，为 `search` 增加重复 `--tag`、`--course`、`--author`、`--date-from`、`--date-to`，并在调用 `SearchService` 前构建和验证筛选对象。
- 如有必要，修改 `src/ragdb/application/search.py`，确保服务入口只接收已验证筛选对象，且向量与关键词路径获得同一对象。
- 修改 `tests/unit/test_cli.py`，新增或扩展 `tests/integration/test_search_cli.py`，覆盖命令行参数、结果内容、日期错误和空结果。
- 更新 `config.example.toml` 或 README（若已有此类命令示例）以展示筛选用法；不提前实施里程碑八的完整文档工作。

### 验收与测试

- 端到端验证导入带元数据的资料后，搜索的任意条件与组合条件均只返回正确资料。
- 验证标签交集、日期边界与参数错误信息。
- 运行全部回归。

```powershell
uv run pytest tests/unit/test_cli.py tests/integration/test_search_cli.py
uv run pytest
uv run python -m ragdb search --help
```

### 提交边界

`feat: expose metadata search filters`

## 完成条件

- 每一项步骤均已通过其列出的测试并已单独推送。
- 全量 `uv run pytest` 通过。
- 工作树干净，且 `task_plan.md`、`findings.md`、`progress.md` 记录最终验证结果与提交号。
