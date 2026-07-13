"""
RAG modulu: FAISS (dense, BAAI/bge-m3) + BM25 (sparse) hibrid axtarış.

Bilik bazası knowledge/faq_augmented.json-dur — hər FAQ girişinin
"variations" sahəsindəki alternativ ifadələr də expand edilərək ayrı
index entry-lərinə çevrilir (eyni cavabla). Bu sayədə 190 FAQ → ~2090
indekslənmiş sual — istifadəçi eyni sualı fərqli sözdə versə belə
doğru cavab tapılır. Threshold-lar üçün bax config.py-dakı rag_*
parametrləri.
"""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from utils.logger import get_logger
from config import cfg

logger = get_logger("RAG")

# faq.json-da bəzi suallar bölmə başlığı və nömrələmə ilə birlikdə yazılıb
# (məs. "Layihə barədə ümumi suallar:\n\n1. "4Sİ Akademiyası" nədir?") —
# bunlar embedding keyfiyyətini korlayır, təmizlənir.
_SECTION_HEADER_RE = re.compile(r"^[^\n?]*:\s*$")
_LEADING_NUMBER_RE = re.compile(r"^\d+\.\s*")


def _clean_question(raw: str) -> str:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    lines = [ln for ln in lines if not _SECTION_HEADER_RE.match(ln)]
    text = " ".join(lines).strip()
    text = _LEADING_NUMBER_RE.sub("", text)
    return text or raw.strip()


def _tokenize(text: str) -> List[str]:
    """BM25 üçün Azərbaycan hərflərini saxlayan sadə tokenizer."""
    text = text.lower()
    text = re.sub(r"[^\w\səıöüşçğ]", " ", text)
    return text.split()


@dataclass(frozen=True)
class Candidate:
    question: str
    answer: str
    score: float


