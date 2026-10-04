import json
import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo
from confluent_kafka import Producer
from .config import settings

log = logging.getLogger(__name__)
producer = None

def get_producer():
    global producer
    if producer is None:
        producer = Producer({'bootstrap.servers': settings.kafka_bootstrap_servers, 'enable.idempotence': True, 'acks': 'all', 'message.timeout.ms': int(settings.kafka_timeout_seconds * 1000)})
    return producer
IST = ZoneInfo('Asia/Kolkata')

def event_envelope(event_type: str, correlation_id: str, data: dict) -> dict:
    def normalize(value):
        if isinstance(value, Decimal):
            return format(value, '.2f')
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        raise TypeError(type(value).__name__)
    return {'eventId': str(uuid4()), 'eventType': event_type, 'eventVersion': 1, 'occurredAt': datetime.now(IST).isoformat(), 'source': 'bank-account-service', 'correlationId': correlation_id, 'data': json.loads(json.dumps(data, default=normalize))}

def publish(topic: str, key: str, event: dict) -> bool:
    delivered = []
    def on_delivery(err, _message):
        if err is not None:
            delivered.append(err)
    try:
        client = get_producer()
        client.produce(topic, key=key, value=json.dumps(event, separators=(',', ':')), on_delivery=on_delivery)
        remaining = client.flush(settings.kafka_timeout_seconds)
        if remaining or delivered:
            log.error('Kafka publish failed topic=%s key=%s event=%s error=%s pending=%s', topic, key, event, delivered, remaining)
            return False
        return True
    except Exception:
        log.exception('Kafka publish failed topic=%s key=%s event=%s', topic, key, event)
        return False

def flush() -> None:
    if producer is not None:
        producer.flush(5)
