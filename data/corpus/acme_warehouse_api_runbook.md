# ACME Logistics — Warehouse Management REST API Runbook
Document ID: SOP-API-003 | Revision: 4.0
Client Identifier: ACME-001 | Target Environment: Production
Page 1 of 3 — CONFIDENTIAL — ACME LOGISTICS INC.
[Home] > [API Docs] > [Warehouse Service]

## 1. API Architecture & Authentication
The ACME Warehouse API provides automated inventory allocation, pallet barcode scanning,
and cross-dock validation. All requests require bearer token authentication using OAuth2.

Page 1 of 3 — CONFIDENTIAL — ACME LOGISTICS INC.
========================================================================

## 2. Rate Limits & Throttling
1. Standard warehouse nodes are restricted to 120 requests per minute per IP address.
2. Throttled requests receive HTTP 429 Too Many Requests with header `Retry-After: <seconds>`.
3. Automated exponential backoff with jitter must be implemented on all automated scanner clients.

Notice: Copyright (c) 2026 ACME Logistics Inc. All Rights Reserved.
Page 2 of 3 — CONFIDENTIAL — ACME LOGISTICS INC.

## 3. Operational Troubleshooting
### Step 3.1: Token Refresh Failures
If scanner terminals encounter HTTP 401 Unauthorized errors:
1. Verify token expiration timestamp in JWT payload.
2. Inspect clock drift on warehouse edge gateway; NTP synchronization drift must remain below 50ms.
3. Force token re-issuance using endpoint `POST /v2/auth/token/refresh` with client credentials.

### Step 3.2: Shipment Webhook Dead-Letter Queue
Unacknowledged shipment status webhooks are routed to dead-letter queue `dlq-acme-shipments`.
Operators must execute replay script `requeue-shipments --batch-size 50` after verifying destination endpoint health.

Page 3 of 3 — End of Document — CONFIDENTIAL — ACME LOGISTICS INC.
