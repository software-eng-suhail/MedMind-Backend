import os
import sys

# Ensure project root is on PYTHONPATH
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MedMind_Backend.settings')
import django
django.setup()

from user.models import User
from django.contrib.auth import authenticate

def print_users():
    print('Users:')
    for u in User.objects.all():
        print(f'username={u.username!r}, email={u.email!r}, is_active={u.is_active}, role={u.role}, id={u.id}')

def check_credentials(username, password):
    print('\nChecking authenticate() for', username)
    result = authenticate(username=username, password=password)
    print('authenticate() returned:', result)

if __name__ == '__main__':
    print_users()
    # optionally read username/password from env to test
    user = os.environ.get('CHECK_USER')
    pwd = os.environ.get('CHECK_PWD')
    if user and pwd:
        check_credentials(user, pwd)
    else:
        print('\nTo test a credential pair set environment variables CHECK_USER and CHECK_PWD and re-run this script.')
