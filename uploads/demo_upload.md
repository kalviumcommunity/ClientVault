# ACME Logistics — Emergency Firewall Access Procedure
Client ID: ACME-001
Document Code: SOP-FW-EMERGENCY-001
Revision: 1.0

## 1. Purpose
This procedure governs temporary emergency firewall access for ACME Logistics production network.

## 2. Prerequisites
1. Valid incident ticket in ServiceNow queue SEC-INFRA.
2. Approval from Network Operations Lead (on-call).
3. Requester must be on the approved vendor access roster.

## 3. Procedure Steps
1. Login to the ACME firewall admin console at https://fw-admin.acme-logistics.internal.
2. Create a time-bound rule with 4-hour maximum TTL.
3. Log the change in the change management system with ticket reference.
4. Verify connectivity from the authorized source IP to the target resource.
5. Remove the rule immediately after the incident is resolved.

## 4. Audit Requirements
All emergency access grants must be logged with: timestamp, requester ID, approving lead, rule ID, and deactivation confirmation.
