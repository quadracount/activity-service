"""Lógica pura de activity-service: eventos -> entradas del feed, y entradas -> respuesta al BFF."""

from datetime import UTC, datetime
from uuid import uuid4

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def format_money(amount: int) -> str:
    """45000 -> "$45.000" (pesos chilenos, sin decimales)."""
    sign = "−" if amount < 0 else ""
    return f"{sign}${abs(amount):,}".replace(",", ".")


def describe_event(event: dict) -> tuple[str, str] | None:
    """Devuelve (actor_name, texto) para un evento, o None si el tipo no se anota."""
    event_type = event.get("type")
    data = event.get("data") or {}

    if event_type == "gasto.creado":
        actor = data["paid_by_name"]
        text = f'{actor} registró "{data["description"]}" por {format_money(data["amount"])}'
        if data.get("source") == "ASSISTANT":
            text += " con el asistente"
        return actor, text
    if event_type == "pago.registrado":
        actor = data["from_name"]
        return actor, f"{actor} le pagó {format_money(data['amount'])} a {data['to_name']}"
    if event_type == "miembro.agregado":
        return data["name"], f"{data['name']} se unió al grupo"
    if event_type == "miembro.eliminado":
        return data["name"], f"{data['name']} salió del grupo"
    return None


def parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def entry_from_event(event: dict) -> dict | None:
    """Convierte un evento en el documento que se guarda en `entries`."""
    described = describe_event(event)
    if described is None:
        return None
    actor_name, text = described
    return {
        "_id": str(uuid4()),
        "event_id": event["event_id"],
        "group_id": event["group_id"],
        "type": event["type"],
        "actor_name": actor_name,
        "text": text,
        "created_at": parse_datetime(event.get("occurred_at")),
    }


def entry_to_response(doc: dict) -> dict:
    """Documento de Mongo -> entrada que espera el BFF."""
    created_at = doc["created_at"]
    if created_at.tzinfo is None:  # Mongo devuelve fechas sin zona, siempre en UTC
        created_at = created_at.replace(tzinfo=UTC)
    return {
        "id": doc["_id"],
        "groupId": doc["group_id"],
        "text": doc["text"],
        "actorName": doc["actor_name"],
        "createdAt": created_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }


def clamp_limit(value) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def build_reply(request_id, response=None, error: str | None = None) -> dict:
    """Cuerpo de respuesta que entiende ClientProxy (RMQ) de NestJS."""
    if error is not None:
        return {"id": request_id, "err": error, "isDisposed": True}
    return {"id": request_id, "response": response, "isDisposed": True}
