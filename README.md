# activity-service

Historial de actividad. Python + MongoDB (`activity_db`) + `aio-pika`.

No expone puerto, todo pasa por RabbitMQ.

## Eventos

Escucha la cola `activity.events`, enlazada con `#` al exchange `quadracount.events`, así que recibe todos los eventos (`gasto.creado`, `pago.registrado`, `miembro.agregado`, `miembro.eliminado`). Cada uno se guarda como una frase, por ejemplo "Diego te pagó $10.000".

El `event_id` tiene índice único para no anotar dos veces el mismo evento.

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
