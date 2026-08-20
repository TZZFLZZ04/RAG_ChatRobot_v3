# Repository Guidelines

## 项目结构与模块组织

后端代码位于 `app/`：`api/v1/` 定义 FastAPI 路由，`services/` 承载业务流程，`repositories/` 封装数据库访问，`schemas/` 与 `db/models/` 分别存放 Pydantic 和 SQLAlchemy 模型。RAG 相关能力位于 `rag/`，向量后端适配器位于 `vectorstores/`，Celery 配置与任务位于 `workers/`。静态前端在 `app/frontend/`，当前是生产化工作台风格的原生 HTML/CSS/JS。数据库迁移在 `alembic/versions/`，脚本在 `scripts/`，测试集中于 `tests/`。`docs/` 存放前端变更说明，`proces.md` 存放后续 RAG 评测改进与 LangSmith 接入流程。运行时上传、索引、评估数据和报告位于 `data/`，不要提交真实数据或本地生成产物。

## 构建、测试与本地开发

- `pip install -r requirements.txt`：安装 Python 3.11 依赖。
- `Copy-Item .env.example .env`：创建本地配置并填写密钥。
- `docker compose up -d postgres redis`：启动本地开发必需服务。
- `docker compose --profile milvus up -d postgres redis etcd minio milvus`：使用 Milvus 时启动完整依赖。
- `alembic upgrade head`：应用数据库迁移。
- `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`：启动 API 与前端。
- `celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo`：在 Windows 启动 Celery Worker。
- `docker compose --profile milvus up --build`：构建并运行全 Docker Milvus 服务栈。
- `python -m pytest`：运行完整测试套件。

## 编码风格与命名

Python 使用 4 空格缩进、类型注解和 `from __future__ import annotations`。模块、函数和变量采用 `snake_case`，类采用 `PascalCase`，常量采用 `UPPER_SNAKE_CASE`。保持分层边界：路由只处理 HTTP 和依赖注入，业务规则放入 service，持久化逻辑放入 repository。仓库未配置统一 formatter/linter；提交前遵循相邻文件风格，保持导入分组、函数简短和返回类型清晰。

## 测试规范

使用 pytest 与 FastAPI `TestClient`。测试文件命名为 `test_<功能>.py`，测试函数命名为 `test_<行为>()`；外部依赖优先使用 `Fake*`、依赖覆盖或 monkeypatch 隔离。新增或修复行为必须补充 API、service、worker、RAG 或页面契约测试。常用定向测试示例：`python -m pytest tests/test_splitters.py tests/test_task_queue_service.py tests/test_web_page.py -q`。Milvus 集成测试默认跳过，启用前启动 Milvus 并设置 `TEST_MILVUS_ENABLED=1`。

## 前端协作注意事项

首页工作台使用真正的视图切换：侧栏按钮通过 `data-view` / `data-view-panel` 切换 overview、knowledge、documents、chat，URL hash 与 active state 同步，不要退回同页锚点滚动。文档任务是独立视图，包含自己的 `documentsCollectionSelect`，需与 `collectionSelect` 保持同步。三份前端脚本都应使用 `extractErrorMessage()` 展示 FastAPI 422 `detail[]` 和后端 `message`。修改 HTML/CSS/JS 时同步更新 `tests/test_web_page.py`，并保持静态资源版本一致。

## RAG 与评估注意事项

递归切分器已显式支持段落、换行、中英文句末标点、分句标点、逗号、空格和字符兜底，并保留句末标点。修改切分规则后，必须重建实际使用后端的 FAISS/Milvus 索引。RAG 评估通过 Celery 后台运行：`POST /api/v1/evaluations/rag/run` 返回 `202` 和任务 ID，`GET /api/v1/evaluations/rag/runs/{task_id}` 查询进度；保持 `CELERY_TASK_IGNORE_RESULT=false`，否则进度不可用。

`proces.md` 仅是待实施流程，不代表 evidence 标签、required facts、独立 Judge、细粒度 tracing 或 LangSmith adapter 已完成。实施这些评测改进时应按文档分阶段推进，先修正 source-only 指标语义，再引入稳定 evidence schema。

## 提交与合并请求

当前工作副本未提供可读取的 Git 历史。提交信息使用简短祈使句并标明范围，例如 `fix: enforce owner scope in document lookup`；一次提交只处理一个逻辑变更。PR 应说明问题、实现方案、配置或迁移影响及验证命令，关联相关 issue；前端变更附截图，API 变更附请求/响应示例。

## 安全与配置

不要提交 `.env`、API 密钥、JWT 密钥、真实文档、生成索引或本地报告。新增配置时同步更新 `.env.example`。生产环境设置 `DB_AUTO_INIT=false`，仅通过 Alembic 管理 schema；文件路径必须经过 `app/core/path_utils.py` 的安全处理。
