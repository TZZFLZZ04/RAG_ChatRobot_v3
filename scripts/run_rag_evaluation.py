from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import deps
from app.schemas.rag_eval import RagEvaluationDataset
from app.services.rag_evaluation_service import RagEvaluationService


def parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run retrieval and answer-focused RAG evaluation.")
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to the evaluation dataset JSON file.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the evaluation report JSON.",
    )
    parser.add_argument(
        "--collection-id",
        help="Optional collection id override applied to all cases.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        help="Optional top-k override applied to all cases.",
    )
    parser.add_argument(
        "--use-hybrid-search",
        type=parse_optional_bool,
        choices=[True, False],
        help="Optional override for use_hybrid_search: true or false.",
    )
    parser.add_argument(
        "--use-rerank",
        type=parse_optional_bool,
        choices=[True, False],
        help="Optional override for use_rerank: true or false.",
    )
    parser.add_argument(
        "--answer-mode",
        choices=["off", "auto", "dataset", "generate"],
        default="auto",
        help="Answer evaluation mode: off, auto, dataset, or generate.",
    )
    parser.add_argument(
        "--llm-judge-mode",
        choices=["off", "auto", "require"],
        default="off",
        help="LLM judge mode: off, auto, or require.",
    )
    return parser


def load_dataset(dataset_path: Path) -> RagEvaluationDataset:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    return RagEvaluationDataset.model_validate(payload)


def build_report(
    *,
    dataset: RagEvaluationDataset,
    collection_id_override: str | None,
    top_k_override: int | None,
    use_hybrid_search_override: bool | None,
    use_rerank_override: bool | None,
    answer_mode: str,
    llm_judge_mode: str,
):
    retrieval_service = deps.get_retrieval_service()
    evaluation_service = RagEvaluationService(
        retrieval_service,
        settings=deps.get_settings(),
    )
    return evaluation_service.evaluate_retrieval_dataset(
        dataset,
        collection_id_override=collection_id_override,
        top_k_override=top_k_override,
        use_hybrid_search_override=use_hybrid_search_override,
        use_rerank_override=use_rerank_override,
        answer_mode=answer_mode,
        llm_judge_mode=llm_judge_mode,
    )


def main() -> None:
    args = build_argument_parser().parse_args()
    dataset_path = Path(args.dataset)
    report_output_path = Path(args.output) if args.output else None

    dataset = load_dataset(dataset_path)
    report = build_report(
        dataset=dataset,
        collection_id_override=args.collection_id,
        top_k_override=args.top_k,
        use_hybrid_search_override=args.use_hybrid_search,
        use_rerank_override=args.use_rerank,
        answer_mode=args.answer_mode,
        llm_judge_mode=args.llm_judge_mode,
    )

    report_json = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if report_output_path is not None:
        report_output_path.parent.mkdir(parents=True, exist_ok=True)
        report_output_path.write_text(report_json, encoding="utf-8")

    print(report_json)


if __name__ == "__main__":
    main()
