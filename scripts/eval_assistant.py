"""
Harness de avaliação offline (AI Evals) do Assistente Locus (Hybrid RAG).

Mede sobre o dataset padrão (evals/assistant_golden_dataset.json):
- Retrieval Recall@5: algum dos `expected_doc_slugs` apareceu no top 5?
- Keyword / Route Coverage: os termos e rotas esperados aparecem nos trechos recuperados?
- Role Boundary Compliance: rotas restritas (`forbidden_routes`, ex.: `/dashboard/convites`
  para `professor`) NUNCA aparecem nos metadados `routes` dos chunks retornados para aquele papel.
- Latência média de recuperação (embedding + pgvector + tsvector + RRF).

Sai com código != 0 caso o Retrieval Recall@5 fique abaixo de 85%.

Uso:
    uv run python scripts/eval_assistant.py
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

src_dir = str(Path(__file__).resolve().parent.parent / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from sqlalchemy import func, select

from config.settings import settings
from infra.database.models.knowledge_chunk import KnowledgeChunkModel
from infra.database.session import AsyncSessionLocal
from modules.assistant.application.use_cases.knowledge.retrieve_knowledge import (
    RetrieveKnowledgeInput,
    RetrieveKnowledgeUseCase,
)
from modules.assistant.infra.gemini.gemini_embedding_provider import GeminiEmbeddingProvider
from modules.assistant.infra.repositories.knowledge_sqlalchemy_repository import (
    KnowledgeSQLAlchemyRepository,
)
from shared.enums.user_role import UserRole

MIN_RECALL_THRESHOLD = 0.85
TOP_K = 5


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: str
    role: UserRole
    query: str
    expected_doc_slugs: list[str]
    expected_keywords: list[str]
    forbidden_routes: list[str]


@dataclass(frozen=True)
class EvalOutcome:
    case: EvalCase
    retrieved_slugs: list[str]
    recall_hit: bool
    keywords_hit: bool
    missing_keywords: list[str]
    role_compliant: bool
    leaked_routes: list[str]
    latency_ms: float


def _load_dataset(dataset_path: Path) -> list[EvalCase]:
    raw_items = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for item in raw_items:
        cases.append(
            EvalCase(
                case_id=str(item["id"]),
                category=str(item.get("category", "geral")),
                role=UserRole(str(item["role"]).lower()),
                query=str(item["query"]),
                expected_doc_slugs=list(item["expected_doc_slugs"]),
                expected_keywords=list(item.get("expected_keywords", [])),
                forbidden_routes=list(item.get("forbidden_routes", [])),
            )
        )
    return cases


async def run_evals() -> int:
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        print(
            "Erro: GEMINI_API_KEY não configurada no .env.\n"
            "Defina GEMINI_API_KEY em classroom-api/.env antes de executar o eval.",
            file=sys.stderr,
        )
        return 1

    dataset_path = (
        Path(__file__).resolve().parent.parent / "evals" / "assistant_golden_dataset.json"
    )
    if not dataset_path.exists():
        print(f"Erro: Dataset não encontrado em {dataset_path}", file=sys.stderr)
        return 1

    cases = _load_dataset(dataset_path)
    embedding_provider = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_embedding_model,
    )

    async with AsyncSessionLocal() as session:
        chunk_count = int(
            (await session.execute(select(func.count(KnowledgeChunkModel.id)))).scalar() or 0
        )
        if chunk_count == 0:
            print(
                "Erro: A tabela knowledge_chunks está vazia.\n"
                "Execute primeiro: uv run python scripts/ingest_help_docs.py",
                file=sys.stderr,
            )
            return 1

        knowledge_repo = KnowledgeSQLAlchemyRepository(session=session)
        retrieve_uc = RetrieveKnowledgeUseCase(
            knowledge_repo=knowledge_repo,
            embedding_provider=embedding_provider,
        )

        print("\n" + "=" * 92)
        print(
            f"LOCUS ASSISTANT — AVALIAÇÃO OFFLINE DE HYBRID RAG "
            f"({len(cases)} casos | {chunk_count} chunks indexados)"
        )
        print("=" * 92)
        print(
            f"{'ID':<9} | {'Papel':<11} | {'Recall@5':<8} | {'Keywords':<8} | "
            f"{'Role OK':<7} | {'Latência':<8} | Top Doc Recuperado"
        )
        print("-" * 92)

        outcomes: list[EvalOutcome] = []

        for case in cases:
            t0 = time.perf_counter()
            chunks = await retrieve_uc.execute(
                RetrieveKnowledgeInput(
                    query=case.query,
                    user_role=case.role,
                    top_k=TOP_K,
                )
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0

            retrieved_slugs = [c.doc_slug for c in chunks]
            recall_hit = any(slug in retrieved_slugs for slug in case.expected_doc_slugs)

            combined_corpus = "\n".join(
                f"{c.section_title} {' '.join(c.routes)} {c.content}" for c in chunks
            ).lower()
            missing_keywords = [
                kw for kw in case.expected_keywords if kw.lower() not in combined_corpus
            ]
            keywords_hit = len(missing_keywords) == 0

            retrieved_routes = {route for c in chunks for route in c.routes}
            leaked_routes = [
                forbidden for forbidden in case.forbidden_routes if forbidden in retrieved_routes
            ]
            role_compliant = len(leaked_routes) == 0

            outcome = EvalOutcome(
                case=case,
                retrieved_slugs=retrieved_slugs,
                recall_hit=recall_hit,
                keywords_hit=keywords_hit,
                missing_keywords=missing_keywords,
                role_compliant=role_compliant,
                leaked_routes=leaked_routes,
                latency_ms=latency_ms,
            )
            outcomes.append(outcome)

            top_doc = retrieved_slugs[0] if retrieved_slugs else "(nenhum)"
            print(
                f"{case.case_id:<9} | {case.role.value:<11} | "
                f"{'PASS' if recall_hit else 'FAIL':<8} | "
                f"{'PASS' if keywords_hit else 'MISS':<8} | "
                f"{'PASS' if role_compliant else 'LEAK':<7} | "
                f"{latency_ms:>6.0f}ms | {top_doc}"
            )

    total = len(outcomes)
    recall_passes = sum(1 for o in outcomes if o.recall_hit)
    keyword_passes = sum(1 for o in outcomes if o.keywords_hit)
    role_passes = sum(1 for o in outcomes if o.role_compliant)
    avg_latency = sum(o.latency_ms for o in outcomes) / total if total else 0.0

    recall_rate = recall_passes / total if total else 0.0
    keyword_rate = keyword_passes / total if total else 0.0
    role_rate = role_passes / total if total else 0.0

    print("-" * 92)
    print(f"Retrieval Recall@{TOP_K}:    {recall_passes}/{total} ({recall_rate * 100:.1f}%)")
    print(f"Keyword/Route Coverage: {keyword_passes}/{total} ({keyword_rate * 100:.1f}%)")
    print(f"Role Boundary Check:    {role_passes}/{total} ({role_rate * 100:.1f}%)")
    print(f"Latência Média:         {avg_latency:.0f} ms")
    print("=" * 92)

    failures = [o for o in outcomes if not o.recall_hit or not o.role_compliant]
    if failures:
        print("\nCasos com falha de Recall@5 ou Violação de Papel:")
        for f in failures:
            print(
                f'  - [{f.case.case_id}] ({f.case.role.value}) "{f.case.query}"\n'
                f"    Esperado: {f.case.expected_doc_slugs} | Obtido: {f.retrieved_slugs[:3]}"
            )
            if f.leaked_routes:
                print(f"    Rotas proibidas vazadas: {f.leaked_routes}")

    if recall_rate < MIN_RECALL_THRESHOLD:
        print(
            f"\nFALHA: Retrieval Recall@{TOP_K} ({recall_rate * 100:.1f}%) ficou abaixo da "
            f"meta mínima de {MIN_RECALL_THRESHOLD * 100:.0f}%.",
            file=sys.stderr,
        )
        return 1

    if role_passes < total:
        print(
            "\nFALHA: Violação de isolamento por papel detectada nos chunks retornados.",
            file=sys.stderr,
        )
        return 1

    print(
        f"\nSUCESSO: Retrieval Recall@{TOP_K} = {recall_rate * 100:.1f}% "
        f"(>= {MIN_RECALL_THRESHOLD * 100:.0f}%) e 100% de conformidade de papéis."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_evals()))