class KnowledgeBase:
    """FAQ üzərində hibrid (dense + BM25) axtarış aparır."""

    def __init__(self, faq_path: Optional[Path] = None):
        self.faq_path = Path(faq_path) if faq_path else cfg.faq_path
        self.index_dir = cfg.vector_store_dir
        self.index_file = self.index_dir / "faiss.index"
        self.metadata_file = self.index_dir / "metadata.json"
        self.manifest_file = self.index_dir / "manifest.json"

        self.metadata: List[dict] = []
        self.index = None
        self._bm25 = None
        self._embedder = None
        self.count = 0

        self._load()

    # --- yükləmə / indeks qurma ---------------------------------------------

    def _load_faq_entries(self) -> List[dict]:
        with open(self.faq_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = []
        for item in data:
            # Admin paneldən passiv edilmiş girişlər indekslənmir
            if item.get("active") is False:
                continue
            q = (item.get("question") or "").strip()
            a = (item.get("answer") or "").strip()
            if not q or not a:
                continue
            # Ana sualı index-ə əlavə et
            entries.append({"question": _clean_question(q), "answer": a})
            # "variations" sahəsindəki alternativ ifadələri də expand et.
            # Hər variation eyni cavabla ayrı entry olur — istifadəçi sualı
            # fərqli sözdə versə belə FAISS/BM25 doğru cavabı tapır.
            for variation in item.get("variations", []):
                v = (variation or "").strip()
                if v:
                    entries.append({"question": _clean_question(v), "answer": a})
        return entries

    def _content_hash(self, entries: List[dict]) -> str:
        payload = cfg.embedding_model + "|" + "|".join(
            e["question"] + "\x00" + e["answer"] for e in entries
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _atomic_write(self, path: Path, write_fn) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        os.close(fd)
        try:
            write_fn(tmp)
            os.replace(tmp, str(path))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _load(self) -> None:
        if not self.faq_path.exists():
            logger.warning(f"FAQ faylı tapılmadı: {self.faq_path}")
            return

        import faiss
        from sentence_transformers import SentenceTransformer

        entries = self._load_faq_entries()
        if not entries:
            logger.warning("FAQ faylı boşdur.")
            return

        faq_hash = self._content_hash(entries)
        needs_build = True
        if self.manifest_file.exists() and self.index_file.exists() and self.metadata_file.exists():
            try:
                manifest = json.loads(self.manifest_file.read_text(encoding="utf-8"))
                needs_build = manifest.get("hash") != faq_hash
            except (json.JSONDecodeError, OSError):
                needs_build = True

        logger.info(f"Embedding modeli yüklənir: {cfg.embedding_model} (ilk dəfədirsə endirilə bilər)")
        # CPU-da yüklənir: kiçik modeldir (94 FAQ, sorğu başına 1 encode),
        # GPU-nun CUDA versiyası ilə uyğunsuzluq riski olmadan işləyir —
        # STT (Whisper) üçün ayrılmış CUDA mühitinə toxunmur.
        self._embedder = SentenceTransformer(cfg.embedding_model, device="cpu")

        if needs_build:
            logger.info(f"{len(entries)} FAQ girişi üçün indeks qurulur (variations daxil)...")
            questions = [e["question"] for e in entries]
            embeddings = self._embedder.encode(
                questions, normalize_embeddings=True, show_progress_bar=True
            )
            embeddings = np.asarray(embeddings, dtype=np.float32)

            index = faiss.IndexFlatIP(embeddings.shape[1])
            index.add(embeddings)

            self._atomic_write(self.index_file, lambda p: faiss.write_index(index, p))
            self._atomic_write(
                self.metadata_file,
                lambda p: Path(p).write_text(
                    json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8"
                ),
            )
            self._atomic_write(
                self.manifest_file,
                lambda p: Path(p).write_text(
                    json.dumps({"hash": faq_hash, "count": len(entries)}, ensure_ascii=False),
                    encoding="utf-8",
                ),
            )
            self.index = index
            self.metadata = entries
            logger.info("Indeks hazırdır.")
        else:
            logger.info("Mövcud indeks yüklənir (FAQ dəyişməyib)...")
            self.index = faiss.read_index(str(self.index_file))
            self.metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))

        self.count = len(self.metadata)

        try:
            from rank_bm25 import BM25Okapi

            corpus = [_tokenize(m["question"]) for m in self.metadata]
            self._bm25 = BM25Okapi(corpus)
        except ImportError:
            logger.warning("rank-bm25 quraşdırılmayıb — yalnız dense axtarış işləyəcək.")

        logger.info(f"Bilik bazası hazırdır: {self.count} FAQ girişi.")

    # --- axtarış -------------------------------------------------------------

    def retrieve(self, query: str) -> List[Candidate]:
        query = (query or "").strip()
        if not query or self.index is None or self.index.ntotal == 0:
            return []

        embedding = self._embedder.encode([query], normalize_embeddings=True)
        embedding = np.asarray(embedding, dtype=np.float32)

        k = min(cfg.rag_top_k, self.index.ntotal)
        dense_scores, ids = self.index.search(embedding, k)
        dense_scores, ids = dense_scores[0], ids[0]

        if self._bm25 is not None and cfg.rag_hybrid_alpha < 1.0:
            bm25_all = np.array(self._bm25.get_scores(_tokenize(query)))
            if bm25_all.max() > 0:
                bm25_all = bm25_all / bm25_all.max()
            scored = [
                (int(i), cfg.rag_hybrid_alpha * float(d) + (1 - cfg.rag_hybrid_alpha) * float(bm25_all[i]))
                for d, i in zip(dense_scores, ids)
                if i >= 0
            ]
        else:
            scored = [(int(i), float(d)) for d, i in zip(dense_scores, ids) if i >= 0]

        scored.sort(key=lambda x: x[1], reverse=True)

        candidates = [
            Candidate(
                question=self.metadata[i]["question"],
                answer=self.metadata[i]["answer"],
                score=score,
            )
            for i, score in scored
        ]

        if not candidates or candidates[0].score < cfg.rag_min_similarity:
            if candidates:
                logger.info(
                    f"Ən yaxşı score {candidates[0].score:.3f} < {cfg.rag_min_similarity} "
                    f"threshold: '{query[:80]}'"
                )
            return []

        top = candidates[0].score
        return [c for c in candidates if c.score >= top - cfg.rag_candidate_margin]
