import os
import urllib.parse as urlparse
from pathlib import Path
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or os.environ.get('SECRET_KEY') or 'django-insecure-tgh$8yv!sa7epy!@qi)3-%c@btrkw@_x#*z0_f0k+i$nbj&#@8'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = (os.environ.get('DJANGO_DEBUG') or os.environ.get('DEBUG', 'True')).lower() in ['1', 'true', 'yes']

ALLOWED_HOSTS_ENV = os.environ.get('DJANGO_ALLOWED_HOSTS') or os.environ.get('ALLOWED_HOSTS')
ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS_ENV.split(',') if h.strip()]


USE_X_FORWARDED_HOST = True

# Application definition

INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',
    'corsheaders',
    'rest_framework',
    'checkup',
    'biopsy_result',
    'API',
    'AI_Engine',
    'billing',
    'rest_framework_simplejwt',
    'user',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'MedMind_Backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'MedMind_Backend.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Optional: allow configuring the database via DATABASE_URL
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith('sqlite:///'):
        _db_path = DATABASE_URL.replace('sqlite:///', '')
        DATABASES['default'] = {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / _db_path,
        }
    elif DATABASE_URL.startswith('postgres://') or DATABASE_URL.startswith('postgresql://'):
        urlparse.uses_netloc.append('postgres')
        parsed = urlparse.urlparse(DATABASE_URL)
        DATABASES['default'] = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed.path.lstrip('/'),
            'USER': parsed.username or '',
            'PASSWORD': parsed.password or '',
            'HOST': parsed.hostname or 'localhost',
            'PORT': str(parsed.port or 5432),
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
            'ATOMIC_REQUESTS': (os.environ.get('DB_ATOMIC_REQUESTS', 'False')).lower() in ['1', 'true', 'yes'],
        }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 5,
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
}

# Use a custom user model defined in the `user` app
AUTH_USER_MODEL = 'user.User'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# CORS/CSRF configuration
ENV_CORS_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS')
CORS_ALLOW_ALL_ORIGINS = (os.environ.get('CORS_ALLOW_ALL_ORIGINS', 'True')).lower() in ['1', 'true', 'yes']
CORS_ALLOW_CREDENTIALS = (os.environ.get('CORS_ALLOW_CREDENTIALS', 'False')).lower() in ['1', 'true', 'yes']
if not CORS_ALLOW_ALL_ORIGINS and ENV_CORS_ORIGINS:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in ENV_CORS_ORIGINS.split(',') if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = []
CORS_ALLOW_HEADERS = [
    'authorization',
    'content-type',
    'x-csrftoken',
]
CORS_ALLOW_METHODS = [
    'GET',
    'POST',
    'PUT',
    'PATCH',
    'DELETE',
    'OPTIONS',
]

ENV_CSRF_TRUSTED = os.environ.get('CSRF_TRUSTED_ORIGINS')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in ENV_CSRF_TRUSTED.split(',')] if ENV_CSRF_TRUSTED else []
SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
CSRF_COOKIE_SAMESITE = os.environ.get('CSRF_COOKIE_SAMESITE', 'Lax')
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Celery configuration
# Use Redis as broker and backend for task results in development.
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/1')
# Execute tasks asynchronously via the broker.
CELERY_TASK_ALWAYS_EAGER = False

# Minimal JWT cookie config
REFRESH_COOKIE_NAME = os.environ.get('REFRESH_COOKIE_NAME', 'refresh_token')
REFRESH_COOKIE_PATH = os.environ.get('REFRESH_COOKIE_PATH', '/api/auth/')
REFRESH_COOKIE_SAMESITE = os.environ.get('REFRESH_COOKIE_SAMESITE', 'Lax')
# Use Secure cookies when not in DEBUG
_cookie_secure_env = os.environ.get('REFRESH_COOKIE_SECURE')
if _cookie_secure_env is None:
    REFRESH_COOKIE_SECURE = not DEBUG
else:
    REFRESH_COOKIE_SECURE = _cookie_secure_env.lower() in ['1', 'true', 'yes']
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_MAX_RETRIES = int(os.environ.get('CELERY_TASK_MAX_RETRIES', '3'))

# Email configuration (Gmail SMTP recommended via App Password)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = 'MedMind'
ACCOUNT_EMAIL_SUBJECT_PREFIX = ''

# JWT lifetimes
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

# Password reset token timeout (seconds)
PASSWORD_RESET_TIMEOUT = int(os.environ.get('PASSWORD_RESET_TIMEOUT', '3600'))