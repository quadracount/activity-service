# activity-service

Historial de actividad. Python + MongoDB (`activity_db`) + `aio-pika`.

No expone puerto, todo pasa por RabbitMQ.

## Eventos

Escucha la cola `activity.events`, enlazada con `#` al exchange `quadracount.events`, así que recibe todos los eventos (`gasto.creado`, `pago.registrado`, `miembro.agregado`, `miembro.eliminado`). Cada uno se guarda como una frase, por ejemplo "Diego te pagó $10.000".

El `event_id` tiene índice único para no anotar dos veces el mismo evento.

| Evento | Texto |
|---|---|
| `gasto.creado` | Martín registró "Gas" por $18.000 (y "con el asistente" si `source` es `ASSISTANT`) |
| `pago.registrado` | Diego le pagó $10.000 a Martín |
| `miembro.agregado` | Tomás se unió al grupo |
| `miembro.eliminado` | Tomás salió del grupo |

El `ack` se hace después de guardar. Un mensaje que no es JSON válido o al que le faltan campos se descarta; si falla Mongo, vuelve a la cola.

## Consultas del BFF

El BFF pide los feeds con `ClientProxy.send()` de NestJS por la cola `activity.rpc`. Llega un mensaje con `reply_to` y `correlation_id` y este cuerpo:

```json
{ "pattern": "activity.get_feed", "data": { "groupId": "g-depto", "limit": 8 }, "id": "abc" }
```

La respuesta se publica en la cola `reply_to`, con el mismo `correlation_id`:

```json
{ "id": "abc", "response": [ ... ], "isDisposed": true }
```

Si falta el mismo `id`, el `correlation_id` o `isDisposed`, el BFF se queda esperando hasta el timeout sin dar error.

Detalles verificados con `@nestjs/microservices` 12.6:

- `reply_to` es `amq.rabbitmq.reply-to` (direct reply-to de RabbitMQ). La respuesta se publica en el exchange por defecto con ese `routing_key`.
- El BFF asocia la respuesta solo por `correlation_id` (el `id` del cuerpo es el mismo valor).
- La cola `activity.rpc` se declara `durable` en los dos lados. Si las opciones no coinciden, RabbitMQ rechaza la declaración.
- Si hay un error, se responde `{ "id": ..., "err": "mensaje", "isDisposed": true }`.

Para probarlo de punta a punta, ver `scripts/check-activity.cjs` en bff-gateway.

Patrones:

- `activity.get_feed` con `{ groupId, limit }`
- `activity.get_user_feed` con `{ groupIds, limit }`

Cada entrada: `{ id, groupId, text, actorName, createdAt }`. El nombre del grupo lo agrega el BFF.

## Variables de entorno

| Variable | Ejemplo |
|---|---|
| `MONGO_URL` | `mongodb://mongodb:27017` |
| `MONGO_DB` | `activity_db` |
| `RABBITMQ_URL` | `amqp://rabbitmq:5672` |

## Correr

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

`activity.py` tiene la lógica sin dependencias (texto de cada evento, formato de respuesta) y `main.py` la conexión con RabbitMQ y Mongo. Tests:

```bash
pip install pytest ruff
ruff check .
pytest
```
