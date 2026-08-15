"""DOI registration check against doi.org."""

from .. import cache
from ._http import SourceError, request

_REDIRECTS = {200, 301, 302, 303, 307, 308}


def validate_doi(doi: str) -> bool:
    ck = cache.cache_key(f"doi:{doi}")
    cached = cache.get("doi", ck)
    if cached is not None:
        return cached.get("valid", False)
    r = request(
        "doi",
        f"https://doi.org/{doi}",
        method="HEAD",
        allow_redirects=False,
    )
    if r.status_code in _REDIRECTS:
        valid = True
    elif r.status_code == 404:
        valid = False
    else:
        raise SourceError("doi", f"HTTP {r.status_code}")
    cache.put("doi", ck, {"valid": valid})
    return valid
