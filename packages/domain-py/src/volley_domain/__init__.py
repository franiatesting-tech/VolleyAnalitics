"""Shared domain package for Volley Intelligence.

Used by both services/api and services/worker so the two never redefine the
same models/schemas independently. See docs/architecture/adr/ADR-002 for why
this package exists outside the original apps/services/packages/ml split.

Importing this package eagerly imports both `models` (Phase 1: Match,
ProcessingJob) and `ontology` (Phase 2: the full volleyball ontology, see
docs/domain/ONTOLOGY.md) so every table is registered on the shared `Base`
before anything inspects `Base.metadata` (Alembic autogenerate, `create_all`
in tests) -- forgetting to import one of these modules is a real, silent way
for tables to go missing from a migration.
"""

from volley_domain import models as models  # noqa: F401
from volley_domain import ontology as ontology  # noqa: F401
from volley_domain.base import Base as Base
