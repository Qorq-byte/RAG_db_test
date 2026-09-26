# 阶段 7：索引重建与读取可靠性

## 7.1 调查环境与可复跑实验

- 基线 `6eae658`；Windows、Python 3.11.15、Chroma 1.5.9。
- `uv.lock` SHA256：`DBD6DC306982EB533D3183E523242007A22CD7553E8CD65D348DA3A04BCB6431`。未修改依赖。
- 命令：`.venv/Scripts/python.exe -m pytest tests/integration/vectorstore/test_index_reliability.py -q`。
- 固定矩阵：默认 HNSW 参数、每集合 1/3 条、逐条/批量、两个集合、每种组合三次，共 12 例；每例检查写后查询、关闭后同进程重开、独立进程重开。无等待、无失败重试、无模型请求。
- 另一个用例测量同目录 12 个适配器的客户端引用：增长至 24（每客户端含一个 admin 引用），显式关闭底层客户端后回到基线。生产适配器当前没有公开关闭接口，也没有析构释放。
- 定向结果：13 passed in 21.15s，读取矩阵 12/12 通过。首次沙箱运行 13 项均在临时目录权限检查中失败，未执行产品逻辑；获得执行权限后运行上述结果。

- 全套基线（含新矩阵）：`.venv/Scripts/python.exe -m pytest -q`，262 passed in 66.00s；累积运行中未观察到读取异常。

## 结论与修改范围

已证明未关闭适配器会累积 Chroma 引用；这支持补全资源所有权与异常释放。**未证明引用增长导致历史 `Nothing found on disk`，本次微型索引矩阵没有复现该错误。** 不调整依赖，不新增睡眠重试，不修改用户知识库。

下一步保持现有服务接口：显式创建的适配器提供幂等 `close()` 和上下文管理；runtime 服务使用按向量操作打开/关闭的适配器，纯 SQLite 查询不打开 Chroma，CLI 和桌面任务异常退出也不遗留客户端。重建持有独立适配器直到完成或回滚。共享系统仅通过 Chroma 公共 `close()` 释放自己的引用，不直接停止其他使用者的系统。

发布验证使用本轮已生成向量，对所有非空目标集合查询并核对当前切片身份；查询失败或取消沿用暂存回滚。每个集合一次抽样验证不等于全索引质量或持久损坏审计。

## 7.2 客户端所有权

- `ChromaVectorStore.close()` 幂等；上下文退出释放；关闭后拒绝操作。默认显式创建的适配器由调用者持有和关闭。
- runtime 创建 `operation_scoped=True` 适配器，不在构造服务时打开 Chroma；每次向量操作在 `finally` 关闭，适配器可以供后续操作继续使用。适用于 CLI、目录监听、桌面导入、问答和生成的检索；服务创建失败、模型调用失败和纯 SQLite 操作均不持有客户端。
- 重建服务持有一个独立客户端，成功、取消、异常回滚后统一释放；维护服务保持每次 session 释放。
- 适配器内部锁防止同一实例操作中被关闭；所有生产 Chroma 客户端共用创建/释放锁，避免 Chroma 系统注册表创建与最后一个引用退出并发。锁不覆盖不同实例的向量查询，不直接操作 Chroma 私有注册表。
- 权衡：runtime 的每次向量操作可能重开本地系统，优先确保确定性释放；本阶段不引入连接池。私有引用计数只用于测试证据，不作为生产逻辑。

- 定向命令：`.venv/Scripts/python.exe -m pytest tests/integration/vectorstore tests/integration/test_embedding_rebuild.py tests/integration/test_index_maintenance.py tests/unit/test_model_settings_page.py -q`；85 passed in 46.36s。覆盖重复释放、异常释放、并发存活者、runtime 12 次服务调用引用恢复、重建三类退出及独立进程重开。
