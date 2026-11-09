"""
Offline RAG retrieval over the AMM knowledge base.
Uses a local sentence-transformer model (downloaded once, runs fully offline
afterward) to embed AMM entries and the detected-defect query, then retrieves
the best match via cosine similarity. No network calls at inference time.
"""

import numpy as np
from amm_data import AMM_DATABASE

_model = None
_corpus_embeddings = None
_corpus_texts = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        # Small, fast, fully local model (~80MB) - good enough for demo retrieval
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _build_corpus():
    global _corpus_embeddings, _corpus_texts
    if _corpus_embeddings is not None:
        return
    model = _get_model()
    _corpus_texts = [
        f"{entry['defect_type']} {entry['title']} {entry['chapter']}"
        for entry in AMM_DATABASE
    ]
    _corpus_embeddings = model.encode(_corpus_texts, normalize_embeddings=True)


def retrieve_procedure(defect_type: str, top_k: int = 1):
    """
    Retrieve the most relevant AMM procedure(s) for a given detected defect type.
    Falls back to direct defect_type matching if embeddings are unavailable
    (keeps the demo resilient even without internet access for model download).
    """
    try:
        _build_corpus()
        model = _get_model()
        query = f"defect detected: {defect_type} aircraft surface inspection"
        query_emb = model.encode([query], normalize_embeddings=True)[0]
        scores = _corpus_embeddings @ query_emb
        ranked_idx = np.argsort(-scores)[:top_k]
        results = []
        for idx in ranked_idx:
            entry = dict(AMM_DATABASE[idx])
            entry["retrieval_score"] = float(scores[idx])
            results.append(entry)
        return results
    except Exception:
        # Offline-safe fallback: direct keyword match on defect_type
        matches = [e for e in AMM_DATABASE if e["defect_type"] == defect_type]
        if not matches:
            matches = [AMM_DATABASE[0]]
        for m in matches:
            m = dict(m)
            m["retrieval_score"] = 1.0
        return matches[:top_k]
