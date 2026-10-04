INSERT INTO customer (customer_id, full_name, email, phone, date_of_birth, pan) OVERRIDING SYSTEM VALUE VALUES
  (1,'Priya Sharma','priya.sharma@example.com','9876500001','1990-04-12','ABCPS1234K'),
  (2,'Rahul Verma','rahul.verma@example.com','9876500002','1988-11-20','AKQPV5678L'),
  (3,'Ananya Iyer','ananya.iyer@example.com','9876500003','1992-07-08','BDIPA4321M')
ON CONFLICT (customer_id) DO NOTHING;
SELECT setval(pg_get_serial_sequence('customer','customer_id'), GREATEST((SELECT COALESCE(MAX(customer_id),1) FROM customer),1));

INSERT INTO account (account_id, account_number, customer_id, account_type, balance, status, opened_at, updated_at) OVERRIDING SYSTEM VALUE VALUES
  (1,'501000000001',1,'SAVINGS',55000,'ACTIVE','2026-09-01 10:00:00+05:30','2026-09-28 12:10:00+05:30'),
  (2,'501000000002',2,'SAVINGS',28500,'ACTIVE','2026-09-01 10:05:00+05:30','2026-09-01 10:05:00+05:30'),
  (3,'501000000003',2,'CURRENT',88000,'ACTIVE','2026-09-01 10:10:00+05:30','2026-09-01 10:10:00+05:30'),
  (4,'501000000004',3,'SAVINGS',13500,'ACTIVE','2026-09-01 10:15:00+05:30','2026-09-01 10:15:00+05:30'),
  (5,'501000000005',3,'CURRENT',5000,'FROZEN','2026-09-01 10:20:00+05:30','2026-09-01 10:20:00+05:30')
ON CONFLICT (account_id) DO NOTHING;
SELECT setval('account_number_seq', GREATEST((SELECT COALESCE(MAX(account_id),1) FROM account),1));

INSERT INTO fund_transfer (transfer_id, reference_no, idempotency_key, from_account_id, to_account_id, amount, remarks, created_at) VALUES
 ('00000000-0000-4000-8000-000000000001','TRF20260910000001','seed-transfer-1',1,2,5000,'Rent share','2026-09-10 09:30:00+05:30'),
 ('00000000-0000-4000-8000-000000000002','TRF20260915000002','seed-transfer-2',3,1,12000,'Invoice 1043','2026-09-15 14:00:00+05:30'),
 ('00000000-0000-4000-8000-000000000003','TRF20260920000003','seed-transfer-3',2,3,3500,'Utility bill','2026-09-20 11:30:00+05:30'),
 ('00000000-0000-4000-8000-000000000004','TRF20260928000004','seed-transfer-4',1,4,2000,'Birthday gift','2026-09-28 12:10:00+05:30')
ON CONFLICT (transfer_id) DO NOTHING;
SELECT setval('transfer_reference_seq', GREATEST((SELECT COUNT(*) FROM fund_transfer),1));

INSERT INTO account_transaction (account_id, transfer_id, txn_type, amount, balance_after, description, txn_time) VALUES
 (1,NULL,'CREDIT',50000,50000,'Initial deposit','2026-09-01 10:00:00+05:30'),
 (1,'00000000-0000-4000-8000-000000000001','DEBIT',5000,45000,'Transfer to 501000000002 - Rent share','2026-09-10 09:30:00+05:30'),
 (1,'00000000-0000-4000-8000-000000000002','CREDIT',12000,57000,'Transfer from 501000000003 - Invoice 1043','2026-09-15 14:00:00+05:30'),
 (1,'00000000-0000-4000-8000-000000000004','DEBIT',2000,55000,'Transfer to 501000000004 - Birthday gift','2026-09-28 12:10:00+05:30'),
 (2,NULL,'CREDIT',30000,30000,'Initial deposit','2026-09-01 10:05:00+05:30'),
 (2,'00000000-0000-4000-8000-000000000001','CREDIT',5000,35000,'Transfer from 501000000001 - Rent share','2026-09-10 09:30:00+05:30'),
 (2,'00000000-0000-4000-8000-000000000003','DEBIT',3500,31500,'Transfer to 501000000003 - Utility bill','2026-09-20 11:30:00+05:30'),
 (2,NULL,'DEBIT',3000,28500,'Card purchase','2026-09-25 13:15:00+05:30'),
 (3,NULL,'CREDIT',80000,80000,'Initial deposit','2026-09-01 10:10:00+05:30'),
 (3,'00000000-0000-4000-8000-000000000002','DEBIT',12000,68000,'Transfer to 501000000001 - Invoice 1043','2026-09-15 14:00:00+05:30'),
 (3,'00000000-0000-4000-8000-000000000003','CREDIT',3500,71500,'Transfer from 501000000002 - Utility bill','2026-09-20 11:30:00+05:30'),
 (3,NULL,'CREDIT',16500,88000,'Branch deposit','2026-09-29 10:00:00+05:30'),
 (4,NULL,'CREDIT',13500,13500,'Initial deposit','2026-09-01 10:15:00+05:30'),
 (4,'00000000-0000-4000-8000-000000000004','CREDIT',2000,15500,'Transfer from 501000000001 - Birthday gift','2026-09-28 12:10:00+05:30'),
 (4,NULL,'DEBIT',2000,13500,'ATM withdrawal','2026-09-30 10:00:00+05:30'),
 (5,NULL,'CREDIT',5000,5000,'Initial deposit','2026-09-01 10:20:00+05:30')
ON CONFLICT DO NOTHING;
SELECT setval(pg_get_serial_sequence('account_transaction','txn_id'), GREATEST((SELECT COALESCE(MAX(txn_id),1) FROM account_transaction),1));
