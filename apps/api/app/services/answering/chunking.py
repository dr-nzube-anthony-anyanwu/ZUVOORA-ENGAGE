"""Split approved document text into retrieval passages (~1,200 characters, paragraph-aware)."""

from __future__ import annotations

import re

TARGET = 1200
MAXIMUM = 3800


def chunk_text(text: str, target: int = TARGET) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        # Very long paragraphs are split on sentence boundaries, then hard-wrapped.
        pieces = [paragraph] if len(paragraph) <= target else re.split(r"(?<=[.!?])\s+", paragraph)
        for piece in pieces:
            while len(piece) > MAXIMUM:
                chunks.append(piece[:MAXIMUM])
                piece = piece[MAXIMUM:]
            if current and len(current) + len(piece) + 2 > target:
                chunks.append(current)
                current = piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks
