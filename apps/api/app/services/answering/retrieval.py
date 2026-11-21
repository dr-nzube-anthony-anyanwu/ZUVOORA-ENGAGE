"""Tenant-scoped full-text retrieval over PUBLISHED FAQs, services and approved documents.

Runs inside a widget transaction, so RLS and column grants already restrict every query to the
widget's clinic and to published content; the queries never take a tenant id from input.
The search terms are reduced to plain lowercase words before reaching to_tsquery (no operators
from user input).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import psycopg

_STOPWORDS = frozenset(
    """
a about above after again all am an and any are as at be because been before being below between
both but by can could did do does doing down during each few for from further had has have having
he her here hers him his how i if in into is it its itself just me more most my no nor not now of
off on once only or other our ours out over own same she should so some such than that the their
them then there these they this those through to too under until up very was we were what when
where which while who whom why will with would you your yours please hello hi thanks thank clinic
""".split()
)

Kind = Literal["faq", "service", "document"]


@dataclass(frozen=True)
class Passage:
    kind: Kind
    title: str
    text: str
    rank: float
    coverage: float  # share of query terms present in this passage


def query_terms(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    terms = [w for w in words if len(w) >= 3 and w not in _STOPWORDS]
    return list(dict.fromkeys(terms))[:12]


def search(conn: psycopg.Connection, question: str, limit: int = 6) -> list[Passage]:
    terms = query_terms(question)
    if not terms:
        return []
    tsquery = " | ".join(terms)  # words only: [a-z0-9]{3,}
    rows = conn.execute(
        """
        with q as (select to_tsquery('english', %(q)s) as query)
        select 'faq' as kind, published->>'question' as title, published->>'answer' as text,
               ts_rank_cd(to_tsvector('english', coalesce(published->>'question','') || ' ' ||
                                      coalesce(published->>'answer','')), q.query) as rank
          from public.faqs, q
         where to_tsvector('english', coalesce(published->>'question','') || ' ' ||
                           coalesce(published->>'answer','')) @@ q.query
        union all
        select 'service', published->>'name',
               concat_ws(' — ', published->>'name', published->>'description',
                         'price: ' || (published->>'price_note')),
               ts_rank_cd(to_tsvector('english', coalesce(published->>'name','') || ' ' ||
                                      coalesce(published->>'category','') || ' ' ||
                                      coalesce(published->>'description','')), q.query)
          from public.services, q
         where to_tsvector('english', coalesce(published->>'name','') || ' ' ||
                           coalesce(published->>'category','') || ' ' ||
                           coalesce(published->>'description','')) @@ q.query
        union all
        select 'document', d.title, c.content, ts_rank_cd(c.search, q.query)
          from public.knowledge_chunks c
          join public.knowledge_documents d on d.id = c.document_id, q
         where c.search @@ q.query
        order by rank desc
        limit %(limit)s
        """,
        {"q": tsquery, "limit": limit},
    ).fetchall()
    passages = []
    for row in rows:
        haystack = f"{row['title']} {row['text']}".lower()
        stems = [t[:5] for t in terms]
        coverage = sum(1 for s in stems if s in haystack) / len(stems)
        passages.append(
            Passage(
                row["kind"], row["title"] or "", row["text"] or "", float(row["rank"]), coverage
            )
        )
    return passages
