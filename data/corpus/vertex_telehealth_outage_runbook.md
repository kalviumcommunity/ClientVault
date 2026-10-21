# Vertex Health Systems — Telehealth Video Service Outage Runbook
Document ID: SOP-TEL-005 | Revision: 3.1
Client Identifier: VERTEX-003 | Service: WebRTC Video Consultation
Page 1 of 3 — CONFIDENTIAL — VERTEX HEALTH SYSTEMS
[Home] > [Telehealth] > [Incident Runbooks]

## 1. Outage Symptoms & Diagnostic Metrics
A telehealth service degradation is declared when WebRTC packet loss exceeds 8.0%
or media server connection failure rate exceeds 2.5% across 100 consecutive consultation rooms.

Page 1 of 3 — CONFIDENTIAL — VERTEX HEALTH SYSTEMS
========================================================================

## 2. Emergency Outage Mitigation Procedures
### Step 2.1: Automated Audio Fallback Bridge
If video stream negotiation times out after 12 seconds:
1. Trigger automatic audio bridge fallback via Twilio Voice SIP trunk.
2. Deliver in-app prompt to patient and clinician switching consultation to secure audio channel.
3. Record fallback event in clinical session log for provider billing parity.

Notice: Copyright (c) 2026 Vertex Health Systems Inc. All Rights Reserved.
Page 2 of 3 — CONFIDENTIAL — VERTEX HEALTH SYSTEMS

### Step 2.2: Media Server Pool Rerouting
To isolate degraded media cluster `cluster-east-webrtc-01`:
1. Execute command: `vertex-telehealth drain-pool --cluster cluster-east-webrtc-01 --grace-period 60s`.
2. Direct all new room allocation requests to standby media cluster `cluster-central-webrtc-02`.
3. Verify TLS cryptographic certificate binding on standby proxy nodes.

### Step 2.3: Provider Queue Broadcasting
Send real-time banner broadcast to all active hospital portal clinicians:
"Notice: Telehealth video routing operating in degraded fallback mode. Priority given to emergency psychiatric and urgent care consults."

Page 3 of 3 — End of Document — CONFIDENTIAL — VERTEX HEALTH SYSTEMS
