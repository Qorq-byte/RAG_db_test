# Task Plan: 检索元数据筛选

## Goal

为 `ragdb search` 增加标签、课程、作者和日期筛选，并确保 SQLite 关键词与 ChromaDB 向量召回使用完全一致的筛选语义。

## Current Phase

Phase 2 — 设计已确认，等待用户审阅已写入的设计文档。

## Phases

### Phase 1: 需求与现状梳理

- [x] 确认范围为 tags、course、author、date。
- [x] 确认多个标签必须同时匹配。
- [x] 审查当前 CLI、领域模型、SQLite FTS 和 ChromaDB 筛选实现。
- **Status:** complete

### Phase 2: 设计与评审

- [x] 比较元数据 JSON、后过滤、索引字段三种方案。
- [x] 与用户确认规范化元数据和标签交集语义。
- [x] 写入设计文档并完成自审。
- [ ] 等待用户审阅设计文档。
- **Status:** in_progress

### Phase 3: 实施计划

- [ ] 将已批准设计拆成可验证的编码步骤。
- [ ] 定义每一步的测试与提交边界。
- **Status:** pending

### Phase 4: 实现与验证

- [ ] 实现元数据传入、索引传播与检索筛选。
- [ ] 运行受影响测试及完整回归。
- [ ] 每个可验证步骤单独提交并推送。
- **Status:** pending

## Decisions Made

| Decision | Rationale |
| --- | --- |
| 使用受控元数据字段 | 保证两条检索路径的行为可预测。 |
| 多标签取交集 | 用户明确要求结果包含全部请求标签。 |
| ChromaDB 每标签布尔索引字段 | 不依赖字符串数组筛选的兼容性。 |
| 不迁移或猜测旧资料元数据 | 避免悄然改变现有资料含义。 |

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| 无 | — | — |
