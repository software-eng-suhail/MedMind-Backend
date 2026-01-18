from celery import shared_task
from django.conf import settings
from django.db import transaction
from pathlib import Path
import numpy as np
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

# Do NOT import Keras/TensorFlow at module import time. Import lazily in _load_keras_model() / _preprocess_image().

from AI_Engine.models import AIModel, ImageResult, ImageSample
from checkup.models import CheckupStatus, SkinCancerCheckup

# Module-level model cache
_MODEL_EFFICIENTNET = None
MAX_RETRIES = getattr(settings, 'CELERY_TASK_MAX_RETRIES', 3)

# Inference settings (match training)
IMG_SIZE = 224
BATCH_SIZE = 32
THRESHOLD = 0.5


def _load_keras_model():
    """Lazily load and cache the EfficientNet Keras model."""
    global _MODEL_EFFICIENTNET
    if _MODEL_EFFICIENTNET is None:
        try:
            # Import here to avoid requiring TensorFlow in environments that don't run inference.
            from keras.models import load_model
        except Exception:
            raise
        path_b = getattr(settings, 'MODEL_B_PATH', None) or Path(settings.BASE_DIR) / 'models' / 'efficientnetb0_nosegmentation_noartifactremoval.h5'
        _MODEL_EFFICIENTNET = load_model(str(path_b), compile=False)
    return _MODEL_EFFICIENTNET


def _preprocess_image(path, target_size=(IMG_SIZE, IMG_SIZE)):
    """
    Preprocess EXACTLY like training:
      tf.io.read_file -> tf.image.decode_jpeg(channels=3) -> resize -> float32 -> efficientnet.preprocess_input
    Returns a NumPy batch of shape (1, H, W, 3) suitable for model.predict.
    """
    try:
        import tensorflow as tf
        from tensorflow.keras.applications.efficientnet import preprocess_input
    except Exception:
        raise

    img = tf.io.read_file(path)
    img = tf.image.decode_jpeg(img, channels=3)
    img = tf.image.resize(img, target_size)
    img = tf.cast(img, tf.float32)
    img = preprocess_input(img)  # IMPORTANT: matches training
    img = tf.expand_dims(img, axis=0)
    return img.numpy()


def _pred_to_label_and_conf(preds):
    """
    Convert model output to (label, confidence).
    - If output is (1,2) softmax: choose argmax, confidence = max prob, label uses class names.
    - Else sigmoid-like: confidence = prob, label by THRESHOLD.
    """
    flat = np.ravel(preds)

    # softmax / multi-class
    if getattr(preds, 'ndim', 0) == 2 and preds.shape[1] and preds.shape[1] > 1:
        probs = flat[: preds.shape[1]]
        idx = int(np.argmax(probs))
        prob_val = float(probs[idx])
        # If you have a real mapping, replace this:
        label = f'class_{idx}'
        return label, prob_val

    # binary sigmoid-like
    prob_val = float(flat[0]) if flat.size else 0.0
    label = 'Malignant' if prob_val >= THRESHOLD else 'Benign'
    return label, prob_val


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
                arr = _preprocess_image(sample.image.path, target_size=(IMG_SIZE, IMG_SIZE))
                self.update_state(
                    state='PROGRESS',
                    meta={'progress': int(100 * (processed - 1) / max(total, 1)), 'step': 'inference'}
                )

                # Force inference mode (safer for long-lived workers)
                try:
                    preds = model(arr, training=False).numpy()
                except Exception:
                    preds = model.predict(arr, verbose=0)

                label, prob_val = _pred_to_label_and_conf(preds)

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

        results = ImageResult.objects.filter(
            image_sample__content_type__model__icontains='skincancercheckup',
            image_sample__object_id=checkup_id
        )

        if results.exists():
            confidences = [r.confidence for r in results if r.confidence is not None]
            if confidences:
                checkup.final_confidence = max(confidences)
                avg_confidence = sum(confidences) / len(confidences)
                checkup.result = 'Malignant' if avg_confidence > 0.70 else 'Benign'
                checkup.save(update_fields=['final_confidence', 'result'])

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
    except Exception:
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
        arr = _preprocess_image(s.image.path, target_size=(IMG_SIZE, IMG_SIZE))

        # Force inference mode (safer for long-lived workers)
        try:
            preds = model(arr, training=False).numpy()
        except Exception:
            preds = model.predict(arr, verbose=0)

        label, prob_val = _pred_to_label_and_conf(preds)

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
