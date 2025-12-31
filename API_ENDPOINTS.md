# API Endpoints

Base URL: `/api/`
Auth: JWT — send `Authorization: Bearer <access_token>`.
Content type: JSON unless uploading files (`multipart/form-data`).

## Conventions
- File uploads: `profile_picture`, `license_image`, `images[0].image`…`images[4].image`, `document` must be multipart.
- Generic attachments: `content_type` uses `app_label.model` (lowercase), e.g. `checkup.skincancercheckup`.
- Async inference: creating a checkup enqueues a Celery task; poll the `results` action or read `status`/`task_id`.

## Auth
- `POST /api/token/`
  - Request
    ```json
    {"username":"doc1","password":"secret"}
    ```
  - Response
    ```json
    {"refresh":"<jwt>","access":"<jwt>"}
    ```
- `POST /api/token/refresh/`
  - Request
    ```json
    {"refresh":"<jwt>"}
    ```
  - Response
    ```json
    {"access":"<jwt>"}
    ```
- `POST /api/auth/signup/doctor/`
  - Request (JSON or multipart; files optional)
    ```json
    {
      "username":"derm1",
      "email":"derm1@example.com",
      "password":"secret",
      "name":"Dr. Derm",
      "credits":500,
      "account_status":"ACTIVE"
    }
    ```
  - Response
    ```json
    {
      "refresh":"<jwt>",
      "access":"<jwt>",
      "doctor":{
        "id":1,
        "name":"Dr. Derm",
        "username":"derm1",
        "email":"derm1@example.com",
        "credits":500,
        "account_status":"ACTIVE",
        "profile_picture":null,
        "license_image":null,
        "created_at":"2025-01-01T10:00:00Z"
      }
    }
    ```
- `POST /api/auth/login/`
  - Request
    ```json
    {"username":"derm1","password":"secret"}
    ```
  - Response (same shape as signup)
    ```json
    {"refresh":"<jwt>","access":"<jwt>","doctor":{...}}
    ```

## Doctors
- `GET /api/doctors/` — list doctors.
- `POST /api/doctors/` — create (same fields as signup; role forced to doctor).
  ```json
  {
    "username":"doc2",
    "email":"doc2@example.com",
    "password":"secret",
    "name":"Dr. Two"
  }
  ```
- `/api/doctors/{id}/` — `GET`, `PUT/PATCH`, `DELETE`.
- `/api/doctors/{id}/checkups/` — `GET` checkups for that doctor.

## Admins
- `GET /api/admins/` — list admins.
- `POST /api/admins/`
  ```json
  {"username":"admin1","email":"a1@example.com","password":"secret","name":"Alice"}
  ```
- `/api/admins/{username}/` — `GET`, `PUT/PATCH`, `DELETE`.

## Skin Cancer Checkups
- `GET /api/skin-cancer-checkups/` — list (supports filter/search/order).
- `POST /api/skin-cancer-checkups/` — creates and deducts 100 credits, queues inference.
  ```json
  {
    "doctor":1,
    "age":45,
    "gender":"male",
    "blood_type":"O+",
    "lesion_size_mm":5.2,
    "lesion_location":"arm",
    "asymmetry":true,
    "border_irregularity":false,
    "color_variation":true,
    "diameter_mm":6.0,
    "evolution":true,
    "note":"Raised lesion"
  }
  ```
  Multipart keys for images: `images[0].image`, `images[1].image`, ...
- `GET /api/skin-cancer-checkups/{id}/` — full detail.
- `GET /api/skin-cancer-checkups/{id}/results/?wait=30` — poll inference.
  - `202 Accepted`
    ```json
    {"status":"PENDING","task_id":"abcd"}
    ```
  - `200 OK`
    ```json
    {"status":"COMPLETED","task_id":"abcd","results":[{"id":10,"result":"melanoma","confidence":0.91}]}
    ```

## Biopsy Results
- `POST /api/biopsy-results/` (multipart upload)
  ```json
  {
    "content_type":"checkup.skincancercheckup",
    "object_id":12,
    "result":"Histopathology confirms malignant melanoma (Breslow 1.2mm).",
    "status":"PENDING",
    "credits_refunded":false
  }
  ```
- `GET /api/biopsy-results/{id}/` — returns review serializer shape.
- `POST /api/biopsy-results/{id}/verify/` (admin only) — sets status `VERIFIED`, records admin, refunds 100 credits once.
  ```json
  {
    "id":5,
    "result":"Confirmed malignant melanoma",
    "document":"https://.../report.pdf",
    "status":"VERIFIED",
    "credits_refunded":true,
    "verified_by":{"id":2,"name":"Dr. Admin"},
    "uploaded_at":"2025-01-02T09:00:00Z",
    "checkup":{
      "id":12,
      "age":45,
      "gender":"male",
      "blood_type":"O+",
      "note":"Raised lesion",
      "checkup_type":"SKIN_CANCER",
      "lesion_size_mm":5.2,
      "lesion_location":"arm",
      "asymmetry":true,
      "border_irregularity":false,
      "color_variation":true,
      "diameter_mm":6.0,
      "evolution":true,
      "images":["https://.../img1.jpg","https://.../img2.jpg"]
    },
    "doctor":{
      "id":1,
      "username":"derm1",
      "name":"Dr. Derm",
      "profile_picture":"https://.../avatar.jpg"
    }
  }
  ```

## Image Samples
- `POST /api/image-samples/` (multipart)
  ```json
  {"content_type":"checkup.skincancercheckup","object_id":12,"image":"<file>"}
  ```
- `GET /api/image-samples/` — list; `/api/image-samples/{id}/` — detail/update/delete.

## Image Results
- `GET /api/image-results/` — list; `/api/image-results/{id}/` — detail.
- `POST /api/image-results/`
  ```json
  {"image_sample":21,"result":"melanoma","model":"efficientnetb0","confidence":0.91}
  ```

## Health
- `GET /api/healthz/`
  ```json
  {"status":"ok","database":"ok"}
  ```
