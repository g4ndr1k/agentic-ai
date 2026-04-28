"""Generic fingerprint derivation — domain-agnostic.

Domains register derivers; the engine never normalizes "by convention."
Each domain provides its own normalize() + derive() pair.

Fingerprint shape (plan §"Fingerprint shape"):
  identity_hash      — stable forever for a given source-row identity (keyed in mappings)
  identity_raw       — canonical pre-hash form (audit / collision check)
  matching_features  — tokens, normalized text, etc. for live scoring (never stored on mappings)
  fingerprint_version — which version produced identity_hash / matching_features

The identity_hash stability contract: stable under the same fingerprint_version.
When fingerprint_version bumps the engine re-derives identity_raw from the live source
row and compares — silent reuse across versions is forbidden.
"""
from __future__ import annotations

import hashlib
from typing import Any, NamedTuple


class Fingerprint(NamedTuple):
    identity_hash: str          # authoritative key (stored on mappings)
    identity_raw: str           # canonical pre-hash form
    matching_features: dict     # live-scoring features; never stored
    fingerprint_version: int    # which version produced this fingerprint


def sha256_hex(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def norm(text: str) -> str:
    """Default text canonicalizer shared by multiple domains."""
    return (text or "").strip().lower().replace(" ", "-")
