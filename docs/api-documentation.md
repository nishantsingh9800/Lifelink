# LifeLink API Documentation

Interactive OpenAPI / Swagger documentation is automatically served by FastAPI at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Modular API Routers

| Prefix | Router | Key Endpoints |
| --- | --- | --- |
| `/api` | System | `GET /api/health`, `GET /api/config/public` |
| `/api/auth` | Authentication | `POST /aadhaar/verify-init`, `POST /register`, `POST /login`, `GET /me`, `POST /otp/send`, `POST /otp/verify`, `POST /dev-verify-phone`, `POST /dev-verify-aadhaar`, `POST /logout` |
| `/api/users` | Users | `GET /me`, `PATCH /me`, `GET/PATCH /me/preferences` |
| `/api/donors` | Donors | `GET /me`, `PUT /me`, `PATCH /me/availability`, `GET/PUT /me/calendar`, `GET /me/trust-profile`, `GET /{id}/trust-profile`, `GET/POST /me/donations`, `PATCH /me/donations/{id}`, `POST /me/availability-reminder`, `GET/PATCH /me/appreciation`, `GET /me/documents`, `POST /me/documents/upload`, `GET /me/face`, `POST /me/face/enroll`, `POST /me/face/verify` |
| `/api/requests` | Blood Requests | `POST ""`, `GET ""`, `GET /{id}`, `GET /{id}/tracking-summary`, `PATCH /{id}`, `POST /{id}/cancel`, `POST /{id}/outcome`, `GET /{id}/history` |
| `/api/coordinators` | Emergency Coordinators | `GET /my-assignments`, `GET /{request_id}`, `POST /{request_id}/invite`, `POST /{id}/respond`, `POST /{id}/revoke`, `POST /{request_id}/progress` |
| `/api/hospitals` | Hospital Verification | `GET /verified`, `GET/POST /me`, `POST /me/documents/upload`, `GET /requests`, `POST /requests/{id}/confirm`, `POST /requests/{id}/close` |
| `/api/family` | Family Emergency Account | `GET/POST /contacts`, `POST /contacts/{id}/respond`, `POST /contacts/{id}/revoke` |
| `/api/share` | Request Sharing | `POST /api/share/{request_id}`, `POST /api/share/{request_id}/disable`, `GET/POST /api/public/shared/{token}` |
| `/api/referrals` | Community Referrals | `GET /me` |
| `/api/integrations` | Integration Readiness | `GET /status`, `POST /eraktkosh/sync`, `POST /masked-call/{request_id}/initiate`, `POST /push/dispatch` |
| `/api/matching` | Matching & Escalation | `POST /{request_id}/run`, `POST /{request_id}/escalate`, `GET /{request_id}/candidates` |
| `/api/responses` | Donor Responses | `GET /incoming`, `POST /{request_id}/respond`, `GET /{request_id}` |
| `/api/notifications` | Notifications | `GET ""`, `POST /{id}/read`, `POST /read-all` |
| `/api/conversations` | Private Conversations | `GET ""`, `GET /{id}` |
| `/api/messages` | Private Messages | `GET /{conversation_id}`, `POST /{conversation_id}`, `POST /{conversation_id}/read` |
| `/api/contact-sharing` | Consent Phone Sharing | `GET /{request_id}`, `POST /{request_id}/consent`, `POST /{request_id}/withdraw` |
| `/api/blood-banks` | Directory & Fallback | `GET ""`, `GET /{id}`, `POST /{id}/contact-attempt`, `GET /attempts/{request_id}` |
| `/api/tracking` | Live Radius Map | `POST /{request_id}/update`, `POST /{request_id}/stop`, `GET /{request_id}` |
| `/api/chatbot` | Rule-Based Assistant | `POST /message`, `GET /history` |
| `/api/reports` | Safety & Blocking | `POST ""`, `POST /block` |
| `/api/admin` | Admin Console (Admin Only) | `GET /overview`, `GET /users`, `PATCH /users/{id}/status`, `GET /donor-documents`, `GET /donor-documents/{id}/file`, `PATCH /donor-documents/{id}`, `GET /requests`, `PATCH /requests/{id}/moderate`, `GET /reports`, `PATCH /reports/{id}`, `POST/PATCH/DELETE /blood-banks`, `GET /analytics`, `GET /audit-logs` |
| `/api/public` | Public Safe Discovery | `GET /donors`, `GET /blood-banks` |
