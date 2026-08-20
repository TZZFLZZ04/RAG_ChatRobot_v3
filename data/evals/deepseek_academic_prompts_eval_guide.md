# DeepSeek 学术论文指令 PDF 评测操作指南

## 交付物

- 数据集：`data/evals/deepseek_academic_prompts_eval.json`
- 来源：`50个顶级的DeepSeek学术论文指令，强烈建议收藏！.pdf`
- 案例数：31
- 标签方式：使用 `expected_sources` 精确匹配来源文件名，不绑定易变化的 chunk ID。

## 评测目的

这份数据集用于检查系统能否从 PDF 中召回正确内容，并基于召回片段回答“某条学术指令的用途、约束或输出格式”。它适合比较递归切分、语义切分、混合检索、重排和上下文感知检索等方案。

当前递归切分已经实现并通过代码测试，因此第一次运行的报告应作为“当前递归切分基线”。后续每次只改变一个变量，重建同一集合索引后再运行完全相同的数据集。

## 第一步：上传并完成入库

1. 启动 PostgreSQL 与 Redis：

   ```powershell
   docker compose up -d postgres redis
   ```

2. 启动 API：

   ```powershell
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. 另开终端启动 Windows Celery Worker：

   ```powershell
   celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo
   ```

4. 在页面中创建一个独立评测集合，上传源 PDF，并等待文档状态变为 `indexed`。
5. 记录该集合的 `collection_id`。数据集没有硬编码集合 ID，运行时必须使用 `--collection-id` 传入。

如果该 PDF 已经存在于知识库中，也可以直接使用其当前集合，但必须确认来源文件名与数据集中的 `expected_sources` 完全一致。

## 第二步：校验数据集格式

```powershell
python -c "from pathlib import Path; from app.schemas.rag_eval import RagEvaluationDataset; p=Path('data/evals/deepseek_academic_prompts_eval.json'); d=RagEvaluationDataset.model_validate_json(p.read_text(encoding='utf-8')); print(d.dataset_name, len(d.cases))"
```

预期输出：

```text
deepseek-academic-prompts-eval 31
```

## 第三步：运行检索基线

将 `<collection_id>` 替换为实际集合 ID：

```powershell
python scripts/run_rag_evaluation.py `
  --dataset data/evals/deepseek_academic_prompts_eval.json `
  --collection-id <collection_id> `
  --answer-mode off `
  --llm-judge-mode off `
  --use-hybrid-search true `
  --use-rerank true `
  --output data/evals/reports/deepseek_recursive_baseline_retrieval.json
```

重点检查：

- `summary.source_metrics.source_hit_rate`
- `summary.primary_metrics.hit_rate_at_k`
- `summary.primary_metrics.mrr_at_k`
- `summary.primary_metrics.ndcg_at_k`
- `case_results[].retrieved`

由于本数据集只使用来源级标签，来源命中率是最稳定的主指标。还应人工查看每个失败案例的前五个片段是否真正包含答案。

## 第四步：运行端到端回答基线

确保 `.env` 中存在有效的 `OPENAI_API_KEY`：

```powershell
python scripts/run_rag_evaluation.py `
  --dataset data/evals/deepseek_academic_prompts_eval.json `
  --collection-id <collection_id> `
  --answer-mode generate `
  --llm-judge-mode auto `
  --use-hybrid-search true `
  --use-rerank true `
  --output data/evals/reports/deepseek_recursive_baseline_answer.json
```

重点检查：

- `summary.answer_metrics.overall_answer_score`
- `summary.answer_metrics.expected_term_recall`
- `summary.answer_metrics.groundedness_score`
- `summary.answer_metrics.unsupported_statement_count`
- `summary.llm_judge_metrics`（如果 Judge 成功运行）
- `case_results[].answer` 和 `case_results[].notes`

## 第五步：人工复核

至少逐条复核以下情况：

1. 来源未命中的案例。
2. `expected_term_recall < 1` 的案例。
3. `unsupported_statement_count > 0` 的案例。
4. 修改前正确、修改后错误的回归案例。
5. 答案位于跨页或跨段落位置的案例。

人工判断时回答三个问题：

- 召回片段是否包含回答问题所需的证据？
- 最终答案是否只使用了文档中存在的信息？
- 答案是否遗漏了问题要求的关键条件或输出格式？

## 第六步：后续方案的前后对比

后续实现新的切分或检索方案后，先重建同一集合：

```powershell
python scripts/rebuild_vector_indexes.py --backend faiss --collection-id <collection_id>
```

重建脚本会先删除旧索引。执行前应确认原 PDF 可重新入库，并优先在独立评测集合操作。如果使用 Milvus，将 `faiss` 改为 `milvus`。

随后用与基线完全相同的模型、Embedding、Top-K、混合检索和重排参数重新运行，并使用新的输出文件名，例如：

```powershell
python scripts/run_rag_evaluation.py `
  --dataset data/evals/deepseek_academic_prompts_eval.json `
  --collection-id <collection_id> `
  --answer-mode generate `
  --llm-judge-mode auto `
  --use-hybrid-search true `
  --use-rerank true `
  --output data/evals/reports/deepseek_after_next_change.json
```

## 建议验收门槛

- 来源命中率、MRR 和 nDCG 不得下降。
- `overall_answer_score` 与 groundedness 不得下降。
- `unsupported_statement_count` 不得增加。
- 目标失败案例应有明确改善，且不能以其他案例明显回退为代价。
- 同时记录 chunk 数量、索引时间和 P95 检索延迟。

## 当前限制

现有 `RagEvaluationCase` 要求每个案例至少定义 chunk、document 或 source 相关标签，因此该数据集只包含文档可回答问题。若要测试“文档没有答案时是否正确拒答”，需要后续增加 `answerable` 标记和拒答/幻觉指标。
