from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from volley_api.api.routes import health, matches
from volley_api.core.config import get_settings
from volley_api.core.errors import register_exception_handlers
from volley_api.core.logging import configure_logging
from volley_api.core.middleware import RequestIdMiddleware

settings = get_settings()
configure_logging(settings.env)

app = FastAPI(
    title="Volley Intelligence API",
    version="0.1.0",
    description="Org-scoped API for match management and pipeline processing.",
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(matches.router)
