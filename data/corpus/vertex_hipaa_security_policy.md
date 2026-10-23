# Vertex Health Systems — HIPAA / HITECH Information Security Policy
Document ID: KB-HIPAA-002 | Revision: 4.5
Client Identifier: VERTEX-003 | Compliance Class: PHI / HIPAA Covered Entity
Page 1 of 3 — CONFIDENTIAL — VERTEX HEALTH SYSTEMS
[Home] > [Security] > [HIPAA Guidelines]

## 1. Protected Health Information (PHI) Definition
Protected Health Information encompasses any electronic health data, lab result, medical imaging,
or billing artifact containing direct or indirect patient identifiers defined by 45 CFR § 164.514.

Page 1 of 3 — CONFIDENTIAL — VERTEX HEALTH SYSTEMS
========================================================================

## 2. Technical Safeguards & Cryptographic Standards
1. All database storage partitions containing patient charts must be encrypted using FIPS 140-2 Level 3 validated modules.
2. Direct database exports to local operator workstations are strictly prohibited and automatically blocked by endpoint DLP.
3. Cryptographic hash checksums (SHA-256) must be generated for all clinical lab transmission payloads.

Notice: Copyright (c) 2026 Vertex Health Systems Inc. All Rights Reserved.
Page 2 of 3 — CONFIDENTIAL — VERTEX HEALTH SYSTEMS

## 3. Audit Logging & Retention Obligations
### Step 3.1: Immutable Access Logs
Every query, view, edit, or export of a patient chart records user identity, workstation IP, timestamp,
and accessed patient MRN into an immutable append-only Amazon S3 Glacier archive.

### Step 3.2: 7-Year Retention Horizon
In accordance with federal regulatory mandates, all clinical system access logs must be retained
for a minimum of 7 calendar years before authorized cryptographic shredding.

Page 3 of 3 — End of Document — CONFIDENTIAL — VERTEX HEALTH SYSTEMS
