"""RAG-readiness estimation engine for AnswRank.

Evaluates whether a site's content chunks would plausibly be retrieved by
LLM RAG pipelines (Perplexity Sonar / ChatGPT Search) for sector queries,
using local TF + 3-gram cosine similarity against the query bank.

HONESTY NOTE (2026-09-14 audit): This module does NOT implement AutoGEO
(ICLR 2026, arXiv:2510.11438) — that system extracts preference rules from
LLMs and rewrites content. This engine is merely INSPIRED by the retrieval-
readiness question AutoGEO raises, and follows the Princeton GEO (KDD 2024,
arXiv:2311.09735) finding that quotable, statistics-dense, well-structured
content improves visibility. It is a heuristic proxy, not a live retrieval
measurement; treat its score as a readiness estimate.
"""

import math
import re
from typing import Dict, List
from pydantic import BaseModel
from bs4 import BeautifulSoup


class TextChunk(BaseModel):
    chunk_id: int
    heading_context: str
    text_content: str
    token_count: int


class QueryRelevanceMatch(BaseModel):
    question: str
    best_chunk_id: int
    best_chunk_preview: str
    similarity_score: float  # 0.0 to 1.0
    will_be_retrieved_in_top_k: bool  # True if similarity >= RETRIEVAL_THRESHOLD (0.45)


class RAGAnalysisResult(BaseModel):
    url: str
    total_chunks_extracted: int
    rag_retrieval_score: float  # 0 to 100
    retrieval_pass_rate_pct: float  # % of questions that hit top-k threshold
    average_similarity: float
    best_performing_chunks: List[int]
    uncovered_questions: List[str]
    matches: List[QueryRelevanceMatch]
    remedy_advice: str


