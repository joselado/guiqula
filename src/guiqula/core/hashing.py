"""Content hashes of JSON data (canonical: sorted keys, no whitespace)."""
import hashlib
import json


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(data):
    return hashlib.sha256(canonical(data).encode()).hexdigest()[:24]
