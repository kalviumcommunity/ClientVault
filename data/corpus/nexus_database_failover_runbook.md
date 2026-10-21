# Nexus Financial Technologies — Database High Availability & Failover Protocol
Document ID: SOP-DR-004 | Revision: 4.2
Client Identifier: NEXUS-002 | Scope: Production Transaction Ledger
Page 1 of 3 — CONFIDENTIAL — NEXUS FINANCIAL TECHNOLOGIES
[Home] > [Infrastructure] > [Disaster Recovery]

## 1. High Availability Architecture
The Nexus financial ledger utilizes a Multi-AZ PostgreSQL cluster with continuous synchronous replication
to an active standby replica in AWS us-east-1 and asynchronous cross-region streaming to us-west-2.

Page 1 of 3 — CONFIDENTIAL — NEXUS FINANCIAL TECHNOLOGIES
========================================================================

## 2. Automatic Failover Criteria
1. Loss of primary node quorum heartbeat for 15 consecutive seconds.
2. Unrecoverable disk I/O degradation exceeding 3000ms per write block.
3. Network split-brain detection triggered by consensus coordinator daemon `pg-sentinel`.

Notice: Copyright (c) 2026 Nexus Financial Technologies. All Rights Reserved.
Page 2 of 3 — CONFIDENTIAL — NEXUS FINANCIAL TECHNOLOGIES

## 3. Manual Failover Execution Steps
### Step 3.1: Replication Lag Verification
Before forcing promotion of the standby node, execute:
```bash
nexus-db-admin check-lag --target replica-az2
```
Promotion is strictly prohibited if Write-Ahead Log (WAL) byte lag exceeds 1024 bytes.

### Step 3.2: Standby Promotion Command
Once replication parity is verified, execute:
```bash
nexus-db-admin promote --node db-standby-02 --force-authoritative
```

### Step 3.3: DNS Service Discovery Update
Route53 internal record `ledger-primary.nexus.internal` will automatically re-point within 5 seconds.
Verify application connection pools have drained and reconnected without dropped isolation transactions.

Page 3 of 3 — End of Document — CONFIDENTIAL — NEXUS FINANCIAL TECHNOLOGIES
