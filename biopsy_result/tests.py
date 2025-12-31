from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from biopsy_result.models import BiopsyResult, BiopsyResultStatus
from checkup.models import SkinCancerCheckup
from user.models import User, AdminProfile, DoctorProfile


class BiopsyResultVerifyActionTests(TestCase):
	def setUp(self):
		self.client = APIClient()

		# Create admin user
		self.admin = User.objects.create_user(
			username='admin1',
			email='admin1@example.com',
			password='adminpass',
			role=User.Role.ADMIN,
		)
		AdminProfile.objects.get_or_create(user=self.admin)

		# Create doctor user
		self.doctor = User.objects.create_user(
			username='doc1',
			email='doc1@example.com',
			password='docpass',
			role=User.Role.DOCTOR,
		)
		self.doctor_profile, _ = DoctorProfile.objects.get_or_create(user=self.doctor)

		# Create a skin cancer checkup
		self.checkup = SkinCancerCheckup.objects.create(
			age=40,
			gender='male',
			blood_type='O+',
			note='test note',
			doctor=self.doctor,
			lesion_size_mm=5.0,
			lesion_location='arm',
			asymmetry=True,
			border_irregularity=False,
			color_variation=True,
			diameter_mm=6.0,
			evolution=False,
		)

		# Create a biopsy result linked to the checkup
		ct = ContentType.objects.get_for_model(self.checkup)
		self.biopsy = BiopsyResult.objects.create(
			content_type=ct,
			object_id=self.checkup.id,
			result='Pending review',
			document=SimpleUploadedFile('report.txt', b'report'),
			status=BiopsyResultStatus.PENDING,
			credits_refunded=False,
		)

	def test_verify_biopsy_result_refunds_credits_and_sets_verifier(self):
		start_credits = self.doctor_profile.credits

		self.client.force_authenticate(user=self.admin)
		url = f'/api/biopsy-results/{self.biopsy.id}/verify/'
		resp = self.client.post(url)

		self.assertEqual(resp.status_code, 200)

		# Refresh from DB
		self.biopsy.refresh_from_db()
		self.doctor_profile.refresh_from_db()

		self.assertEqual(self.biopsy.status, BiopsyResultStatus.VERIFIED)
		self.assertEqual(self.biopsy.verified_by, self.admin)
		self.assertTrue(self.biopsy.credits_refunded)
		self.assertEqual(self.doctor_profile.credits, start_credits + 100)
