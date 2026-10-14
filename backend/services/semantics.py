"""
Local semantic memory search (Phase 5): Okapi BM25, pure Python, no deps.
Indexes MemoryEntry rows (objective + outcome + errors) for ranked retrieval.
FREE MODE: fully local, no embeddings API.
"""
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from database.models import MemoryEntry
from database.session import SessionLocal

_TOKEN_RE = re.compile(r"[a-z0-9áéíóúüñ]{2,}", re.IGNORECASE)

# English + Spanish stopwords kept small on purpose (domain terms matter)
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "el", "la", "los", "las", "del", "que", "por", "con", "una", "uno", "para",
    "como", "pero", "sus", "ya", "o", "y", "de", "en", "un", "se", "su", "al",
}


def tokenize(text: str) -> List[str]:
    return [
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if t.lower() not in _STOPWORDS
    ]


class BM25Index:
    """Okapi BM25 over in-memory documents; rebuildable from DB."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: List[Dict[str, Any]] = []
        self._doc_len: List[int] = []
        self._tf: List[Counter] = []
        self._df: Dict[str, int] = defaultdict(int)
        self._avgdl: float = 0.0
        self._built_at: Optional[datetime] = None

    @property
    def size(self) -> int:
        return len(self._docs)

    def build(self, docs: List[Dict[str, Any]]) -> None:
        """docs: [{id, text, meta...}] — text is what gets tokenized."""
        self._docs = docs
        self._tf = []
        self._doc_len = []
        self._df = defaultdict(int)
        for doc in docs:
            tokens = tokenize(doc.get("text", ""))
            tf = Counter(tokens)
            self._tf.append(tf)
            self._doc_len.append(len(tokens))
            for term in tf:
                self._df[term] += 1
        n = max(len(docs), 1)
        self._avgdl = (sum(self._doc_len) / n) if n else 0.0
        self._built_at = datetime.utcnow()

    def _idf(self, term: str) -> float:
        n = len(self._docs)
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        # Okapi idf with +1 floor to avoid negatives on very common terms
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._docs:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scored: List[tuple] = []
        for i, tf in enumerate(self._tf):
            score = 0.0
            dl = self._doc_len[i] or 1
            for term in q_tokens:
                f = tf.get(term, 0)
                if f == 0:
                    continue
                idf = self._idf(term)
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1))
                score += idf * f * (self.k1 + 1) / denom
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda t: t[0], reverse=True)
        out = []
        for score, i in scored[:top_k]:
            doc = dict(self._docs[i])
            doc["score"] = round(score, 4)
            out.append(doc)
        return out


# Module-level index (rebuilt on demand with a staleness window)
_index = BM25Index()
_index_dirty = True
_REBUILD_SECONDS = 30


def _doc_text(row: MemoryEntry) -> str:
    parts = [row.objective or "", row.outcome or "", " ".join(row.errors or [])]
    return " ".join(p for p in parts if p)


def rebuild_index(force: bool = False) -> int:
    global _index, _index_dirty
    if (
        not force
        and not _index_dirty
        and _index._built_at
        and (datetime.utcnow() - _index._built_at).total_seconds() < _REBUILD_SECONDS
    ):
        return _index.size

    docs: List[Dict[str, Any]] = []
    try:
        db = SessionLocal()
        try:
            rows = db.execute(
                select(MemoryEntry).order_by(MemoryEntry.id.desc()).limit(2000)
            ).scalars().all()
            for row in rows:
                text = _doc_text(row)
                if not text.strip():
                    continue
                docs.append(
                    {
                        "id": row.id,
                        "task_id": row.task_id,
                        "objective": (row.objective or "")[:300],
                        "outcome": (row.outcome or "")[:300],
                        "evaluation": row.evaluation,
                        "text": text,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                )
        finally:
            db.close()
    except Exception:
        docs = []

    _index.build(docs)
    _index_dirty = False
    return _index.size


def invalidate_index() -> None:
    global _index_dirty
    _index_dirty = True


def search_memory(query: str, top_k: int = 5) -> Dict[str, Any]:
    """Semantic search over experience memory. Rebuilds index if stale."""
    rebuild_index()
    hits = _index.search(query, top_k=top_k)
    return {
        "query": query,
        "count": len(hits),
        "indexed": _index.size,
        "results": hits,
    }
