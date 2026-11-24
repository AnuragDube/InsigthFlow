from __future__ import annotations

from alembic import context

from insightflow.metadata.db import make_engine
from insightflow.metadata.models import Base

config = context.config
url = config.get_main_option("sqlalchemy.url") or ""

with make_engine(url).connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite cannot ALTER most constraints; batch mode recreates tables
    )
    with context.begin_transaction():
        context.run_migrations()
