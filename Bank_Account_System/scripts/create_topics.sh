#!/usr/bin/env bash
set -euo pipefail
BROKER="localhost:9092"
for topic in bank.account.opened.v1 bank.transfer.completed.v1; do
  docker exec bank-kafka /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$BROKER" --create --if-not-exists \
    --topic "$topic" --partitions 3 --replication-factor 1
done
