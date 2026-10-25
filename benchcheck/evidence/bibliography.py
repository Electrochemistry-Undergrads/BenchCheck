"""Optional DOI bibliography enrichment from Crossref; failures leave metadata unverified."""
import re
import time
from urllib.parse import quote
import httpx

_CACHE = {}


def lookup(doi: str, transport=None) -> dict:
    doi = doi.strip().removeprefix('https://doi.org/')
    if not re.fullmatch(r'10\.\d{4,9}/[^\s<>]{1,180}', doi):
        return {}
    if doi in _CACHE and time.monotonic()-_CACHE[doi][0]<86400:
        return dict(_CACHE[doi][1])
    try:
        with httpx.Client(timeout=5, transport=transport) as client:
            response=client.get('https://api.crossref.org/works/'+quote(doi,safe=''),headers={'User-Agent':'BenchCheck bibliography lookup'})
            response.raise_for_status()
            message=response.json().get('message') or {}
        venue=(message.get('container-title') or [None])[0]
        date=message.get('published-online') or message.get('published') or message.get('issued') or {}
        parts=date.get('date-parts') or [[]]
        year=parts[0][0] if parts[0] else None
        result={k:v for k,v in {'venue':venue,'year':year,'doi':doi,'bibliography_source':'Crossref'}.items() if v}
        _CACHE[doi]=(time.monotonic(),result)
        return result
    except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError):
        return {}
