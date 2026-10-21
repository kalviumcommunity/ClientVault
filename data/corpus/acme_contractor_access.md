# ACME Logistics — Contractor & Vendor Access Policy
Document ID: KB-ONB-002 | Revision: 2.1
Client ID: ACME-001 | Security Tier: Level-2
Page 1 of 3 — CONFIDENTIAL — ACME LOGISTICS INC.
[Home] > [Security] > [Vendor Access]

## 1. Scope and Eligibility
This document defines temporary network and application access protocols for external contractors
and freight logistics partners supporting ACME Logistics operations.

Page 1 of 3 — CONFIDENTIAL — ACME LOGISTICS INC.
========================================================================

## 2. Contractor Verification & Screening
1. Background clearance confirmation must be uploaded to the ACME Vendor Portal.
2. An active non-disclosure agreement (NDA) must be verified by Legal.
3. Access sponsorship must come from an ACME Director or higher authority.

Notice: Copyright (c) 2026 ACME Logistics Inc. All Rights Reserved.
Page 2 of 3 — CONFIDENTIAL — ACME LOGISTICS INC.

## 3. Credential Provisioning & Time Limits
### Step 3.1: Ephemeral Certificate Generation
Contractor credentials are issued as short-lived x509 certificates with a maximum lifespan of 14 calendar days.

### Step 3.2: Bastion Host Restriction
All shell or database access must traverse the corporate bastion host `bastion.acme-logistics.net` with session recording enabled.

### Step 3.3: Automatic Revocation
Accounts without active session traffic for 72 consecutive hours are automatically suspended by IAM daemon `iam-watchdog`.

Page 3 of 3 — End of Document — CONFIDENTIAL — ACME LOGISTICS INC.
