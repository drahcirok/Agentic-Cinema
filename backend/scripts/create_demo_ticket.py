"""Create one Firestore demo ticket without invoking Gemini.

Run from the repository root with developer ADC already configured. This is a
local operator tool, not an API endpoint, so it never bypasses web auth.
"""

from __future__ import annotations

import argparse
import os
from uuid import UUID

os.environ.setdefault("TICKET_STORAGE_BACKEND", "firestore")

from app.models.ticket import Department, Priority, TicketCreate
from app.services.ticket_repository import FirestoreTicketRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a FrameFlow demo ticket without Gemini.")
    parser.add_argument("--owner-id", required=True, help="Firebase UID of the production member.")
    parser.add_argument("--production-id", required=True, type=UUID, help="Production UUID shown in FrameFlow.")
    parser.add_argument("--shot-id", required=True)
    parser.add_argument("--note", required=True)
    parser.add_argument("--department", choices=[item.value for item in Department], default="vfx")
    parser.add_argument("--priority", choices=[item.value for item in Priority], default="medium")
    args = parser.parse_args()

    ticket = FirestoreTicketRepository().create(
        TicketCreate(
            shot_id=args.shot_id,
            director_note=args.note,
            department=Department(args.department),
            priority=Priority(args.priority),
            ai_rationale="Ticket de demostración creado manualmente; Gemini no fue invocado.",
        ),
        owner_id=args.owner_id,
        production_id=args.production_id,
    )
    print(f"Created ticket {ticket.id} in production {ticket.production_id}")


if __name__ == "__main__":
    main()
