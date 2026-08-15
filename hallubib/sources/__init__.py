"""Grounded-search clients for the online bibliographic sources."""

from ._http import SourceError
from .arxiv import search as search_arxiv
from .crossref import search as search_crossref
from .doi import validate_doi
from .openalex import search_doi as search_openalex_doi
from .openalex import search_title as search_openalex_title
from .semanticscholar import search_match as search_semscholar
from .semanticscholar import search_relevance as search_semscholar_relevance

__all__ = [
    "SourceError",
    "search_arxiv",
    "search_crossref",
    "search_openalex_doi",
    "search_openalex_title",
    "search_semscholar",
    "search_semscholar_relevance",
    "validate_doi",
]
