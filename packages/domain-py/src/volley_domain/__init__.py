"""Shared domain package for Volley Intelligence.

Used by both services/api and services/worker so the two never redefine the
same models/schemas independently. See docs/architecture/adr/ADR-002 for why
this package exists outside the original apps/services/packages/ml split.
"""
