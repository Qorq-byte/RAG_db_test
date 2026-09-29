# 复杂文档离线检索评估（2026-09-29）

本轮补充一个固定的 5 资料 / 8 查询评估集，覆盖 Markdown 标题、Word 段落与表格、带文字层 PDF、普通文本。评估在临时知识库中真正创建这些文件，经过项目现有解析、切片、SQLite/Chroma 写入和混合检索路径；不是把全部资料直接作为手工文本导入。

## 复现

使用 Python 3.11 与项目依赖，在仓库根目录运行：

```powershell
uv run ragdb --config config.example.toml evaluate run .data/complex-evaluation-report.json --dataset src/ragdb/evaluation_data/complex_documents.json --offline
```

输出文件已存在时需换一个文件名。`--offline` 使用项目内的字符双字哈希向量，只检查离线管线，不下载模型或调用云端 API。仅评估合成文本，临时库运行后清理；报告默认留在被 Git 忽略的 `.data/`。

## 结果

| 项目 | 结果 |
| --- | ---: |
| 文档 | 5：Markdown 1、DOCX 1、PDF 1、普通文本 2 |
| 标注查询 | 8：标题/故障、Word 段落/表格、PDF 校验/凭据、普通文本 |
| Recall@3 | 1.0 |
| MRR@3 | 1.0 |
| nDCG@3 | 1.0 |
| 完整回归 | 22 项通过：指标、CLI、格式拒绝与解析器 |

报告样本很小，查询使用明确的资料措辞，不能作为真实业务检索质量、跨语言能力、OCR 成功率或真实嵌入模型效果的结论。PDF 样本有文本层，不代表扫描 PDF；云端服务商账号未参与。使用自己的资料评估时，应按 [README 的评估命令](../../README.md#技术结构与开发) 与 [进阶指南](../user-guide.md#检索质量评估) 提供独立标注集，核对逐题 `ranked_sources` 与指标。单一来源的多个切片在指标中按来源去重。

## 安全与实现边界

文件评估只支持 `text`、`markdown`、`docx`、`pdf` 四种声明格式；含文件的资料 ID 仅允许字母、数字、下划线和连字符，防止把生成文件写出隔离目录。`evaluation_id` 始终由资料 ID 决定，外部 `metadata` 不得覆盖其标签。评估文件全为公开合成内容，不应把含个人数据的实际文档放入仓库。
