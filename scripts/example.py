import requests

url = "http://localhost:8000/api/skin-cancer-checkups/"
headers = {}
data = {
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
    ("images", open(r"C:/Users\Black Surface/Pictures/Screenshots/Screenshot 2024-09-07 000111.png", "rb")),
    ("images", open(r"C:/Users\Black Surface/Pictures/Screenshots/Screenshot 2024-09-07 000111.png", "rb")),
]

r = requests.post(url, headers=headers, data=data, files=files)
print(r.status_code)
print(r.text)