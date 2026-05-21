"""Hit Rate@5 validation gate for the hybrid retriever.

This is the hard gate between Phase 2 and Phase 3: the retriever must not be
wired into the agent graph until Hit Rate@5 >= GATE_THRESHOLD against the
held-out query/chunk pairs.

Run directly:  python -m devagent.rag.validate
Exit code 0 if the gate passes, 1 if it fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from devagent.rag.hybrid_retriever import HybridRetriever, RetrievedChunk

PAIRS_PATH = Path(__file__).resolve().parent.parent.parent / "eval" / "golden" / "retrieval_pairs.yaml"
GATE_THRESHOLD = 0.75
TOP_K = 5


def _hit(chunk: RetrievedChunk, expected_file: str | None, expected_substring: str | None) -> bool:
    if expected_file:
        # code/doc chunks carry file_path; commit chunks name their files in-text
        if expected_file in chunk.metadata.get("file_path", ""):
            return True
        if expected_file in chunk.text:
            return True
    if expected_substring and expected_substring.lower() in chunk.text.lower():
        return True
    return False


def run_validation(*, verbose: bool = True) -> float:
    spec = yaml.safe_load(PAIRS_PATH.read_text())
    pairs = spec["pairs"]
    repo = spec.get("repo")
    retriever = HybridRetriever()

    hits = 0
    for pair in pairs:
        results = retriever.retrieve(pair["query"], top_k=TOP_K, repo=repo, allow_fresh=False)
        hit = any(
            _hit(c, pair.get("expected_file"), pair.get("expected_substring"))
            for c in results
        )
        hits += int(hit)
        if verbose:
            mark = "PASS" if hit else "MISS"
            cites = ", ".join(c.citation for c in results)
            print(f"  [{mark}] {pair['query'][:60]:<60} -> {cites}")

    hit_rate = hits / len(pairs)
    if verbose:
        print(f"\nHit Rate@{TOP_K}: {hit_rate:.2f} ({hits}/{len(pairs)})  "
              f"gate >= {GATE_THRESHOLD}")
    return hit_rate


def main() -> None:
    hit_rate = run_validation()
    if hit_rate >= GATE_THRESHOLD:
        print(f"GATE PASSED — retriever may be wired into the agent graph.")
        sys.exit(0)
    print(f"GATE FAILED — tune chunking / RRF k / routing before Phase 3.")
    sys.exit(1)


if __name__ == "__main__":
    main()
