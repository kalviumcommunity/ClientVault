# Nexus Financial Technologies — Regulatory Compliance & PCI-DSS Guide
Document ID: KB-CMP-002 | Revision: 3.0
Client Identifier: NEXUS-002 | Classification: Strictly Confidential
Page 1 of 3 — CONFIDENTIAL — NEXUS FINANCIAL TECHNOLOGIES
[Home] > [Compliance] > [PCI-DSS & SOC2]

## 1. Compliance Architecture Overview
Nexus Financial Technologies operates within Tier-1 PCI-DSS and SOC2 Type II regulatory boundaries.
All cardholder data (CHD) and sensitive authentication data (SAD) must be isolated from general compute clusters.

Page 1 of 3 — CONFIDENTIAL — NEXUS FINANCIAL TECHNOLOGIES
========================================================================

## 2. Cardholder Data Tokenization
1. Plaintext primary account numbers (PAN) must never enter persistent storage or log sinks.
2. The Nexus Tokenization Vault ingests raw card data directly from certified hardware payment terminals.
3. Applications receive non-reversible surrogate tokens formatted as UUIDv4 references with Luhn check preservation.

Notice: Copyright (c) 2026 Nexus Financial Technologies. All Rights Reserved.
Page 2 of 3 — CONFIDENTIAL — NEXUS FINANCIAL TECHNOLOGIES

## 3. Cryptographic Storage & Encryption
### Step 3.1: Data at Rest
All database partitions storing financial transaction records must utilize AES-256 GCM encryption.
Encryption keys are managed inside certified Cloud HSM modules and rotated bi-annually.

### Step 3.2: Data in Transit
All network communications must enforce TLS 1.3 with strict cipher suites.
Insecure TLS versions (1.0, 1.1, 1.2) are dropped at the edge cloud load balancer without negotiation.

Page 3 of 3 — End of Document — CONFIDENTIAL — NEXUS FINANCIAL TECHNOLOGIES
