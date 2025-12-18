from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    AdminViewSet,
    BiopsyResultViewSet,
    DoctorLoginView,
    DoctorSignupView,
    DoctorViewSet,
    HealthCheckView,
    ImageResultViewSet,
    ImageSampleViewSet,
    SkinCancerCheckupViewSet,
)

router = DefaultRouter()
router.register(r'doctors', DoctorViewSet, basename='doctor')
router.register(r'admins', AdminViewSet, basename='admin')
router.register(r'image-samples', ImageSampleViewSet, basename='image_sample')
router.register(r'image-results', ImageResultViewSet, basename='image_result')
router.register(r'biopsy-results', BiopsyResultViewSet, basename='biopsy_result')
router.register(r'skin-cancer-checkups', SkinCancerCheckupViewSet, basename='skin_cancer_checkup')

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/signup/doctor/', DoctorSignupView.as_view(), name='doctor_signup'),
    path('auth/login/', DoctorLoginView.as_view(), name='doctor_login'),
    path('healthz/', HealthCheckView.as_view(), name='healthz'),
    path('', include(router.urls)),
]
