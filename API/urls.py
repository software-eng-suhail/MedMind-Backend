from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DoctorViewSet,
    AdminViewSet,
    CheckupViewSet,
    SkinCancerCheckupViewSet,
    ImageSampleViewSet,
    ImageResultViewSet,
    BiopsyResultViewSet,
)

router = DefaultRouter()
router.register(r'doctors', DoctorViewSet, basename='doctor')
router.register(r'admins', AdminViewSet, basename='admin')
router.register(r'checkups', CheckupViewSet, basename='checkup')
router.register(r'skin-cancer', SkinCancerCheckupViewSet, basename='skin_cancer')
router.register(r'image-samples', ImageSampleViewSet, basename='image_sample')
router.register(r'image-results', ImageResultViewSet, basename='image_result')
router.register(r'biopsy-results', BiopsyResultViewSet, basename='biopsy_result')

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]
