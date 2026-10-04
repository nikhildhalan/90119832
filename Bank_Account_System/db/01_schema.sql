CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bank_app') THEN
    CREATE ROLE bank_app LOGIN PASSWORD 'bank_app_pwd';
  END IF;
END $$;

CREATE SEQUENCE IF NOT EXISTS account_number_seq START 1;
CREATE SEQUENCE IF NOT EXISTS transfer_reference_seq START 1;

CREATE TABLE IF NOT EXISTS customer (
  customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  full_name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  phone VARCHAR(10) NOT NULL UNIQUE,
  date_of_birth DATE NOT NULL,
  pan CHAR(10) NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_customer_pan CHECK (pan ~ '^[A-Z]{5}[0-9]{4}[A-Z]$'),
  CONSTRAINT ck_customer_phone CHECK (phone ~ '^[6-9][0-9]{9}$'),
  CONSTRAINT ck_customer_email_lower CHECK (email = lower(email))
);

CREATE TABLE IF NOT EXISTS account (
  account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  account_number VARCHAR(12) NOT NULL UNIQUE DEFAULT ('5010' || lpad(nextval('account_number_seq')::text, 8, '0')),
  customer_id BIGINT NOT NULL REFERENCES customer(customer_id),
  account_type VARCHAR(10) NOT NULL CHECK (account_type IN ('SAVINGS','CURRENT')),
  currency CHAR(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  balance NUMERIC(15,2) NOT NULL DEFAULT 0 CHECK (balance >= 0),
  status VARCHAR(10) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','FROZEN','CLOSED')),
  version INTEGER NOT NULL DEFAULT 0,
  opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_account_customer_type UNIQUE (customer_id, account_type)
);

CREATE TABLE IF NOT EXISTS fund_transfer (
  transfer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reference_no VARCHAR(20) NOT NULL UNIQUE DEFAULT ('TRF' || to_char(now() AT TIME ZONE 'Asia/Kolkata','YYYYMMDD') || lpad(nextval('transfer_reference_seq')::text, 6, '0')),
  idempotency_key VARCHAR(64) NOT NULL UNIQUE,
  request_fingerprint CHAR(64),
  from_account_id BIGINT NOT NULL REFERENCES account(account_id),
  to_account_id BIGINT NOT NULL REFERENCES account(account_id),
  amount NUMERIC(15,2) NOT NULL CHECK (amount BETWEEN 1 AND 200000),
  remarks VARCHAR(100),
  status VARCHAR(10) NOT NULL DEFAULT 'COMPLETED' CHECK (status IN ('COMPLETED','FAILED')),
  failure_reason VARCHAR(40),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_transfer_accounts CHECK (from_account_id <> to_account_id),
  CONSTRAINT ck_transfer_failure_reason CHECK ((status = 'FAILED' AND failure_reason IS NOT NULL) OR (status = 'COMPLETED' AND failure_reason IS NULL))
);

CREATE TABLE IF NOT EXISTS account_transaction (
  txn_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  account_id BIGINT NOT NULL REFERENCES account(account_id),
  transfer_id UUID REFERENCES fund_transfer(transfer_id),
  txn_type VARCHAR(6) NOT NULL CHECK (txn_type IN ('CREDIT','DEBIT')),
  amount NUMERIC(15,2) NOT NULL CHECK (amount > 0),
  balance_after NUMERIC(15,2) NOT NULL CHECK (balance_after >= 0),
  description VARCHAR(140) NOT NULL,
  txn_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_ledger_transfer_leg UNIQUE (transfer_id, txn_type)
);

CREATE TABLE IF NOT EXISTS notification_log (
  event_id UUID NOT NULL,
  account_number VARCHAR(12) NOT NULL,
  event_type VARCHAR(40) NOT NULL,
  channel VARCHAR(10) NOT NULL DEFAULT 'SMS',
  message VARCHAR(300) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, account_number)
);

CREATE INDEX IF NOT EXISTS ix_transfer_sender_day ON fund_transfer(from_account_id, created_at) WHERE status = 'COMPLETED';
CREATE INDEX IF NOT EXISTS ix_ledger_statement ON account_transaction(account_id, txn_time DESC, txn_id DESC);
CREATE INDEX IF NOT EXISTS ix_transfer_reference ON fund_transfer(reference_no);

CREATE OR REPLACE FUNCTION prevent_ledger_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'account_transaction is append-only';
END;
$$;
DROP TRIGGER IF EXISTS tr_account_transaction_immutable ON account_transaction;
CREATE TRIGGER tr_account_transaction_immutable BEFORE UPDATE OR DELETE ON account_transaction
FOR EACH ROW EXECUTE FUNCTION prevent_ledger_mutation();

GRANT CONNECT ON DATABASE bankdb TO bank_app;
GRANT USAGE ON SCHEMA public TO bank_app;
GRANT SELECT, INSERT ON customer TO bank_app;
GRANT SELECT, INSERT, UPDATE ON account TO bank_app;
GRANT SELECT, INSERT ON fund_transfer TO bank_app;
GRANT SELECT, INSERT ON account_transaction TO bank_app;
GRANT SELECT, INSERT ON notification_log TO bank_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bank_app;
REVOKE UPDATE, DELETE ON account_transaction FROM bank_app;
