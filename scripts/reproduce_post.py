import os
import os
import sys
import pathlib
import django
import json
from django.conf import settings

# Ensure project root is on sys.path so the `MedMind_Backend` package can be imported
project_root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MedMind_Backend.settings')
django.setup()
# Allow the test client host used by Django's test client
from django.conf import settings as dj_settings
try:
    dj_settings.ALLOWED_HOSTS = list(dj_settings.ALLOWED_HOSTS) + ['testserver', 'localhost', '127.0.0.1']
except Exception:
    dj_settings.ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

from django.test import Client

payload = {
    "age": 45,
    "gender": "male",
    "blood_type": "A+",
    "doctor": 1,
    "lesion_size_mm": 12.5,
    "lesion_location": "left arm",
    "asymmetry": False,
    "border_irregularity": False,
    "color_variation": True,
    "diameter_mm": 12.5,
    "evolution": True
}

c = Client()
resp = c.post('/api/skin-cancer/', data=json.dumps(payload), content_type='application/json')
print('STATUS:', resp.status_code)
try:
    print('RESPONSE:', resp.json())
except Exception:
    print('RESPONSE (raw):', resp.content)

# Also print any server-side exceptions if they were attached to the response
if hasattr(resp, 'resolver_match'):
    print('Resolver match:', resp.resolver_match)
