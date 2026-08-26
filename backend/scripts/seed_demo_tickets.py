"""Create a small, realistic FrameFlow workflow demo without calling Gemini.

This is an operator tool, not an HTTP endpoint. It uses the developer's ADC
credentials to write sample Firestore documents for one Firebase user.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from uuid import uuid4

from google.cloud import firestore


DEMO_TICKETS = (
    {
        "shot_id": "DEMO-INBOX-000",
        "director_note": "Eliminar el reflejo del equipo en la ventana del fondo.",
        "department": "vfx",
        "priority": "medium",
        "status": "pending_review",
        "ai_rationale": "La limpieza de reflejos requiere retoque y composición VFX.",
        "artist_note": None,
        "supervisor_feedback": None,
    },
    {
        "shot_id": "DEMO-VFX-001",
        "director_note": "Eliminar el boom micrófono visible sobre el actor.",
        "department": "vfx",
        "priority": "high",
        "status": "assigned",
        "ai_rationale": "La eliminación de objetos del encuadre corresponde a VFX.",
        "artist_note": None,
        "supervisor_feedback": None,
    },
    {
        "shot_id": "DEMO-SOUND-002",
        "director_note": "Reducir el zumbido constante sin afectar el diálogo.",
        "department": "sound",
        "priority": "medium",
        "status": "in_progress",
        "ai_rationale": "La nota describe limpieza y restauración de audio.",
        "artist_note": "Se aisló el tono de 60 Hz; falta revisar la transición final.",
        "supervisor_feedback": None,
    },
    {
        "shot_id": "DEMO-COLOR-003",
        "director_note": "Igualar la exposición del contraplano con la toma principal.",
        "department": "color",
        "priority": "medium",
        "status": "ready_for_qc",
        "ai_rationale": "Se requiere corrección de exposición y continuidad de color.",
        "artist_note": "Match de exposición aplicado; listo para revisión de continuidad.",
        "supervisor_feedback": None,
    },
    {
        "shot_id": "DEMO-VFX-004",
        "director_note": "Reemplazar el cielo manteniendo el movimiento de cámara.",
        "department": "vfx",
        "priority": "high",
        "status": "completed",
        "ai_rationale": "El reemplazo de cielo es una tarea de composición VFX.",
        "artist_note": "Cielo compuesto y track validado.",
        "supervisor_feedback": "QC aprobado; continuidad correcta.",
    },
    {
        "shot_id": "DEMO-EDITORIAL-005",
        "director_note": "El catering llegó tarde al set.",
        "department": "editorial",
        "priority": "low",
        "status": "rejected",
        "ai_rationale": "La nota es de logística y no requiere postproducción.",
        "artist_note": None,
        "supervisor_feedback": "No corresponde al flujo de postproducción.",
    },
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FrameFlow demo tickets in Firestore.")
    parser.add_argument("--owner-id", required=True, help="Firebase UID that should see the demo tickets.")
    parser.add_argument("--project", required=True, help="Google Cloud project ID.")
    parser.add_argument("--collection", default="postproduction_tickets", help="Firestore collection name.")
    parser.add_argument("--database", default="(default)", help="Firestore database ID.")
    args = parser.parse_args()

    client = firestore.Client(project=args.project, database=args.database)
    now = datetime.now(timezone.utc)
    batch = client.batch()

    for template in DEMO_TICKETS:
        document = client.collection(args.collection).document(str(uuid4()))
        batch.set(document, {
            **template,
            "owner_id": args.owner_id,
            "supervisor_note": None,
            "created_at": now,
            "updated_at": now,
        })

    batch.commit()
    print(f"Created {len(DEMO_TICKETS)} demo tickets for Firebase UID {args.owner_id}.")


if __name__ == "__main__":
    main()
