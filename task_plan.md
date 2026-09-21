# Task Plan: 网页与公开 GitHub 仓库导入

## Goal

完成第一阶段的第六里程碑：受限网页抓取和公开 GitHub 仓库导入；每个完成步骤测试、提交并推送 GitHub。

## Current Phase

设计规格已获用户批准，正在记录并推送；待用户审阅已提交规格后生成详细实施计划。

## Phases

### Phase 1: 需求与现状梳理

- [x] 审查既有里程碑、CLI、配置和本地导入流水线。
- [x] 确认严格按既有里程碑顺序，从第六里程碑继续。
- **Status:** complete

### Phase 2: 设计与评审

- [x] 比较复用本地导入、独立安全适配器、手写 API 三种方案。
- [x] 用户确认采用独立受限适配器方案。
- [x] 写入设计文档并完成自审。
- [ ] 用户审阅已提交的设计文档。
- **Status:** in_progress

### Phase 3: 实施计划

- [ ] 将已批准设计拆成可验证的编码步骤。
- [ ] 定义每一步的测试与提交边界。
- **Status:** pending

### Phase 4: 实现与验证

- [ ] 实现网页抓取、网页导入、GitHub 仓库导入。
- [ ] 运行受影响测试及完整回归。
- [ ] 每个可验证步骤单独提交并推送。
- **Status:** pending

## Decisions Made

| Decision | Rationale |
| --- | --- |
| 独立网页与仓库适配器 | 保留安全边界、来源标识与可重复导入语义。 |
| HTTPX 与 Trafilatura | 提供可测试请求边界和稳定正文提取。 |
| 系统 Git 浅克隆 | 不需 GitHub 令牌，且可保留可追溯的本地文件结构。 |
| 仅公开 GitHub HTTPS | 不处理认证、不接受任意远端地址。 |

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| 无 | — | — |
