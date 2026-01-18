# Billing API Guide

Base path: `/api/billing/`

## Auth & Roles
- Auth required.
- Doctors: can purchase for themselves and list their own transactions.
- Admins: can purchase for a doctor (must provide `doctor_id`) and can list all transactions.

## Bundles
- Allowed values: `SMALL` (5,000 credits, $20), `MEDIUM` (10,000 credits, $35), `LARGE` (20,000 credits, $60).

## Create Purchase (idempotent)
- Endpoint: `POST /api/billing/`
- Doctors: omit `doctor_id`.
- Admins: include `doctor_id`.
- Idempotency: `idempotency_key` is required and unique per doctor. Reusing the same key returns the existing successful transaction and balance.

### Request (doctor)
```json
{
  "bundle": "MEDIUM",
  "idempotency_key": "checkout-12345"
}
```

### Request (admin for doctor id 17)
```json
{
  "bundle": "LARGE",
  "idempotency_key": "order-abc-001",
  "doctor_id": 17
}
```

### Success Response (201)
```json
{
  "id": 42,
  "doctor": 17,
  "bundle": "LARGE",
  "credits_added": 20000,
  "amount_usd": "60.00",
  "status": "SUCCESS",
  "provider": "SIMULATED",
  "provider_ref": null,
  "idempotency_key": "order-abc-001",
  "created_at": "2026-01-12T10:00:00Z",
  "new_balance": 45000
}
```
- `new_balance` shows the doctor’s updated credits.

### Idempotent Replay (same key)
- Returns the same transaction data and `new_balance`; no double charge, no extra credits.

### Validation Errors
- Missing `doctor_id` for admins, unknown doctor, invalid bundle, or duplicate `idempotency_key` + doctor → 400 with details.

#### Error: missing doctor_id (admin)
```json
{
  "doctor_id": ["This field is required for admins."]
}
```

#### Error: doctor not found
```json
{
  "doctor_id": ["Doctor not found."]
}
```

#### Error: invalid bundle
```json
{
  "bundle": ["Invalid bundle."]
}
```

#### Error: duplicate idempotency key (same doctor)
```json
{
  "detail": "Invalid refresh token."  // Returned as 401 only in refresh path; for purchases, duplicate returns the existing txn (200) rather than an error
}
```
Note: For purchases, a duplicate successful `idempotency_key` returns 201 with the existing transaction, not an error.

## List Transactions
- Endpoint: `GET /api/billing/`
- Doctor: sees own transactions.
- Admin: sees all transactions.
- Sorted newest first.

### Response (200)
```json
[
  {
    "id": 42,
    "doctor": 17,
    "bundle": "LARGE",
    "credits_added": 20000,
    "amount_usd": "60.00",
    "status": "SUCCESS",
    "provider": "SIMULATED",
    "provider_ref": null,
    "idempotency_key": "order-abc-001",
    "created_at": "2026-01-12T10:00:00Z"
  },
  {
    "id": 41,
    "doctor": 17,
    "bundle": "MEDIUM",
    "credits_added": 10000,
    "amount_usd": "35.00",
    "status": "SUCCESS",
    "provider": "SIMULATED",
    "provider_ref": null,
    "idempotency_key": "checkout-12345",
    "created_at": "2026-01-10T09:30:00Z"
  }
]
```

### Possible errors
- Auth missing/invalid: `401` with `{"detail": "Authentication credentials were not provided."}` or JWT error.
- Forbidden (non-admin accessing non-own data): `403` with `{"detail": "You do not have permission to perform this action."}`.

## Key Behaviors
- Credits applied immediately; transaction marked `SUCCESS` in one call.
- Unique constraint `(doctor, idempotency_key)` prevents duplicates.
- If the doctor profile is missing, purchase fails with 400 (`doctor profile missing`).
