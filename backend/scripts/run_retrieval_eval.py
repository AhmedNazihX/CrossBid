"""S7.1 — put the retrieval answer key to the real chat agent and score what comes back.

    DATABASE_URL=postgresql://crossbid:crossbid@localhost:55432/crossbid_eval \
      uv run python scripts/run_retrieval_eval.py de fr en

Needs `scripts/index_pack.py` to have run against the same database. Writes
`tests/fixtures/retrieval/<pack>.samples.json`, so the ragas scoring and the report can be
re-run offline without asking the agent 30 questions again.

**It asks the product, not a reconstruction of it.** Every question goes through
`openrouter_chat` and `build_chat_graph` — the same context, tools and model the
`POST /bids/{id}/chat` route builds — because a retrieval score measured against a
hand-rolled search loop would describe something no bidder can reach. The one thing it does
differently is keep the graph's messages: `run_chat_turn` returns only the delivered
`ChatTurn`, and `retrieved_contexts` has to come from the ledger, which is every passage the
agent *retrieved* rather than the subset it chose to cite (`crossbid/eval/retrieval.py` says
why that distinction decides the number).

Each question is asked on its own thread. Sharing one would let question 12 be answered from
what question 11 retrieved, and the metric would then be measuring a conversation rather than
a retrieval.

Cost: one cheap-model chat turn per question plus its embedding — cents for all ninety.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.messages import HumanMessage  # noqa: E402

from crossbid.agent.chat_graph import (  # noqa: E402
    build_chat_graph,
    ledger_of,
    openrouter_chat,
)
from crossbid.db import Database  # noqa: E402
from crossbid.eval.packrun import PACKS, TenderPack  # noqa: E402
from crossbid.eval.questions import QuestionSet, load_question_set  # noqa: E402
from crossbid.models.review import ChatTurn  # noqa: E402
from crossbid.settings import SettingsError, load_settings  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index_pack import ids_for  # noqa: E402

RETRIEVAL_DIR = BACKEND_DIR / "tests" / "fixtures" / "retrieval"
INPUT_ERROR = 2


def question_set_path(pack: TenderPack) -> Path:
    return RETRIEVAL_DIR / f"{pack.name}.questions.yaml"


def samples_path(pack: TenderPack) -> Path:
    return RETRIEVAL_DIR / f"{pack.name}.samples.json"


async def _ask(graph: object, question: str, thread_id: str) -> tuple[ChatTurn, list[str]]:
    """One question on a fresh thread: the delivered answer, and everything retrieved."""
    result = await graph.ainvoke(  # type: ignore[attr-defined]
        {"messages": [HumanMessage(content=question)], "pending": 0, "answer": None},
        {"configurable": {"thread_id": thread_id}},
    )
    turn = ChatTurn.model_validate(result["answer"])
    contexts = [
        citation.quote
        for retrieved in ledger_of(result["messages"])
        for citation in retrieved.citations
        if citation is not None and citation.quote
    ]
    return turn, contexts


async def _collect(database: Database, settings: object, pack: TenderPack) -> Path:
    question_set: QuestionSet = load_question_set(question_set_path(pack))
    company_id, bid_id = ids_for(pack)

    samples: list[dict[str, object]] = []
    async with openrouter_chat(
        settings,  # type: ignore[arg-type]
        database,
        company_id=str(company_id),
        bid_id=str(bid_id),
        language=pack.bidder_language,
    ) as context:
        graph = build_chat_graph(context)
        for question in question_set.questions:
            thread = f"eval:{pack.name}:{question.id}:{uuid.uuid4()}"
            turn, contexts = await _ask(graph, question.question, thread)
            samples.append(
                {
                    "id": question.id,
                    "label_id": question.label_id,
                    "question": question.question,
                    "reference": question.reference,
                    "reference_contexts": list(question.reference_contexts),
                    "doc": question.doc,
                    "page": question.page,
                    "answer": turn.content,
                    "retrieved_contexts": contexts,
                    "citations": [
                        {"document_name": c.document_name, "page": c.page}
                        for c in turn.citations
                    ],
                }
            )
            print(
                f"  {question.id}: {len(contexts)} passages, {len(turn.citations)} citation(s)",
                flush=True,
            )

    path = samples_path(pack)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"fixture_dir": pack.fixture_dir, "samples": samples},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    retrieved = sum(1 for sample in samples if sample["retrieved_contexts"])
    print(
        f"{pack.name}: {retrieved}/{len(samples)} questions retrieved something -> {path.name}"
    )
    return path


async def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask the retrieval key. Costs cents.")
    parser.add_argument("packs", nargs="+", choices=sorted(PACKS))
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR
    dsn = settings.env.database_url
    if dsn is None:
        print("DATABASE_URL is not set — point it at the indexed throwaway", file=sys.stderr)
        return INPUT_ERROR

    database = await Database.connect(dsn.get_secret_value())
    try:
        for name in args.packs:
            print(f"asking {name} …", flush=True)
            await _collect(database, settings, PACKS[name])
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
