# Auth API Guide

Base URL: `/api/`

## Endpoints

### Doctor Signup
`POST /api/auth/signup/doctor/`

Use to create a doctor account and receive JWT tokens.

- Content-Type: `multipart/form-data` (when sending `profile_picture`) or `application/json` (no file).
- Body fields:
  - `username` (string, required)
  - `email` (string, required)
  - `password` (string, required)
  - `name` (string, optional)
  - `credits` (integer, optional)
  - `account_status` (optional; one of `ACTIVE`, `LOGGED_OUT`, `SUSPENDED`, `NOT_VERIFIED`; defaults to `ACTIVE`)
  - `profile_picture` (file, optional; multipart only)

Example (JSON):
```http
POST /api/auth/signup/doctor/
Content-Type: application/json

{
  "username": "drsmith",
  "email": "drsmith@example.com",
  "password": "S3cureP@ss!",
  "name": "Dr. Smith",
  "credits": 100
}
```

Example (multipart with picture):
```http
POST /api/auth/signup/doctor/
Content-Type: multipart/form-data

username=drsmith&email=drsmith@example.com&password=S3cureP@ss!&name=Dr. Smith
--boundary
Content-Disposition: form-data; name="profile_picture"; filename="avatar.jpg"
Content-Type: image/jpeg

<binary>
--boundary--
```

Success 201 response:
```json
{
  "refresh": "<jwt-refresh>",
  "access": "<jwt-access>",
  "doctor": {
    "id": 12,
    "name": "Dr. Smith",
    "username": "drsmith",
    "email": "drsmith@example.com",
    "credits": 100,
    "account_status": "ACTIVE",
    "profile_picture": "https://api.example.com/media/profile_pics/avatar.jpg",
    "created_at": "2025-12-18T10:15:30Z"
  }
}
```

### Doctor Login
`POST /api/auth/login/`

Issues a JWT pair for existing doctors.

- Content-Type: `application/json`
- Body:
  - `username` **or** `email` (string, required)
  - `password` (string, required)

Example:
```http
POST /api/auth/login/
Content-Type: application/json

{
  "username": "drsmith",
  "password": "S3cureP@ss!"
}
```

Success 200 response:
```json
{
  "refresh": "<jwt-refresh>",
  "access": "<jwt-access>",
  "doctor": {
    "id": 12,
    "name": "Dr. Smith",
    "username": "drsmith",
    "email": "drsmith@example.com",
    "credits": 100,
    "account_status": "ACTIVE",
    "profile_picture": "https://api.example.com/media/profile_pics/avatar.jpg",
    "created_at": "2025-12-18T10:15:30Z"
  }
}
```

Errors: 400 missing fields, 401 invalid credentials, 403 if user is not a doctor.

### Obtain JWT Pair (generic)
`POST /api/token/`

Body: `{"username": "<user>", "password": "<pass>"}`

Response 200:
```json
{ "refresh": "<jwt-refresh>", "access": "<jwt-access>" }
```

### Refresh Access Token
`POST /api/token/refresh/`

Body: `{"refresh": "<jwt-refresh>"}`

Response 200:
```json
{ "access": "<new-jwt-access>" }
```

## Usage
- Send `Authorization: Bearer <access>` on protected endpoints.
- Use multipart only when uploading `profile_picture`; otherwise JSON is simpler.
- `account_status` is optional on signup (default `ACTIVE`).
- `profile_picture` responses are absolute URLs when the API can build them from the request.

