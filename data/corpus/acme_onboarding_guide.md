# ACME Logistics — Client Onboarding & Authentication Runbook
Document ID: KB-ONB-001 | Revision: 3.2
Classification: Internal Client Support Only
Page 1 of 4 — CONFIDENTIAL — ACME LOGISTICS INC.
[Home] > [Client Portal] > [Knowledge Base] > [Onboarding]

## 1. Overview
This procedure governs onboarding verification, sponsor authorization,
and initial credential provisioning for ACME Logistics (Client ID: ACME-001).

Page 1 of 4 — CONFIDENTIAL — ACME LOGISTICS INC.
========================================================================

## 2. Pre-Requisites
1. Requester email domain must strictly match `@acme-logistics.com`.
2. Valid ticket reference in ServiceNow queue `SEC-ONB`.
3. Identity confirmation verified via primary sponsor directory.

Notice: Copyright (c) 2026 ACME Logistics Inc. All Rights Reserved.
Page 2 of 4 — CONFIDENTIAL — ACME LOGISTICS INC.

## 3. Provisioning Procedure
### Step 3.1: Sponsor Verification
Verify corporate identity against the approved client sponsor roster.
Requests from generic domains (gmail, yahoo) must be rejected immediately.

Page 3 of 4 — CONFIDENTIAL — ACME LOGISTICS INC.

### Step 3.2: Dual-Operator Sign-Off
Dual-operator authorization is strictly required:
1. Operator 1 initiates the credential generation request in the admin IAM portal.
2. Operator 2 (Senior Desk Lead) inspects the verification ticket and signs off with cryptographic OTP.

### Step 3.3: Sandbox Confinement
All newly generated credentials must be bound strictly to the Staging VPC sandbox
for the first 48 hours with audit trail logging enabled.

Page 4 of 4 — End of Document — CONFIDENTIAL — ACME LOGISTICS INC.
