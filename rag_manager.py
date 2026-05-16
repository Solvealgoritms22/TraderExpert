from __future__ import annotations

import shutil
from pathlib import Path

from app_paths import data_path, resource_path


class RAGManager:
    def __init__(self):
        self.user_dir = data_path("rag")
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self._seed_default_documents()

    def _seed_default_documents(self):
        source_dir = resource_path("rag")
        if not source_dir.exists():
            return
        for source in source_dir.glob("*.md"):
            target = self.user_dir / source.name
            if not target.exists():
                shutil.copy2(source, target)

    def load_context(self, query_terms: list[str] | None = None, max_chars: int = 12000, custom_dir: str | None = None) -> str:
        search_dir = Path(custom_dir) if custom_dir else self.user_dir
        if not search_dir.exists():
            search_dir = self.user_dir

        query_terms = [term.lower() for term in (query_terms or []) if term]
        chunks = []
        for path in sorted(search_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if query_terms and not any(term in text.lower() for term in query_terms):
                continue
            chunks.append(f"# {path.name}\n{text.strip()}")
            if sum(len(chunk) for chunk in chunks) >= max_chars:
                break
        return "\n\n".join(chunks)[:max_chars]
