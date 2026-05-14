"""Turn RawDocs into LlamaIndex TextNodes.

Code is AST-chunked with CodeSplitter when a tree-sitter grammar is available,
otherwise it falls back to a line-aware splitter. Text (issues, docs, commits)
uses a token-based SentenceSplitter. Source metadata rides on every node so
retrieved chunks can cite file:line / issue# / commit SHA.
"""

from __future__ import annotations

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode

from devagent.ingestion.fetchers import RawDoc

# file extension -> CodeSplitter (tree-sitter) language name
_EXT_TO_LANG = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go",
    ".rs": "rust", ".java": "java", ".rb": "ruby",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".sh": "bash",
}

_text_splitter = SentenceSplitter(chunk_size=512, chunk_overlap=64)
# fallback for code when tree-sitter grammar is missing: keep lines intact
_code_fallback = SentenceSplitter(chunk_size=900, chunk_overlap=100, paragraph_separator="\n\n")

# cache of language -> CodeSplitter instance (or None if unavailable)
_code_splitters: dict[str, object | None] = {}


def _lang_for(file_path: str) -> str | None:
    for ext, lang in _EXT_TO_LANG.items():
        if file_path.endswith(ext):
            return lang
    return None


def _get_code_splitter(language: str):
    if language in _code_splitters:
        return _code_splitters[language]
    try:
        from llama_index.core.node_parser import CodeSplitter

        splitter = CodeSplitter(language=language, chunk_lines=60, chunk_lines_overlap=10)
        # force a parse to surface a missing-grammar error now, not mid-ingest
        splitter.split_text("x = 1\n")
        _code_splitters[language] = splitter
    except Exception:  # noqa: BLE001 — any tree-sitter failure -> fallback
        _code_splitters[language] = None
    return _code_splitters[language]


def chunk_code(doc: RawDoc) -> list[TextNode]:
    file_path = doc.metadata["file_path"]
    language = _lang_for(file_path)
    splitter = _get_code_splitter(language) if language else None

    nodes: list[TextNode] = []
    if splitter is not None:
        pieces = splitter.split_text(doc.text)
    else:
        pieces = [n.get_content() for n in _code_fallback.get_nodes_from_documents(
            [_as_document(doc)]
        )]

    # CodeSplitter preserves order; approximate line ranges for citations.
    cursor = 1
    for piece in pieces:
        line_count = piece.count("\n") + 1
        meta = {**doc.metadata, "source_type": "code",
                "line_start": cursor, "line_end": cursor + line_count - 1}
        nodes.append(TextNode(text=piece, metadata=meta))
        cursor += line_count
    return nodes


def chunk_text(doc: RawDoc) -> list[TextNode]:
    pieces = _text_splitter.split_text(doc.text)
    return [
        TextNode(text=piece, metadata={**doc.metadata, "source_type": doc.source_type})
        for piece in pieces
    ]


def _as_document(doc: RawDoc):
    from llama_index.core import Document

    return Document(text=doc.text, metadata=doc.metadata)


def chunk(doc: RawDoc) -> list[TextNode]:
    """Dispatch a RawDoc to the right splitter based on its source type."""
    if doc.source_type == "code":
        return chunk_code(doc)
    return chunk_text(doc)
