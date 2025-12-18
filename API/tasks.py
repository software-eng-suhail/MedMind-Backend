from celery import shared_task
from django.conf import settings
from django.db import transaction
from pathlib import Path
import numpy as np
from PIL import Image
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

# Do NOT import Keras/TensorFlow at module import time. Import lazily in _load_keras_model().

from AI_Engine.models import AIModel, ImageResult, ImageSample
from checkup.models import CheckupStatus, SkinCancerCheckup

# Module-level model cache
_MODEL_EFFICIENTNET = None
MAX_RETRIES = getattr(settings, 'CELERY_TASK_MAX_RETRIES', 3)


def _load_keras_model():
    """Lazily load and cache the EfficientNet Keras model."""
    global _MODEL_EFFICIENTNET
    if _MODEL_EFFICIENTNET is None:
        try:
            # Import here to avoid requiring TensorFlow in environments that don't run inference.
            from keras.models import load_model
        except Exception as e:
            # Re-raise to be caught by caller and logged; keeps module import safe for non-TF environments.
            raise
        path_b = getattr(settings, 'MODEL_B_PATH', None) or Path(settings.BASE_DIR) / 'models' / 'efficientnetb0_nosegmentation_noartifactremoval.h5'
        _MODEL_EFFICIENTNET = load_model(str(path_b))
    return _MODEL_EFFICIENTNET


def _preprocess_image(path, target_size=(224, 224)):
    img = Image.open(path).convert('RGB')
    img = img.resize(target_size)
    # Keep raw 0-255 scale to mirror the training pipeline (no normalization)
    arr = np.asarray(img).astype('float32')
    arr = np.expand_dims(arr, axis=0)
    return arr


@shared_task(bind=True)
def run_inference_for_checkup(self, checkup_id):
    """Run the EfficientNet Keras model on all ImageSample rows for a checkup.

    Creates an ImageResult per image and returns their ids.
    This task updates the checkup `status`, `started_at`, `completed_at`, and `task_id`.
    """
    try:
        model = _load_keras_model()

        # Mark checkup in-progress
        try:
            checkup = SkinCancerCheckup.objects.get(pk=checkup_id)
        except SkinCancerCheckup.DoesNotExist:
            # Non-retriable: bad input
            raise

        checkup.status = CheckupStatus.IN_PROGRESS
        checkup.started_at = timezone.now()
        try:
            checkup.task_id = str(self.request.id)
        except Exception:
            pass
        checkup.save(update_fields=['status', 'started_at', 'task_id'])

        samples = ImageSample.objects.filter(content_type__model__icontains='skincancercheckup', object_id=checkup_id)
        if not samples.exists():
            checkup.status = CheckupStatus.FAILED
            checkup.error_message = 'No image samples found for checkup'
            checkup.completed_at = timezone.now()
            checkup.save(update_fields=['status', 'error_message', 'completed_at'])
            return {'result_ids': []}

        created_result_ids = []
        total = samples.count()
        processed = 0

        for sample in samples:
            processed += 1
            try:
                arr = _preprocess_image(sample.image.path, target_size=(224, 224))
                self.update_state(state='PROGRESS', meta={'progress': int(100 * (processed - 1) / max(total, 1)), 'step': 'inference'})
                preds = model.predict(arr)

                if getattr(preds, 'ndim', 0) > 1 and np.ravel(preds).size > 1:
                    probs = np.ravel(preds)[: len(np.ravel(preds))]
                    idx = int(np.argmax(probs))
                    prob_val = float(probs[idx])
                    label = f'class_{idx}'
                else:
                    prob_val = float(np.ravel(preds)[0])
                    label = 'Malignant' if prob_val >= 0.5 else 'Benign'

                ImageResult.objects.filter(image_sample=sample, model=AIModel.EFFICIENTNET).delete()
                with transaction.atomic():
                    ir = ImageResult.objects.create(
                        image_sample=sample,
                        result=label,
                        model=AIModel.EFFICIENTNET,
                        confidence=prob_val,
                    )

                created_result_ids.append(ir.id)
            except Exception:
                logger.exception('Inference failed for sample %s', sample.pk)
                continue

        checkup.status = CheckupStatus.COMPLETED
        checkup.completed_at = timezone.now()
        checkup.save(update_fields=['status', 'completed_at'])

        self.update_state(state='SUCCESS', meta={'result_ids': created_result_ids})
        return {'result_ids': created_result_ids}
    except Exception as exc:
        try:
            checkup = SkinCancerCheckup.objects.get(pk=checkup_id)
            checkup.status = CheckupStatus.FAILED
            checkup.error_message = str(exc)
            checkup.completed_at = timezone.now()
            checkup.save(update_fields=['status', 'error_message', 'completed_at'])
        except SkinCancerCheckup.DoesNotExist:
            # Do not retry if the checkup itself is missing
            raise
        except Exception:
            pass

        if getattr(self.request, 'retries', 0) < MAX_RETRIES:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        raise
    


@shared_task(bind=True)
def run_inference_for_sample(self, sample_id):
    """Run the EfficientNet model for a single ImageSample.

    Deletes previous EfficientNet results for the sample and writes a new one.
    Updates the checkup status fields (IN_PROGRESS/COMPLETED) for the related checkup.
    """
    try:
        model = _load_keras_model()
    except Exception as e:
        logger.exception('Failed to load models')
        raise

    try:
        s = ImageSample.objects.get(pk=sample_id)
    except ImageSample.DoesNotExist:
        raise Exception(f'ImageSample {sample_id} does not exist')

    # set checkup to in-progress
    try:
        checkup = SkinCancerCheckup.objects.get(pk=s.object_id)
        checkup.status = CheckupStatus.IN_PROGRESS
        checkup.started_at = timezone.now()
        try:
            checkup.task_id = str(self.request.id)
        except Exception:
            pass
        checkup.save(update_fields=['status', 'started_at', 'task_id'])
    except Exception:
        checkup = None

    try:
        arr = _preprocess_image(s.image.path, target_size=(224, 224))
        preds = model.predict(arr)
        if getattr(preds, 'ndim', 0) > 1 and np.ravel(preds).size > 1:
            probs = np.ravel(preds)[0:len(np.ravel(preds))]
            idx = int(np.argmax(probs))
            prob_val = float(probs[idx])
            label = f'class_{idx}'
        else:
            prob_val = float(np.ravel(preds)[0])
            label = 'Malignant' if prob_val >= 0.5 else 'Benign'

        # delete previous EFFICIENTNET results for this sample
        ImageResult.objects.filter(image_sample=s, model=AIModel.EFFICIENTNET).delete()

        with transaction.atomic():
            ir = ImageResult.objects.create(
                image_sample=s,
                result=label,
                model=AIModel.EFFICIENTNET,
                confidence=prob_val,
            )
    except Exception as exc:
        logger.exception('Inference failed for sample %s', s.pk)
        if checkup:
            checkup.status = CheckupStatus.FAILED
            checkup.error_message = 'Inference failed for a sample'
            checkup.completed_at = timezone.now()
            checkup.save(update_fields=['status', 'error_message', 'completed_at'])
        if getattr(self.request, 'retries', 0) < MAX_RETRIES:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        raise

    # Set checkup completed
    if checkup:
        checkup.status = CheckupStatus.COMPLETED
        checkup.completed_at = timezone.now()
        checkup.save(update_fields=['status', 'completed_at'])

    return {'result_id': ir.id}
    


