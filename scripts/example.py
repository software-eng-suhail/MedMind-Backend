import os
import requests

BASE = os.environ.get('API_BASE', 'http://localhost:8000')
url = f"{BASE}/api/skin-cancer-checkups/"

# Use the exact payload from the original example
data = {
    "age": "20",
    "gender": "male",
    "blood_type": "O+",
    "note": "Patient complained of mole changes over the past 3 months.",
    "doctor": "14",
    "lesion_size_mm": "12.5",
    "lesion_location": "left_arm",
    "asymmetry": "false",
    "border_irregularity": "true",
    "color_variation": "true",
    "diameter_mm": "6.2",
    "evolution": "true",
}

# Optional: perform login to obtain JWT and include in Authorization header
LOGIN = {
    'username': os.environ.get('API_LOGIN_USER', ''),
    'password': os.environ.get('API_LOGIN_PASS', ''),
}

headers = {}
if LOGIN['username'] and LOGIN['password']:
    try:
        resp = requests.post(f"{BASE}/api/auth/login/", json=LOGIN)
        resp.raise_for_status()
        tok = resp.json().get('access')
        if tok:
            headers['Authorization'] = f'Bearer {tok}'
            print('Authenticated; Authorization header set')
    except Exception as e:
        print('Login failed, proceeding unauthenticated:', e)

files = [
    ("images", open(os.path.join('example_images', 'B3.png'), 'rb')),
    ("images", open(os.path.join('example_images', 'M2.png'), 'rb')),
]

with requests.Session() as s:
    r = s.post(url, headers=headers, data=data, files=files)
    print(r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text)
        
    # If the POST created a checkup and returned its id, fetch the results
    try:
        resp_json = r.json()
    except Exception:
        resp_json = None

    if r.ok and resp_json and isinstance(resp_json, dict) and resp_json.get('id'):
        checkup_id = resp_json.get('id')
        results_url = f"{BASE}/api/skin-cancer-checkups/{checkup_id}/results/"
        try:
            rr = s.get(results_url, headers=headers)
            print('Results GET', rr.status_code)
            try:
                print(rr.json())
            except Exception:
                print(rr.text)
        except Exception as e:
            print('Failed to fetch results:', e)
    else:
        print('No checkup id returned; skipping results fetch')

