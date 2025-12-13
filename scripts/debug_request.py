import os
import sys
import re
import json
import requests

BASE = os.environ.get('API_BASE', 'http://127.0.0.1:8000')
url = f"{BASE}/api/skin-cancer-checkups/"

# payload matching example.py
payload = {
    "age": "45",
    "gender": "male",
    "blood_type": "O+",
    "note": "Patient complained of lesion",
    "doctor": "9",
    "lesion_size_mm": "12.5",
    "lesion_location": "left_arm",
    "asymmetry": "false",
    "border_irregularity": "true",
    "color_variation": "true",
    "diameter_mm": "6.2",
    "evolution": "true",
}

files = [
    ("images", open(os.path.join('example_images', 'WEB06875.jpg'), 'rb')),
    ("images", open(os.path.join('example_images', 'WEB07174.jpg'), 'rb')),
]

try:
    r = requests.post(url, data=payload, files=files, timeout=10)
    print('POST URL:', url)
    print('Status:', r.status_code)
    print('Content-Type:', r.headers.get('Content-Type'))
    text = r.text
    with open('scripts/last_debug_response.html', 'w', encoding='utf-8') as fh:
        fh.write(text)
    print('Wrote scripts/last_debug_response.html')
    print('Response body (truncated):')
    print(text[:4000])
    # attempt to extract exception information
    trace_match = re.search(r'(Traceback \(most recent call last\):(.*)Exception Type:.*Exception Value:.*)', text, re.S)
    if trace_match:
        print('\n--- Extracted Traceback ---')
        print(trace_match.group(1))
    else:
        # search for Exception Type/Value
        et = re.search(r'Exception Type:\s*<strong>([^<]+)</strong>', text)
        ev = re.search(r'Exception Value:\s*<pre>([^<]+)</pre>', text)
        if et or ev:
            print('\n--- Exception Info ---')
            if et:
                print('Type:', et.group(1))
            if ev:
                print('Value:', ev.group(1))
except Exception as e:
    print('Request failed:', e)
    sys.exit(1)

