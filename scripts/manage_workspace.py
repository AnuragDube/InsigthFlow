"""Manage pilot workspaces with trusted, local database access."""

from __future__ import annotations

import argparse
import re

from sqlalchemy import select

from insightflow.core.context import VerifiedIdentity
from insightflow.core.errors import AppError, NotFoundError, ValidationFailed
from insightflow.core.settings import get_settings
from insightflow.metadata.bootstrap import ensure_org
from insightflow.metadata.db import make_engine, session_scope
from insightflow.metadata.memberships import set_role
from insightflow.metadata.migrate import upgrade_to_head
from insightflow.metadata.models import Organization


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("workspace")
    create.add_argument("name")
    for command in ("grant", "revoke"):
        action = commands.add_parser(command)
        action.add_argument("workspace")
        action.add_argument("issuer")
        action.add_argument("subject")
        if command == "grant":
            action.add_argument("role", choices=["owner", "editor", "viewer"])
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", args.workspace):
        parser.error("use a lowercase workspace slug up to 63 characters")

    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        upgrade_to_head(settings.database_url)
        with session_scope(engine) as session:
            if args.command == "create":
                name = args.name.strip()
                if not 1 <= len(name) <= 200:
                    raise ValidationFailed("Workspace names must contain 1 to 200 characters.")
                workspace = ensure_org(session, args.workspace, name)
                result = f"Workspace ID: {workspace.org_id}"
            else:
                org_id = session.scalar(
                    select(Organization.id).where(Organization.slug == args.workspace)
                )
                if org_id is None:
                    raise NotFoundError("Workspace not found.")
                identity = VerifiedIdentity(args.issuer, args.subject, org_id)
                set_role(session, identity, args.role if args.command == "grant" else None)
                result = "Workspace membership updated."
        print(result)
    except AppError as exc:
        parser.exit(1, f"{exc.detail}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
