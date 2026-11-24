from datetime import UTC, datetime

from activity import build_reply, clamp_limit, entry_from_event, entry_to_response, format_money


def event(event_type, data):
    return {
        "event_id": "ev-1",
        "type": event_type,
        "occurred_at": "2026-11-06T18:20:00Z",
        "group_id": "g-depto",
        "data": data,
    }


def test_format_money():
    assert format_money(45000) == "$45.000"
    assert format_money(500) == "$500"
    assert format_money(-8000) == "−$8.000"


def test_gasto_creado_con_asistente():
    entry = entry_from_event(
        event(
            "gasto.creado",
            {
                "expense_id": "e-1",
                "description": "Mercadería y útiles de aseo",
                "amount": 45000,
                "paid_by": "u-martin",
                "paid_by_name": "Martín",
                "shares": [],
                "source": "ASSISTANT",
            },
        )
    )
    assert entry["actor_name"] == "Martín"
    assert entry["text"] == 'Martín registró "Mercadería y útiles de aseo" por $45.000 con el asistente'
    assert entry["created_at"] == datetime(2026, 11, 6, 18, 20, tzinfo=UTC)


def test_pago_registrado():
    entry = entry_from_event(
        event(
            "pago.registrado",
            {
                "payment_id": "p-1",
                "from_user_id": "u-diego",
                "from_name": "Diego",
                "to_user_id": "u-martin",
                "to_name": "Martín",
                "amount": 10000,
            },
        )
    )
    assert entry["text"] == "Diego le pagó $10.000 a Martín"


def test_miembros():
    assert entry_from_event(event("miembro.agregado", {"user_id": "u-x", "name": "Tomás"}))["text"] == (
        "Tomás se unió al grupo"
    )
    assert entry_from_event(event("miembro.eliminado", {"user_id": "u-x", "name": "Tomás"}))["text"] == (
        "Tomás salió del grupo"
    )


def test_evento_desconocido_no_se_anota():
    assert entry_from_event(event("otro.evento", {})) is None


def test_entry_to_response_con_fecha_de_mongo_sin_zona():
    doc = {
        "_id": "a-1",
        "group_id": "g-depto",
        "text": "x",
        "actor_name": "Diego",
        "created_at": datetime(2026, 11, 6, 18, 20),
    }
    assert entry_to_response(doc) == {
        "id": "a-1",
        "groupId": "g-depto",
        "text": "x",
        "actorName": "Diego",
        "createdAt": "2026-11-06T18:20:00.000Z",
    }


def test_clamp_limit():
    assert clamp_limit(None) == 20
    assert clamp_limit(5) == 5
    assert clamp_limit(1000) == 100
    assert clamp_limit(0) == 1


def test_build_reply_formato_nest():
    assert build_reply("abc", response=[]) == {"id": "abc", "response": [], "isDisposed": True}
    assert build_reply("abc", error="falló") == {"id": "abc", "err": "falló", "isDisposed": True}
