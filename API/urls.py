from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DoctorViewSet, AdminViewSet

router = DefaultRouter()
router.register(r'doctors', DoctorViewSet, basename='doctor')
router.register(r'admins', AdminViewSet, basename='admin')

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]
