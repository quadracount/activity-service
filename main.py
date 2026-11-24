"""activity-service: anota los eventos de QuadraCount y responde los feeds al BFF por RabbitMQ."""

import asyncio
import json
import logging
import os

import aio_pika
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.errors import DuplicateKeyError

from activity import build_reply, clamp_limit, entry_from_event, entry_to_response

EVENTS_EXCHANGE = "quadracount.events"
EVENTS_QUEUE = "activity.events"
RPC_QUEUE = "activity.rpc"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("activity-service")


class ActivityService:
    def __init__(self, entries):
        self.entries = entries

    async def ensure_indexes(self):
        await self.entries.create_index("event_id", unique=True)
        await self.entries.create_index([("group_id", ASCENDING), ("created_at", DESCENDING)])

    # ---- Eventos ----

    async def on_event(self, message: aio_pika.abc.AbstractIncomingMessage):
        try:
            event = json.loads(message.body)
            entry = entry_from_event(event)
        except (ValueError, KeyError, TypeError) as err:
            # Un mensaje mal formado nunca se va a poder procesar: se descarta.
            log.error("Evento inválido descartado (%s): %r", err, message.body[:200])
            await message.reject(requeue=False)
            return

        try:
            if entry is not None:
                await self.entries.insert_one(entry)
                log.info("Anotado %s %s", event["type"], event["event_id"])
        except DuplicateKeyError:
            log.info("Evento repetido ignorado: %s", event["event_id"])
        except Exception:
            log.exception("No se pudo guardar el evento, vuelve a la cola")
            await message.nack(requeue=True)
            return
        await message.ack()

    # ---- Request-reply con el BFF ----

    async def get_feed(self, data: dict) -> list[dict]:
        query = {"group_id": data["groupId"]}
        return await self._find(query, data.get("limit"))

    async def get_user_feed(self, data: dict) -> list[dict]:
        query = {"group_id": {"$in": list(data.get("groupIds") or [])}}
        return await self._find(query, data.get("limit"))

    async def _find(self, query: dict, limit) -> list[dict]:
        cursor = self.entries.find(query).sort("created_at", DESCENDING).limit(clamp_limit(limit))
        return [entry_to_response(doc) async for doc in cursor]

    async def on_rpc(self, message: aio_pika.abc.AbstractIncomingMessage, exchange):
        async with message.process():
            request_id = None
            try:
                body = json.loads(message.body)
                request_id = body.get("id")
                handler = {
                    "activity.get_feed": self.get_feed,
                    "activity.get_user_feed": self.get_user_feed,
                }.get(body.get("pattern"))
                if handler is None:
                    reply = build_reply(request_id, error=f"Patrón desconocido: {body.get('pattern')}")
                else:
                    reply = build_reply(request_id, response=await handler(body.get("data") or {}))
            except Exception as err:
                log.exception("Error respondiendo una consulta")
                reply = build_reply(request_id, error=str(err))

            if not message.reply_to:
                return
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(reply).encode(),
                    correlation_id=message.correlation_id,
                    content_type="application/json",
                ),
                routing_key=message.reply_to,
            )


async def connect_rabbitmq(url: str) -> aio_pika.abc.AbstractRobustConnection:
    # connect_robust reconecta solo, pero el primer intento falla si RabbitMQ aún no está listo
    while True:
        try:
            return await aio_pika.connect_robust(url)
        except (ConnectionError, OSError) as err:
            log.warning("RabbitMQ no disponible (%s), reintento en 3 s", err)
            await asyncio.sleep(3)


async def main():
    mongo = AsyncMongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    service = ActivityService(mongo[os.environ.get("MONGO_DB", "activity_db")]["entries"])
    await service.ensure_indexes()

    connection = await connect_rabbitmq(os.environ.get("RABBITMQ_URL", "amqp://localhost:5672"))
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    exchange = await channel.declare_exchange(
        EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    events_queue = await channel.declare_queue(EVENTS_QUEUE, durable=True)
    await events_queue.bind(exchange, routing_key="#")
    await events_queue.consume(service.on_event)

    # Debe coincidir con queueOptions del ClientProxy del BFF (durable: true)
    rpc_queue = await channel.declare_queue(RPC_QUEUE, durable=True)
    await rpc_queue.consume(lambda message: service.on_rpc(message, channel.default_exchange))

    log.info("activity-service escuchando %s y %s", EVENTS_QUEUE, RPC_QUEUE)
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
