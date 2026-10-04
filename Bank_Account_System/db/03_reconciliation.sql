-- R1: current balance equals the net append-only ledger movement per account.
SELECT a.account_number, a.balance AS account_balance,
       COALESCE(SUM(CASE WHEN l.txn_type='CREDIT' THEN l.amount ELSE -l.amount END),0) AS ledger_balance
FROM account a LEFT JOIN account_transaction l USING(account_id)
GROUP BY a.account_id,a.account_number,a.balance
HAVING a.balance <> COALESCE(SUM(CASE WHEN l.txn_type='CREDIT' THEN l.amount ELSE -l.amount END),0);

-- R2: completed transfers have exactly one equal amount debit and credit on the expected accounts.
SELECT t.reference_no, t.amount,
       COUNT(*) FILTER (WHERE l.txn_type='DEBIT' AND l.account_id=t.from_account_id AND l.amount=t.amount) AS debit_legs,
       COUNT(*) FILTER (WHERE l.txn_type='CREDIT' AND l.account_id=t.to_account_id AND l.amount=t.amount) AS credit_legs
FROM fund_transfer t LEFT JOIN account_transaction l USING(transfer_id)
WHERE t.status='COMPLETED'
GROUP BY t.transfer_id,t.reference_no,t.amount,t.from_account_id,t.to_account_id
HAVING COUNT(*) FILTER (WHERE l.txn_type='DEBIT' AND l.account_id=t.from_account_id AND l.amount=t.amount) <> 1
    OR COUNT(*) FILTER (WHERE l.txn_type='CREDIT' AND l.account_id=t.to_account_id AND l.amount=t.amount) <> 1;

-- R3: no negative balances and transfer ledger legs net to zero.
SELECT account_number,balance FROM account WHERE balance < 0;
SELECT t.reference_no, SUM(CASE WHEN l.txn_type='CREDIT' THEN l.amount ELSE -l.amount END) AS net
FROM fund_transfer t JOIN account_transaction l USING(transfer_id)
WHERE t.status='COMPLETED'
GROUP BY t.transfer_id,t.reference_no
HAVING SUM(CASE WHEN l.txn_type='CREDIT' THEN l.amount ELSE -l.amount END) <> 0;
