# Auth Endpoints Test Requests

Base URL: `http://127.0.0.1:8000/api`

## 1. Doctor Signup
```bash
curl -X POST http://127.0.0.1:8000/api/auth/signup/doctor/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testdoctor",
    "email": "test@doctor.com",
    "password": "securepass123",
    "name": "Dr. Test"
  }'
```

**Expected Response:**
```json
{
  "refresh": "<jwt_token>",
  "access": "<jwt_token>",
  "doctor": {
    "id": 1,
    "name": "Dr. Test",
    "username": "testdoctor",
    "email": "test@doctor.com",
    "credits": 1000,
    "account_status": "NOT_VERIFIED",
    "email_verification_status": "PENDING",
    "profile_picture": null,
    "license_image": null,
    "created_at": "2025-12-31T..."
  }
}
```

## 2. Doctor Login
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testdoctor",
    "password": "securepass123"
  }'
```

**Or login with email:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@doctor.com",
    "password": "securepass123"
  }'
```

**Expected Response:**
```json
{
  "refresh": "<jwt_token>",
  "access": "<jwt_token>",
  "doctor": {
    "id": 1,
    "name": "Dr. Test",
    "username": "testdoctor",
    "email": "test@doctor.com",
    "credits": 1000,
    "account_status": "NOT_VERIFIED",
    "email_verification_status": "PENDING",
    "profile_picture": null,
    "license_image": null,
    "created_at": "2025-12-31T..."
  }
}
```

## 3. Verify Email (requires doctor authentication)
```bash
curl -X POST http://127.0.0.1:8000/api/auth/verify-email/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json"
```

**Expected Response:**
```json
{
  "detail": "Email verified successfully."
}
```

## 4. Logout (requires authentication)
```bash
curl -X POST http://127.0.0.1:8000/api/auth/logout/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json"
```

**Expected Response:**
```json
{
  "detail": "Successfully logged out."
}
```

## 5. Verify Doctor Account (admin only)
First, create an admin user via Django shell or using the admin endpoint.

```bash
# Create admin first (if not exists)
curl -X POST http://127.0.0.1:8000/api/admins/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin1",
    "email": "admin@test.com",
    "password": "adminpass123",
    "name": "Admin User"
  }'

# Get admin token
curl -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin1",
    "password": "adminpass123"
  }'

# Verify doctor
curl -X POST http://127.0.0.1:8000/api/auth/verify-doctor/ \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "doctor_id": 1
  }'
```

**Expected Response:**
```json
{
  "detail": "Doctor testdoctor verified successfully."
}
```

## 6. Suspend Doctor Account (admin only)
```bash
curl -X POST http://127.0.0.1:8000/api/auth/suspend-doctor/ \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "doctor_id": 1
  }'
```

**Expected Response:**
```json
{
  "detail": "Doctor testdoctor suspended successfully."
}
```

## 7. Token Refresh
```bash
curl -X POST http://127.0.0.1:8000/api/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{
    "refresh": "<refresh_token>"
  }'
```

**Expected Response:**
```json
{
  "access": "<new_access_token>"
}
```

---

## Complete Test Flow

### 1. Test Doctor Registration & Login Flow
```bash
# 1. Sign up
RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/auth/signup/doctor/ \
  -H "Content-Type: application/json" \
  -d '{"username":"doc1","email":"doc1@test.com","password":"pass123","name":"Dr. One"}')

echo $RESPONSE | jq .

# Extract access token (requires jq)
ACCESS=$(echo $RESPONSE | jq -r .access)

# 2. Verify email
curl -X POST http://127.0.0.1:8000/api/auth/verify-email/ \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json"

# 3. Logout
curl -X POST http://127.0.0.1:8000/api/auth/logout/ \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json"

# 4. Login again
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"doc1","password":"pass123"}'
```

### 2. Test Admin Verification Flow
```bash
# 1. Create admin
curl -X POST http://127.0.0.1:8000/api/admins/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@test.com","password":"admin123","name":"Admin"}'

# 2. Get admin token
ADMIN_TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r .access)

# 3. Verify doctor (use doctor_id from signup response)
curl -X POST http://127.0.0.1:8000/api/auth/verify-doctor/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"doctor_id":1}'

# 4. Check doctor status (get doctor details)
curl -X GET http://127.0.0.1:8000/api/doctors/1/ \
  -H "Content-Type: application/json"
```

---

## Using Python requests
```python
import requests

BASE_URL = "http://127.0.0.1:8000/api"

# 1. Signup
signup_response = requests.post(
    f"{BASE_URL}/auth/signup/doctor/",
    json={
        "username": "pydoc",
        "email": "py@doc.com",
        "password": "pass123",
        "name": "Python Doctor"
    }
)
print(signup_response.json())
access_token = signup_response.json()["access"]

# 2. Verify email
verify_response = requests.post(
    f"{BASE_URL}/auth/verify-email/",
    headers={"Authorization": f"Bearer {access_token}"}
)
print(verify_response.json())

# 3. Logout
logout_response = requests.post(
    f"{BASE_URL}/auth/logout/",
    headers={"Authorization": f"Bearer {access_token}"}
)
print(logout_response.json())

# 4. Login
login_response = requests.post(
    f"{BASE_URL}/auth/login/",
    json={"username": "pydoc", "password": "pass123"}
)
print(login_response.json())
```
