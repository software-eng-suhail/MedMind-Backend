from django.test import TestCase
from rest_framework.test import APIClient
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch
import io
from PIL import Image
from user.models import User


def make_test_image_bytes(fmt='PNG', size=(100, 100), color=(255, 0, 0)):
	b = io.BytesIO()
	img = Image.new('RGB', size, color)
	img.save(b, format=fmt)
	b.seek(0)
	return b


class APIAuthAndCheckupTests(TestCase):
	def setUp(self):
		self.client = APIClient()

	def test_doctor_signup_and_login(self):
		signup_url = '/api/auth/signup/doctor/'
		data = {
			'username': 'drsmith',
			'email': 'drsmith@example.com',
			'password': 'testpass123',
		}
		r = self.client.post(signup_url, data, format='json')
		self.assertEqual(r.status_code, 201)
		self.assertIn('access', r.data)
		self.assertIn('refresh', r.data)

		login_url = '/api/auth/login/'
		r2 = self.client.post(login_url, {'username': 'drsmith', 'password': 'testpass123'}, format='json')
		self.assertEqual(r2.status_code, 200)
		self.assertIn('access', r2.data)

	def test_create_checkup_and_inference_enqueued(self):
		# create doctor via model
		doctor = User.objects.create_user(username='drjones', email='drjones@example.com', password='testpass', role=User.Role.DOCTOR)
		# login
		login_url = '/api/auth/login/'
		r = self.client.post(login_url, {'username': 'drjones', 'password': 'testpass'}, format='json')
		token = r.data['access']
		self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

		# prepare image
		img_bytes = make_test_image_bytes()
		img_file = SimpleUploadedFile('test.png', img_bytes.read(), content_type='image/png')

		payload = {
			'age': 50,
			'gender': 'male',
			'doctor': doctor.pk,
			'lesion_location': 'arm',
			'lesion_size_mm': 5.0,
			'blood_type': 'A',
			'diameter_mm': 10.0,
			'images': [img_file],
		}

		# Avoid importing the real API.tasks module (which may import TensorFlow).
		from types import SimpleNamespace
		# Create a mock tasks module that has a callable task with delay attribute
		mock_run = type('T', (), {'delay': lambda *a, **k: SimpleNamespace(id='mock-task-id')})
		with patch.dict('sys.modules', {'API.tasks': SimpleNamespace(run_inference_for_checkup=mock_run)}):
			r2 = self.client.post('/api/skin-cancer-checkups/', data=payload, format='multipart')
			# If create fails the assertion below will report and fail the test.
			self.assertEqual(r2.status_code, 201)

		# list checkups
		r3 = self.client.get('/api/skin-cancer-checkups/')
		self.assertEqual(r3.status_code, 200)

	def test_create_checkup_handles_broker_down_gracefully(self):
		# create doctor via model
		doctor = User.objects.create_user(username='drjones2', email='drjones2@example.com', password='testpass', role=User.Role.DOCTOR)
		# login
		login_url = '/api/auth/login/'
		r = self.client.post(login_url, {'username': 'drjones2', 'password': 'testpass'}, format='json')
		token = r.data['access']
		self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

		# prepare image
		img_bytes = make_test_image_bytes()
		img_file = SimpleUploadedFile('test.png', img_bytes.read(), content_type='image/png')

		payload = {
			'age': 50,
			'gender': 'male',
			'doctor': doctor.pk,
			'lesion_location': 'arm',
			'lesion_size_mm': 5.0,
			'blood_type': 'A',
			'diameter_mm': 10.0,
			'images': [img_file],
		}

		# Simulate broker down: replace API.tasks.run_inference_for_checkup with object whose delay raises.
		from types import SimpleNamespace
		def bad_delay(*a, **k):
			raise Exception('Broker down')
		bad_run = SimpleNamespace(delay=bad_delay)
		with patch.dict('sys.modules', {'API.tasks': SimpleNamespace(run_inference_for_checkup=bad_run)}):
			r2 = self.client.post('/api/skin-cancer-checkups/', data=payload, format='multipart')
			self.assertEqual(r2.status_code, 201)
			self.assertFalse(r2.data.get('_task_queued', True))

	def test_checkup_detail_returns_images_and_results(self):
		# create doctor
		doctor = User.objects.create_user(username='drwho', email='drwho@example.com', password='testpass', role=User.Role.DOCTOR)
		# Create checkup directly via serializer or model
		from checkup.models import SkinCancerCheckup
		c = SkinCancerCheckup.objects.create(
			age=40,
			gender='female',
			blood_type='O',
			doctor=doctor,
			lesion_size_mm=4.0,
			lesion_location='leg',
			asymmetry=False,
			border_irregularity=False,
			color_variation=False,
			diameter_mm=6.0,
			evolution=False,
		)

		# add an ImageSample
		from django.contrib.contenttypes.models import ContentType
		from AI_Engine.models import ImageSample, ImageResult, AIModel
		ct = ContentType.objects.get_for_model(c)
		# create sample image file
		img_bytes = make_test_image_bytes()
		img_file = SimpleUploadedFile('test.png', img_bytes.read(), content_type='image/png')
		s = ImageSample.objects.create(content_type=ct, object_id=c.pk, image=img_file)

		# add a result
		ImageResult.objects.create(image_sample=s, result='Malignant', model=AIModel.EFFICIENTNET, confidence=0.95)

		# get detail
		r = self.client.get(f'/api/skin-cancer-checkups/{c.pk}/')
		self.assertEqual(r.status_code, 200)
		data = r.json()
		self.assertIn('doctor', data)
		self.assertIn('image_samples', data)
		self.assertTrue(len(data['image_samples']) >= 1)
		self.assertIn('result', data['image_samples'][0])
