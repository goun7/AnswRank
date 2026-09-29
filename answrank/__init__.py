"""AnswRank: Answer Engine Optimization (AEO) and Generative Engine Optimization (GEO) Audit Engine.

Evaluates and optimizes web domains for citation and visibility across
ChatGPT, Perplexity, Gemini, Claude, and AI Answer Engines.
"""

__version__ = "1.0.0"
__author__ = "AnswRank Core Team"

from answrank.models import AuditResult, CategoryScores
from answrank.audit.engine import AuditEngine

__all__ = ["AuditResult", "CategoryScores", "AuditEngine", "__version__"]
