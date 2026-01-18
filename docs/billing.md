## Create Purchase (idempotent)
- Endpoint: `POST /api/billing/`
- Idempotency: `idempotency_key` is required and unique per doctor. Reusing the same key returns the existing successful transaction and balance.

### Request (doctor)
```json
{
  "bundle": "MEDIUM",
  "idempotency_key": "checkout-12345"
}
```

## Bundles
- Allowed values: `SMALL` (5,000 credits, $20), `MEDIUM` (10,000 credits, $35), `LARGE` (20,000 credits, $60).