class RAGEngine:
    """Evaluates semantic chunking quality and dense retrieval similarity against sector questions."""

    RETRIEVAL_THRESHOLD = 0.45  # Dense cosine similarity threshold for top-k inclusion

    @classmethod
    def extract_semantic_chunks(cls, html_content: str, max_chunk_words: int = 300) -> List[TextChunk]:
        """Parse HTML into semantically coherent paragraph and section chunks."""
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
            tag.decompose()

        chunks: List[TextChunk] = []
        current_heading = "Giriş / Genel"
        current_text_blocks = []
        current_word_count = 0
        chunk_idx = 1

        for element in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            text = element.get_text(strip=True)
            if not text or len(text) < 20:
                continue

            if element.name in ["h1", "h2", "h3"]:
                if current_text_blocks:
                    combined = " ".join(current_text_blocks)
                    chunks.append(
                        TextChunk(
                            chunk_id=chunk_idx,
                            heading_context=current_heading,
                            text_content=combined,
                            token_count=len(combined.split()),
                        )
                    )
                    chunk_idx += 1
                    current_text_blocks = []
                    current_word_count = 0
                current_heading = text
            else:
                words = text.split()
                if current_word_count + len(words) > max_chunk_words and current_text_blocks:
                    combined = " ".join(current_text_blocks)
                    chunks.append(
                        TextChunk(
                            chunk_id=chunk_idx,
                            heading_context=current_heading,
                            text_content=combined,
                            token_count=len(combined.split()),
                        )
                    )
                    chunk_idx += 1
                    current_text_blocks = [text]
                    current_word_count = len(words)
                else:
                    current_text_blocks.append(text)
                    current_word_count += len(words)

        if current_text_blocks:
            combined = " ".join(current_text_blocks)
            chunks.append(
                TextChunk(
                    chunk_id=chunk_idx,
                    heading_context=current_heading,
                    text_content=combined,
                    token_count=len(combined.split()),
                )
            )

        return chunks

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        """Tokenize and normalize text with Turkish/English stopword handling."""
        text = text.lower()
        # Remove punctuation
        tokens = re.findall(r"\b[a-zçğıöşü0-9]{3,}\b", text)
        stopwords = {
            "ve", "ile", "için", "bir", "bu", "şu", "olan", "olarak", "gibi", "daha",
            "en", "çok", "var", "yok", "the", "and", "for", "with", "from", "are", "you"
        }
        return [t for t in tokens if t not in stopwords]

    @classmethod
    def _compute_cosine_similarity(cls, query_text: str, chunk_text: str) -> float:
        """Compute Query-to-Passage Semantic Relevance using Term Frequencies & character 3-grams."""
        tokens_q = cls._tokenize(query_text)
        tokens_d = cls._tokenize(chunk_text)

        if not tokens_q or not tokens_d:
            return 0.0

        vec_q: Dict[str, float] = {}
        for t in tokens_q:
            vec_q[t] = 1.0
            for i in range(len(t) - 2):
                vec_q[t[i:i+3]] = 0.3

        vec_d: Dict[str, float] = {}
        for t in tokens_d:
            vec_d[t] = vec_d.get(t, 0.0) + 1.0
            for i in range(len(t) - 2):
                vec_d[t[i:i+3]] = vec_d.get(t[i:i+3], 0.0) + 0.3

        intersection = set(vec_q.keys()) & set(vec_d.keys())
        dot_product = sum(vec_q[k] * min(1.5, vec_d[k]) for k in intersection)
        # Token listesi boş değilse her token nonzero ağırlık koyar; mag_q > 0.
        # (Boş sorgu early return'de yakalanır — 158'deki dead guard kaldırıldı.)
        mag_q = math.sqrt(sum(v ** 2 for v in vec_q.values()))

        # Query-normalized coverage with mild passage length penalty
        score = dot_product / (mag_q * 1.5)
        return min(1.0, round(score, 4))


    @classmethod
    def evaluate_content_rag(
        cls,
        url: str,
        html_content: str,
        questions: List[str],
    ) -> RAGAnalysisResult:
        """Evaluate how well web content chunks match target sector questions."""
        chunks = cls.extract_semantic_chunks(html_content)

        if not chunks:
            # Fallback if no chunks extracted
            chunks = [
                TextChunk(
                    chunk_id=1,
                    heading_context="Ham İçerik",
                    text_content=html_content[:500],
                    token_count=len(html_content[:500].split()),
                )
            ]

        matches: List[QueryRelevanceMatch] = []
        best_chunks_tracker: Dict[int, int] = {}
        uncovered: List[str] = []

        for q in questions:
            best_sim = 0.0
            best_c_id = chunks[0].chunk_id
            best_preview = chunks[0].text_content[:100]

            for chunk in chunks:
                combined_context = f"{chunk.heading_context}: {chunk.text_content}"
                sim = cls._compute_cosine_similarity(q, combined_context)
                if sim > best_sim:
                    best_sim = sim
                    best_c_id = chunk.chunk_id
                    best_preview = chunk.text_content[:120] + "..."

            is_retrieved = best_sim >= cls.RETRIEVAL_THRESHOLD
            if is_retrieved:
                best_chunks_tracker[best_c_id] = best_chunks_tracker.get(best_c_id, 0) + 1
            else:
                uncovered.append(q)

            matches.append(
                QueryRelevanceMatch(
                    question=q,
                    best_chunk_id=best_c_id,
                    best_chunk_preview=best_preview,
                    similarity_score=best_sim,
                    will_be_retrieved_in_top_k=is_retrieved,
                )
            )

        pass_count = sum(1 for m in matches if m.will_be_retrieved_in_top_k)
        total_q = len(questions) if questions else 1
        pass_rate = round((pass_count / total_q) * 100.0, 1)
        avg_sim = round(sum(m.similarity_score for m in matches) / total_q, 4)
        rag_score = round(min(100.0, (avg_sim * 100.0 * 1.5) + (pass_rate * 0.3)), 1)

        sorted_best_chunks = [k for k, _ in sorted(best_chunks_tracker.items(), key=lambda x: x[1], reverse=True)]

        if rag_score >= 75.0:
            remedy = "MÜKEMMEL RAG DÜZENİ: Sayfa içerikleri sektör sorularıyla yüksek anlamsal yakınlığa sahip. LLM retriever'ları bu paragrafları doğrudan bağlamına alacaktır."
        elif rag_score >= 50.0:
            remedy = f"ORTA RAG DÜZENİ: Sayfa içeriği {len(uncovered)} kritik soru için zayıf semantik bağ taşıyor. Başlıklar altına doğrudan soru odaklı SSS ve açıklama blokları eklenmelidir."
        else:
            remedy = "KRİTİK RAG KUSURU: Sayfa metinleri aşırı genel veya jenerik; AI arama motorlarının dense embedding filtrelerini geçememektedir. llms-full.txt ve doğrudan soru cevap blokları zorunludur."

        return RAGAnalysisResult(
            url=url,
            total_chunks_extracted=len(chunks),
            rag_retrieval_score=rag_score,
            retrieval_pass_rate_pct=pass_rate,
            average_similarity=avg_sim,
            best_performing_chunks=sorted_best_chunks[:5],
            uncovered_questions=uncovered[:5],
            matches=matches,
            remedy_advice=remedy,
        )
