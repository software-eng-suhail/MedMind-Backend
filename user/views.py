import time

from django.contrib.auth import authenticate
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.conf import settings
from django.core.mail import send_mail
from django.core import signing
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from django.http import HttpResponse

from user.models import User, EmailVerificationStatus
from user.serializers import (
	DoctorSerializer,
	DoctorWriteSerializer,
	LoginSerializer,
)


class DoctorViewSet(viewsets.ModelViewSet):
	queryset = User.objects.filter(role=User.Role.DOCTOR).select_related('doctor_profile')
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser, JSONParser]

	def get_queryset(self):
		qs = super().get_queryset()
		user = getattr(self.request, 'user', None)
		# Doctors can only see/update themselves
		if getattr(user, 'is_doctor', lambda: False)():
			qs = qs.filter(pk=user.pk)
		return qs

	def get_serializer_class(self):
		if self.action in ['create', 'update', 'partial_update']:
			return DoctorWriteSerializer
		return DoctorSerializer

	def perform_destroy(self, instance):
		"""Soft-delete: mark user inactive instead of removing the record."""
		instance.is_active = False
		instance.save(update_fields=['is_active'])


class AuthViewSet(viewsets.ViewSet):
	permission_classes = [permissions.AllowAny]
	parser_classes = [MultiPartParser, FormParser, JSONParser]

	class DoctorIdSerializer(serializers.Serializer):
		doctor_id = serializers.IntegerField(required=True)

	class EmptySerializer(serializers.Serializer):
		pass

	class ForgotPasswordSerializer(serializers.Serializer):
		email = serializers.EmailField(required=True)

	class ResetPasswordSerializer(serializers.Serializer):
		uid = serializers.CharField(required=True)
		token = serializers.CharField(required=True)
		new_password = serializers.CharField(required=True, min_length=8)

	serializer_action_classes = {
		'signup_doctor': DoctorWriteSerializer,
		'login': LoginSerializer,
		'logout': EmptySerializer,
		'verify_email': EmptySerializer,
		'verify_doctor': DoctorIdSerializer,
		'suspend_doctor': DoctorIdSerializer,
		'password_forgot': ForgotPasswordSerializer,
		'password_reset': ResetPasswordSerializer,
	}

	def get_serializer_class(self):
		return self.serializer_action_classes.get(self.action)

	def get_serializer(self, *args, **kwargs):
		serializer_class = self.get_serializer_class()
		if serializer_class is None:
			return None
		kwargs.setdefault('context', self.get_serializer_context())
		return serializer_class(*args, **kwargs)

	def get_serializer_context(self):
		return {'request': self.request, 'format': self.format_kwarg, 'view': self}

	@action(detail=False, methods=['post'], url_path='signup/doctor')
	def signup_doctor(self, request):
		# Block re-signup with a soft-deleted account
		email = request.data.get('email')
		if email:
			deleted = User.objects.filter(email=email, is_active=False).first()
			if deleted:
				return Response({'detail': 'Deleted account.'}, status=status.HTTP_400_BAD_REQUEST)

		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.save()

		# Automatically send verification email after signup
		email = getattr(user, 'email', None)
		if email:
			try:
				token = signing.dumps({'uid': user.pk}, salt='email-verify')
				verify_url = request.build_absolute_uri(f"/api/auth/verify-email?token={token}")
				subject = 'Verify your MedMind email'
				body = (
					f'Hello {user.username or user.email},\n\n'
					f'Please verify your email by clicking the link below (valid for 24 hours):\n'
					f'{verify_url}\n\n'
					'If you did not request this, you can ignore this email.'
				)
				send_mail(subject, body, settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER, [email], fail_silently=True)
			except Exception:
				pass

		return Response(status=status.HTTP_201_CREATED)

	@action(detail=False, methods=['post'], url_path='login')
	def login(self, request):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		username = serializer.validated_data.get('username') or serializer.validated_data.get('email')
		password = serializer.validated_data['password']

		user = authenticate(request, username=username, password=password)
		if user is None:
			try:
				u = User.objects.get(email=username)
			except User.DoesNotExist:
				return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
			user = authenticate(request, username=u.username, password=password)
			if user is None:
				return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

		if not user.is_active:
			return Response({'detail': 'Account is deleted'}, status=status.HTTP_403_FORBIDDEN)

		if not user.is_doctor():
			return Response({'detail': 'User is not a doctor'}, status=status.HTTP_403_FORBIDDEN)

		if not user.is_verified_email():
			return Response({'detail': 'Email not verified'}, status=status.HTTP_403_FORBIDDEN)

		if user.is_suspended_doctor():
			return Response({'detail': 'Doctor account is suspended'}, status=status.HTTP_403_FORBIDDEN)

		if not user.is_verified_doctor():
			return Response({'detail': 'Doctor account not verified'}, status=status.HTTP_403_FORBIDDEN)

		profile = getattr(user, 'doctor_profile', None)
		if profile:
			profile.logged_in = True
			profile.save(update_fields=['logged_in'])

		refresh = RefreshToken.for_user(user)
		access = str(refresh.access_token)
		resp = Response({
			'access': access,
			'doctor': DoctorSerializer(user, context={'request': request}).data,
		})
		# Set HttpOnly refresh cookie
		cookie_name = getattr(settings, 'REFRESH_COOKIE_NAME', 'refresh_token')
		cookie_path = getattr(settings, 'REFRESH_COOKIE_PATH', '/api/auth/')
		samesite = getattr(settings, 'REFRESH_COOKIE_SAMESITE', 'Lax')
		secure = getattr(settings, 'REFRESH_COOKIE_SECURE', not settings.DEBUG)
		max_age = int(getattr(settings, 'SIMPLE_JWT', {}).get('REFRESH_TOKEN_LIFETIME', timedelta(days=1)).total_seconds()) if isinstance(getattr(settings, 'SIMPLE_JWT', {}).get('REFRESH_TOKEN_LIFETIME', timedelta(days=1)), timedelta) else 24*60*60
		resp.set_cookie(
			cookie_name,
			str(refresh),
			max_age=max_age,
			httponly=True,
			secure=secure,
			path=cookie_path,
			samesite=samesite,
		)
		return resp

	@action(detail=False, methods=['post'], url_path='logout', permission_classes=[permissions.IsAuthenticated])
	def logout(self, request):
		user = request.user
		if user.is_doctor():
			profile = getattr(user, 'doctor_profile', None)
			if profile:
				profile.logged_in = False
				profile.save(update_fields=['logged_in'])
		# Clear refresh cookie
		resp = Response({'detail': 'Successfully logged out.'}, status=status.HTTP_200_OK)
		cookie_name = getattr(settings, 'REFRESH_COOKIE_NAME', 'refresh_token')
		cookie_path = getattr(settings, 'REFRESH_COOKIE_PATH', '/api/auth/')
		samesite = getattr(settings, 'REFRESH_COOKIE_SAMESITE', 'Lax')
		resp.delete_cookie(cookie_name, path=cookie_path, samesite=samesite)
		return resp

	@action(detail=False, methods=['post'], url_path='refresh')
	def refresh(self, request):
		cookie_name = getattr(settings, 'REFRESH_COOKIE_NAME', 'refresh_token')
		refresh_token = request.COOKIES.get(cookie_name) or request.data.get('refresh') or request.data.get('refresh_token')
		# Debug: log what we received (will show None if absent)
		print(f"[DEBUG] refresh token from cookie: {request.COOKIES.get(cookie_name)!r}, from body: {request.data.get('refresh') or request.data.get('refresh_token')!r}")
		if not refresh_token:
			return Response({'detail': 'No refresh token provided.'}, status=status.HTTP_401_UNAUTHORIZED)
		try:
			ref = RefreshToken(refresh_token)
			access = str(ref.access_token)
			return Response({'access': access})
		except Exception:
			return Response({'detail': 'Invalid refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)

	@action(detail=False, methods=['post'], url_path='send-verification-email', permission_classes=[permissions.AllowAny])
	def send_verification_email(self, request):
		target_user = None

		email_param = request.data.get('email')
		if not email_param:
			return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

		try:
			target_user = User.objects.get(email=email_param, role=User.Role.DOCTOR)
		except User.DoesNotExist:
			return Response({'detail': 'Doctor not found for this email.'}, status=status.HTTP_404_NOT_FOUND)

		email = getattr(target_user, 'email', None)

		token = signing.dumps({'uid': target_user.pk}, salt='email-verify')
		verify_url = request.build_absolute_uri(f"/api/auth/verify-email?token={token}")

		subject = 'Verify your MedMind email'
		body = (
			f'Hello {target_user.username or target_user.email},\n\n'
			f'Please verify your email by clicking the link below (valid for 24 hours):\n'
			f'{verify_url}\n\n'
			'If you did not request this, you can ignore this email.'
		)

		try:
			send_mail(subject, body, settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER, [email], fail_silently=False)
		except Exception as exc:
			return Response({'detail': f'Failed to send email: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

		return Response({'detail': 'Verification email sent.'}, status=status.HTTP_200_OK)

	@action(detail=False, methods=['post'], url_path='verify-email')
	def verify_email(self, request):
		token = request.data.get('token') or request.query_params.get('token')
		if not token:
			return Response({'detail': 'Missing token.'}, status=status.HTTP_400_BAD_REQUEST)

		try:
			data = signing.loads(token, max_age=24 * 60 * 60, salt='email-verify')
		except Exception:
			return Response({'detail': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)

		uid = data.get('uid')

		try:
			user = User.objects.get(pk=uid)
		except User.DoesNotExist:
			return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

		profile = getattr(user, 'doctor_profile', None)
		if not profile:
			return Response({'detail': 'Doctor profile not found.'}, status=status.HTTP_400_BAD_REQUEST)

		profile.email_verification_status = EmailVerificationStatus.VERIFIED
		profile.save(update_fields=['email_verification_status'])

		return Response({'detail': 'Email verified successfully.'}, status=status.HTTP_200_OK)

	@action(detail=False, methods=['post'], url_path='password/forgot')
	def password_forgot(self, request):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		email = serializer.validated_data['email']

		# Always return 200 to avoid user enumeration
		response_payload = {'detail': 'If an account exists for this email, a reset link has been sent.'}

		try:
			user = User.objects.get(email=email)
			# Generate reset token
			token_generator = PasswordResetTokenGenerator()
			token = token_generator.make_token(user)
			uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
			# Build absolute URL to backend verify endpoint (no hardcoded domain)
			verify_path = f"/api/auth/password/reset/verify?uid={uidb64}&token={token}"
			verify_url = request.build_absolute_uri(verify_path)
			# Email content
			subject = 'Reset your MedMind password'
			body = (
				'We received a request to reset your password.\n\n'
				f'Open this link to proceed (valid for {getattr(settings, "PASSWORD_RESET_TIMEOUT", 3600) / 60} minutes):\n'
				f'{verify_url}\n\n'
				'If you did not request this, you can ignore this email.'
			)
			try:
				send_mail(subject, body, settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER, [email], fail_silently=True)
			except Exception:
				pass
		except User.DoesNotExist:
			# Do not reveal non-existence
			pass

		return Response(response_payload, status=status.HTTP_200_OK)

	@action(detail=False, methods=['get'], url_path='password/reset/verify')
	def password_reset_verify(self, request):
		uidb64 = request.query_params.get('uid')
		token = request.query_params.get('token')
		if not uidb64 or not token:
			return Response({'detail': 'Missing uid or token.'}, status=status.HTTP_400_BAD_REQUEST)
		try:
			uid = urlsafe_base64_decode(uidb64).decode()
			user = User.objects.get(pk=uid)
			valid = PasswordResetTokenGenerator().check_token(user, token)
			# If HTML is requested, render a minimal reset form served by the backend
			wants_html = 'text/html' in request.META.get('HTTP_ACCEPT', '') or request.query_params.get('format') == 'html'
			if wants_html:
				if not valid:
					return HttpResponse('<h2>Invalid or expired link.</h2>', status=400)
				html = """
				<!doctype html>
				<html lang='en'>
				<head>
				  <meta charset='utf-8'>
				  <meta name='viewport' content='width=device-width, initial-scale=1'>
				  <title>Reset Password</title>
				  <style>
				    body {{ font-family: Arial, sans-serif; max-width: 420px; margin: 40px auto; padding: 0 16px; }}
				    form {{ display: flex; flex-direction: column; gap: 12px; }}
				    input[type=password], button {{ padding: 10px; font-size: 15px; }}
				    button {{ background: #2563eb; color: #fff; border: none; border-radius: 6px; cursor: pointer; }}
				    .msg {{ margin-top: 8px; font-size: 14px; }}
				  </style>
				</head>
				<body>
				  <h2>Reset your password</h2>
				  <form id='reset-form'>
				    <input type='hidden' id='uid' value='{uidb64}' />
				    <input type='hidden' id='token' value='{token}' />
				    <label>New password</label>
				    <input type='password' id='pw1' required minlength='8' />
				    <label>Confirm password</label>
				    <input type='password' id='pw2' required minlength='8' />
				    <button type='submit'>Change password</button>
				    <div class='msg' id='msg'></div>
				  </form>
				  <script>
				  const form = document.getElementById('reset-form');
				  const msg = document.getElementById('msg');
				  form.addEventListener('submit', async (e) => {{
				    e.preventDefault();
				    const pw1 = document.getElementById('pw1').value;
				    const pw2 = document.getElementById('pw2').value;
				    if (pw1 !== pw2) {{ msg.textContent = 'Passwords do not match.'; msg.style.color = 'red'; return; }}
				    msg.textContent = 'Submitting...'; msg.style.color = '#444';
				    try {{
				      const resp = await fetch('/api/auth/password/reset/', {{
				        method: 'POST',
				        headers: {{ 'Content-Type': 'application/json' }},
				        body: JSON.stringify({{ uid: document.getElementById('uid').value, token: document.getElementById('token').value, new_password: pw1 }})
				      }});
				      const data = await resp.json();
				      if (resp.ok) {{ msg.textContent = data.detail || 'Password reset successful.'; msg.style.color = 'green'; }}
				      else {{ msg.textContent = data.detail || 'Unable to reset password.'; msg.style.color = 'red'; }}
				    }} catch(err) {{
				      msg.textContent = 'Network error. Please try again.';
				      msg.style.color = 'red';
				    }}
				  }});
				  </script>
				</body>
				</html>
				""".format(uidb64=uidb64, token=token)
				return HttpResponse(html)
			return Response({'valid': bool(valid)}, status=status.HTTP_200_OK)
		except Exception:
			return Response({'valid': False}, status=status.HTTP_200_OK)

	@action(detail=False, methods=['post'], url_path='password/reset')
	def password_reset(self, request):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		uidb64 = serializer.validated_data['uid']
		token = serializer.validated_data['token']
		new_password = serializer.validated_data['new_password']

		try:
			uid = urlsafe_base64_decode(uidb64).decode()
			user = User.objects.get(pk=uid)
			if not PasswordResetTokenGenerator().check_token(user, token):
				return Response({'detail': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
			user.set_password(new_password)
			user.save(update_fields=['password'])
			# Optional: mark doctor as logged out
			profile = getattr(user, 'doctor_profile', None)
			if profile:
				profile.logged_in = False
				profile.save(update_fields=['logged_in'])
			return Response({'detail': 'Password reset successful.'}, status=status.HTTP_200_OK)
		except User.DoesNotExist:
			return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
		except Exception:
			return Response({'detail': 'Unable to reset password.'}, status=status.HTTP_400_BAD_REQUEST)
