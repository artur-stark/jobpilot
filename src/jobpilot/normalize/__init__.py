from jobpilot.normalize.dedupe import InsertResult, insert_vacancy
from jobpilot.normalize.extract import canonical_url, normalize_key, parse_salary, strip_html
from jobpilot.normalize.fingerprint import make_fingerprint, match_key

__all__ = [
    "InsertResult",
    "insert_vacancy",
    "canonical_url",
    "normalize_key",
    "parse_salary",
    "strip_html",
    "make_fingerprint",
    "match_key",
]
