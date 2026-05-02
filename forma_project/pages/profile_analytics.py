"""Normalize public profile paths for analytics storage and aggregation."""

from __future__ import annotations

from .models import _reserved_public_profile_slugs


def normalize_profile_path(path: str) -> str:
    """Canonical path: leading slash, lowercase, trailing slash."""
    if not path:
        return ''
    p = path.strip()
    if not p.startswith('/'):
        p = '/' + p
    p = p.rstrip('/') + '/'
    return p.lower()


def is_trackable_public_profile_path(path: str) -> bool:
    """
    Accept only paths that could be public trainer profile URLs (or legacy /trainer/<id>/).
    Rejects admin, staff, static routes, etc.
    """
    p = normalize_profile_path(path)
    inner = p.strip('/')
    if not inner:
        return False
    segments = [s for s in inner.split('/') if s]
    if len(segments) == 1:
        # Legacy self-serve profile URLs were one segment (e.g. /first-last/).
        return segments[0].lower() not in _reserved_public_profile_slugs()
    if len(segments) == 2:
        a, b = segments[0].lower(), segments[1]
        if a in _reserved_public_profile_slugs():
            return False
        if b == 'profile':
            return True
        if a == 'trainer' and b.isdigit():
            return True
        if len(b) == 5 and b.isalnum():
            return True
        return False
    return False


def profile_path_for_object(profile) -> str:
    """Same normalization used when storing beacons (matches browser pathname style)."""
    return normalize_profile_path(profile.get_absolute_url())
