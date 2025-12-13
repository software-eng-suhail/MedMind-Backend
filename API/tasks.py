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

from AI_Engine.models import ImageSample, ImageResult, AIModel
from checkup.models import SkinCancerCheckup

# Module-level model cache
_MODEL_EFFICIENTNET = None


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
    arr = np.asarray(img).astype('float32') / 255.0
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
    except Exception as e:
        logger.exception('Failed to load models')
        raise

    # Mark checkup in-progress
    try:
        checkup = SkinCancerCheckup.objects.get(pk=checkup_id)
    except SkinCancerCheckup.DoesNotExist:
        raise Exception(f'Checkup {checkup_id} does not exist')

    checkup.status = 'IN_PROGRESS'
    checkup.started_at = timezone.now()
    # Record the worker task id
    try:
        checkup.task_id = str(self.request.id)
    except Exception:
        pass
    checkup.save(update_fields=['status', 'started_at', 'task_id'])

    # Query samples for this checkup
    samples = ImageSample.objects.filter(content_type__model__icontains='skincancercheckup', object_id=checkup_id)
    if not samples.exists():
        # mark failed and exit
        checkup.status = 'FAILED'
        checkup.error_message = 'No image samples found for checkup'
        checkup.completed_at = timezone.now()
        checkup.save(update_fields=['status', 'error_message', 'completed_at'])
        return {'result_ids': []}

    created_result_ids = []
    total = samples.count()
    processed = 0

    for s in samples:
        processed += 1
        try:

            # Preprocess for EfficientNet (expects ~224x224, normalized to [0,1])
            arr = _preprocess_image(s.image.path, target_size=(224, 224))

            # Run the single model (EfficientNet). Handle both scalar and
            # multiclass outputs conservatively.
            self.update_state(state='PROGRESS', meta={'progress': int(100 * (processed-1) / max(total,1)), 'step': 'inference'})
            preds = model.predict(arr)

            # Interpret predictions:
            # - If preds is vector (multiclass), pick argmax and its probability.
            # - If preds is scalar-like (binary), use threshold 0.5 for label.
            if getattr(preds, 'ndim', 0) > 1 and np.ravel(preds).size > 1:
                probs = np.ravel(preds)[0:len(np.ravel(preds))]
                idx = int(np.argmax(probs))
                prob_val = float(probs[idx])
                label = f'class_{idx}'
            else:
                prob_val = float(np.ravel(preds)[0])
                label = 'Malignant' if prob_val >= 0.5 else 'Benign'

            # Remove previous EfficientNet result for this sample (avoid duplicates on re-run)
            ImageResult.objects.filter(image_sample=s, model=AIModel.EFFICIENTNET).delete()
            # Persist the result atomically (single model)
            with transaction.atomic():
                ir = ImageResult.objects.create(
                    image_sample=s,
                    result=label,
                    model=AIModel.EFFICIENTNET,
                    confidence=prob_val,
                )

            created_result_ids.append(ir.id)
        except Exception as exc:
            logger.exception('Inference failed for sample %s', s.pk)
            # continue with next sample
            continue

    # Mark checkup completed
    checkup.status = 'COMPLETED'
    checkup.completed_at = timezone.now()
    checkup.save(update_fields=['status', 'completed_at'])

    self.update_state(state='SUCCESS', meta={'result_ids': created_result_ids})
    return {'result_ids': created_result_ids}
    


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
        checkup.status = 'IN_PROGRESS'
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
    except Exception:
        logger.exception('Inference failed for sample %s', s.pk)
        if checkup:
            checkup.status = 'FAILED'
            checkup.error_message = 'Inference failed for a sample'
            checkup.completed_at = timezone.now()
            checkup.save(update_fields=['status', 'error_message', 'completed_at'])
        raise

    # Set checkup completed
    if checkup:
        checkup.status = 'COMPLETED'
        checkup.completed_at = timezone.now()
        checkup.save(update_fields=['status', 'completed_at'])

    return {'result_id': ir.id}
    


