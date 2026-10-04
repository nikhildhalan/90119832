import json
import logging
import signal
from confluent_kafka import Consumer, KafkaError
from .config import settings
from .db import open_pool, close_pool, pool

log = logging.getLogger('notification-service')
TOPICS = ['bank.account.opened.v1', 'bank.transfer.completed.v1']
running = True

def stop(*_):
    global running
    running = False

def notification_rows(event: dict):
    data = event['data']
    event_type = event['eventType']
    if event_type == 'AccountOpened':
        return [(data['accountNumber'], f"Your {data['accountType']} account {data['accountNumber']} is open. Initial deposit INR {data['initialDeposit']}.")]
    if event_type == 'TransferCompleted':
        amount = data['amount']
        return [(data['fromAccountNumber'], f"INR {amount} transferred to {data['toAccountNumber']} (ref {data['referenceNo']})."),
                (data['toAccountNumber'], f"INR {amount} received from {data['fromAccountNumber']} (ref {data['referenceNo']}).")]
    return []

def main():
    logging.basicConfig(level=logging.INFO)
    open_pool()
    consumer = Consumer({'bootstrap.servers': settings.kafka_bootstrap_servers, 'group.id': 'notification-service', 'auto.offset.reset': 'earliest', 'enable.auto.commit': False})
    consumer.subscribe(TOPICS)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error('Kafka consumer error: %s', msg.error())
                continue
            try:
                event = json.loads(msg.value().decode('utf-8'))
                rows = notification_rows(event)
                with pool.connection() as conn:
                    with conn.transaction():
                        for account_number, message in rows:
                            conn.execute('''INSERT INTO notification_log(event_id,account_number,event_type,message)
                              VALUES(%s,%s,%s,%s) ON CONFLICT(event_id,account_number) DO NOTHING''',
                              (event['eventId'], account_number, event['eventType'], message[:300]))
                consumer.commit(message=msg, asynchronous=False)
            except Exception:
                log.exception('Event handling failed; offset will be retried')
    finally:
        consumer.close()
        close_pool()

if __name__ == '__main__':
    main()
