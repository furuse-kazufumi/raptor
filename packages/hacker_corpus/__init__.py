"""
Hacker corpus fetcher package.

Fetches data from hacker community sources for corpus2skill ingestion:
  - Phrack magazine (phrack.org)
  - GitHub Security Advisories (GHSA)
  - CAPEC attack patterns (MITRE)
  - D3FEND defensive techniques (MITRE)
  - OSS-Security mailing list (openwall.com)
  - Google Project Zero blog

Usage:
    from packages.hacker_corpus.sources import (
        PhrackFetcher, GHSAFetcher, CAPECFetcher,
        D3FENDFetcher, OSSSecurityFetcher, ProjectZeroFetcher,
    )
"""

from packages.hacker_corpus.base import CorpusFetcher, FetchResult
from packages.hacker_corpus.sources import (
    PhrackFetcher,
    GHSAFetcher,
    CAPECFetcher,
    D3FENDFetcher,
    OSSSecurityFetcher,
    ProjectZeroFetcher,
)

#: All available fetchers, keyed by CLI name
ALL_FETCHERS: dict[str, type[CorpusFetcher]] = {
    "phrack": PhrackFetcher,
    "ghsa": GHSAFetcher,
    "capec": CAPECFetcher,
    "d3fend": D3FENDFetcher,
    "oss_security": OSSSecurityFetcher,
    "project_zero": ProjectZeroFetcher,
}

__all__ = [
    "CorpusFetcher",
    "FetchResult",
    "ALL_FETCHERS",
    "PhrackFetcher",
    "GHSAFetcher",
    "CAPECFetcher",
    "D3FENDFetcher",
    "OSSSecurityFetcher",
    "ProjectZeroFetcher",
]
