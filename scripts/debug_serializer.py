import os
import sys
import pathlib
import django
import json

project_root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MedMind_Backend.settings')
django.setup()

from django.conf import settings as dj_settings
try:
    dj_settings.ALLOWED_HOSTS = list(dj_settings.ALLOWED_HOSTS) + ['testserver', 'localhost', '127.0.0.1']
except Exception:
    dj_settings.ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

from checkup.serializers import SkinCancerCreateSerializer
from django.test.client import RequestFactory
from django.contrib.auth import get_user_model

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

rf = RequestFactory()
request = rf.post('/api/skin-cancer/', data=json.dumps(payload), content_type='application/json')

# Not authenticating request; serializer requires either doctor id existing or authenticated user.
serializer = SkinCancerCreateSerializer(data=payload, context={'request': request})
print('is_valid:', serializer.is_valid())
print('errors:', serializer.errors)
if serializer.is_valid():
    print('validated_data keys:', list(serializer.validated_data.keys()))
    print('validated_data:', serializer.validated_data)
    try:
        instance = serializer.save()
        print('saved instance id:', instance.pk)
    except Exception as e:
        print('save error:', type(e), e)
        # Reproduce lower-level steps manually to inspect DB state
        from checkup.models import Checkup, SkinCancerCheckup
        from django.contrib.auth import get_user_model
        User = get_user_model()
        doctor_obj = serializer.validated_data.get('doctor')
        checkup_kwargs = {
            'age': serializer.validated_data.get('age'),
            'gender': serializer.validated_data.get('gender'),
            'blood_type': serializer.validated_data.get('blood_type'),
            'doctor': doctor_obj,
        }
        print('Attempting manual Checkup create with:', checkup_kwargs)
        chk = Checkup.objects.create(**checkup_kwargs)
        print('Manual created checkup id:', chk.pk, 'age in object:', chk.age)
        # Query DB raw to inspect stored age
        qs = Checkup.objects.filter(pk=chk.pk).values('pk', 'age')
        print('DB query for checkup:', list(qs))
        try:
            lesion_fields = {k: serializer.validated_data.get(k) for k in ['lesion_size_mm','lesion_location','asymmetry','border_irregularity','color_variation','diameter_mm','evolution']}
            child = SkinCancerCheckup.objects.create(pk=chk.pk, **lesion_fields)
            print('Child created with id', child.pk)
        except Exception as e2:
            print('Child create error:', type(e2), e2)
else:
    print('Did not validate; aborting')
