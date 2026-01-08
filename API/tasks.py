from __future__ import annotations

import logging
import io
import os
from pathlib import Path
from typing import List, Any

import numpy as np
from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.utils import timezone
import matplotlib.cm as cm

from AI_Engine.models import AIModel, ImageResult, ImageSample
from checkup.models import CheckupStatus, SkinCancerCheckup

logger = logging.getLogger(__name__)


# Model configuration
MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path(__file__).resolve().parent.parent / "models"))
MODEL_FILENAME = os.environ.get("MODEL_FILENAME", "best_model.keras")
MODEL_PATH = Path(os.environ.get("MODEL_PATH", MODEL_DIR / MODEL_FILENAME))
IMG_SIZE = int(os.environ.get("MODEL_IMG_SIZE", 224))
ENABLE_MIXED_PRECISION = os.environ.get("ENABLE_MIXED_PRECISION", "1") == "1"
_MODEL = None  # cached loaded model
_TF = None  # cached tensorflow module (lazy import)


def _tf():
    """Lazy-load TensorFlow to keep web container light."""
    global _TF
    if _TF is None:
        import tensorflow as tf  # type: ignore
        _TF = tf
    return _TF


def _maybe_enable_mixed_precision(tf):
    """Optionally enable mixed_float16 to match training policies."""
    if ENABLE_MIXED_PRECISION:
        tf.keras.mixed_precision.set_global_policy("mixed_float16")
        logger.info("Enabled mixed_float16 policy for inference")


def _build_inference_model(tf):
    """Build the EfficientNetB0 inference model matching the training head."""
    base = tf.keras.applications.EfficientNetB0(
        include_top=False,
        weights=None,
        input_shape=(IMG_SIZE, IMG_SIZE, 3),
    )
    inputs = tf.keras.Input(shape=(IMG_SIZE, IMG_SIZE, 3))
    x = base(inputs, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", dtype="float32")(x)
    return tf.keras.Model(inputs, outputs)


def _load_with_patched_dense(tf, path: Path):
    """Attempt to load a model while tolerating a 'quantization_config' key in Dense."""
    class PatchedDense(tf.keras.layers.Dense):
        def __init__(self, *args, quantization_config=None, **kwargs):  # noqa: D401
            super().__init__(*args, **kwargs)

    custom_objects = {"Dense": PatchedDense}
    # safe_mode=False allows unknown symbols in the V3 format
    return tf.keras.models.load_model(str(path), compile=False, custom_objects=custom_objects, safe_mode=False)

def _load_model():
    """Load and cache the TensorFlow model."""
    global _MODEL
    if _MODEL is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Model file not found at {MODEL_PATH}")
        tf = _tf()
        logger.info("Loading model from %s", MODEL_PATH)
        if MODEL_PATH.is_dir():
            _MODEL = tf.keras.models.load_model(str(MODEL_PATH), compile=False)
            return _MODEL

        ext = MODEL_PATH.suffix.lower()
        if ext in {".keras", ".h5", ".hdf5"}:
            loaders = [
                lambda: _load_with_patched_dense(tf, MODEL_PATH),
                lambda: tf.keras.models.load_model(str(MODEL_PATH), compile=False),
            ]
            for loader in loaders:
                try:
                    _MODEL = loader()
                    break
                except Exception:  # pragma: no cover - loader failure
                    _MODEL = None
            if _MODEL is None:
                _maybe_enable_mixed_precision(tf)
                model = _build_inference_model(tf)
                try:
                    model.load_weights(str(MODEL_PATH))
                except Exception as err:
                    raise ValueError("Unable to load model or weights from the provided artifact") from err
                _MODEL = model
            return _MODEL

        # Weight-only artifacts (e.g., saved as plain weights without recognized extension)
        _maybe_enable_mixed_precision(tf)
        model = _build_inference_model(tf)
        try:
            model.load_weights(str(MODEL_PATH))
        except Exception as err:
            raise ValueError("Unsupported model artifact or failed to load weights") from err
        _MODEL = model
    return _MODEL


def _prepare_image(img_path: str) -> np.ndarray:
    """Load and preprocess an image for EfficientNet inference."""
    tf = _tf()
    img = tf.keras.utils.load_img(img_path, target_size=(IMG_SIZE, IMG_SIZE))
    arr = tf.keras.utils.img_to_array(img)
    arr = tf.keras.applications.efficientnet.preprocess_input(arr)
    return np.expand_dims(arr, axis=0)


def _get_gradcam_layers(model: Any):
    """Fetch backbone, GAP, dropout, and head layers matching the training notebook."""
    backbone = model.get_layer("efficientnetb0")
    gap_layer = model.get_layer("global_average_pooling2d")
    drop_layer = model.get_layer("dropout")
    head_layer = model.get_layer("dense")
    return backbone, gap_layer, drop_layer, head_layer


def _make_gradcam_heatmap_image(model: Any, img_path: str) -> bytes | None:
    """Compute Grad-CAM using the training notebook recipe and return the standalone heatmap PNG bytes."""
    tf = _tf()
    try:
        backbone, gap_layer, drop_layer, head_layer = _get_gradcam_layers(model)
    except Exception as e:
        logger.warning("Grad-CAM layer lookup failed: %s", e)
        return None

    # Preprocess like training (resize 224, preprocess_input, float32)
    img = tf.keras.preprocessing.image.load_img(img_path, target_size=(IMG_SIZE, IMG_SIZE))
    img_array = tf.keras.preprocessing.image.img_to_array(img)
    img_array = tf.keras.applications.efficientnet.preprocess_input(img_array)
    img_tensor = tf.convert_to_tensor(img_array[None, ...], dtype=tf.float32)

    with tf.GradientTape() as tape:
        conv_outputs = backbone(img_tensor, training=False)
        tape.watch(conv_outputs)
        x = gap_layer(conv_outputs)
        x = drop_layer(x, training=False)
        preds = head_layer(x)
        loss = preds[:, 0]

    grads = tape.gradient(loss, conv_outputs)
    if grads is None:
        return None
    grads = tf.cast(grads, tf.float32)
    conv_outputs = tf.cast(conv_outputs, tf.float32)

    pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))
    conv_outputs = conv_outputs[0]
    heatmap = tf.reduce_sum(conv_outputs * pooled_grads, axis=-1)
    heatmap = tf.maximum(heatmap, 0)
    # Normalize to [0,1]
    denom = tf.reduce_max(heatmap) + 1e-8
    heatmap = heatmap / denom
    # Resize heatmap to original image resolution for visualization
    orig = tf.keras.preprocessing.image.load_img(img_path)
    orig_arr = tf.keras.preprocessing.image.img_to_array(orig)
    heatmap = tf.image.resize(heatmap[..., None], (orig_arr.shape[0], orig_arr.shape[1]), method="bicubic")
    heatmap = tf.squeeze(heatmap, axis=-1)
    heatmap = tf.clip_by_value(heatmap, 0.0, 1.0)
    heatmap_np = heatmap.numpy()

    # Apply jet colormap to create RGB heatmap (no overlay)
    heatmap_uint8 = np.uint8(255 * heatmap_np)
    cmap = cm.get_cmap("jet")
    colors = cmap(np.arange(256))[:, :3]
    color_heatmap = colors[heatmap_uint8]

    heatmap_img = tf.keras.preprocessing.image.array_to_img(color_heatmap)
    buf = io.BytesIO()
    heatmap_img.save(buf, format="PNG")
    return buf.getvalue()


def _predict_image(model: Any, img_path: str) -> float:
    """Return the malignant probability for a single image."""
    batch = _prepare_image(img_path)
    # Model outputs a single sigmoid value
    pred = model.predict(batch, verbose=0)
    score = float(np.squeeze(pred))
    if not np.isfinite(score):
        raise ValueError("Non-finite prediction score; model likely not loaded with compatible weights")
    # clamp to [0,1] just in case
    if score < 0.0:
        score = 0.0
    elif score > 1.0:
        score = 1.0
    return score


def _label_for_score(score: float) -> str:
    return "Malignant" if score >= 0.5 else "Benign"


@shared_task(bind=True, name="api.run_inference_for_checkup")
def run_inference_for_checkup(self, checkup_id: int):
    """Run inference for all images attached to the given checkup.

    - Loads the fine-tuned EfficientNet model once per worker.
    - Writes an ImageResult per ImageSample.
    - Updates the SkinCancerCheckup with aggregate result and confidence.
    """

    try:
        checkup = SkinCancerCheckup.objects.get(pk=checkup_id)
    except SkinCancerCheckup.DoesNotExist:
        logger.error("Checkup %s does not exist", checkup_id)
        return

    # Mark as in progress
    checkup.status = CheckupStatus.IN_PROGRESS
    checkup.started_at = timezone.now()
    checkup.error_message = None
    checkup.save(update_fields=["status", "started_at", "error_message"])

    try:
        model = _load_model()

        ct = ContentType.objects.get_for_model(checkup)
        samples: List[ImageSample] = list(ImageSample.objects.filter(content_type=ct, object_id=checkup.pk))
        if not samples:
            raise ValueError("No images found for this checkup")

        scores: List[float] = []

        # Remove any previous results to avoid duplicates on reruns
        ImageResult.objects.filter(image_sample__in=[s.pk for s in samples]).delete()

        for sample in samples:
            score = _predict_image(model, sample.image.path)
            scores.append(score)
            # Generate Grad-CAM heatmap (standalone) using training notebook recipe
            try:
                png_bytes = _make_gradcam_heatmap_image(model, sample.image.path)
            except Exception as xai_exc:
                logger.warning("Grad-CAM generation failed for sample %s: %s", sample.pk, xai_exc)
                png_bytes = None

            # Create ImageResult and attach XAI image if available
            result_obj = ImageResult.objects.create(
                image_sample=sample,
                result=_label_for_score(score),
                model=AIModel.EFFICIENTNET,
                confidence=score,
            )
            if png_bytes:
                filename = f"checkup_{checkup.pk}_sample_{sample.pk}.png"
                result_obj.xai_image.save(filename, ContentFile(png_bytes), save=True)

        avg_score = float(np.mean(scores)) if scores else 0.0
        checkup.result = _label_for_score(avg_score)
        checkup.final_confidence = avg_score
        checkup.status = CheckupStatus.COMPLETED
        checkup.completed_at = timezone.now()
        checkup.image_count = len(samples)
        checkup.save(update_fields=[
            "result",
            "final_confidence",
            "status",
            "completed_at",
            "image_count",
        ])
        logger.info("Inference complete for checkup %s: result=%s score=%.4f", checkup.pk, checkup.result, avg_score)

    except Exception as exc:
        logger.exception("Inference failed for checkup %s", checkup_id)
        checkup.status = CheckupStatus.FAILED
        checkup.error_message = str(exc)
        checkup.completed_at = timezone.now()
        # Refund once per checkup using failure_refund flag to avoid double refunds on retries
        doctor_profile = getattr(checkup.doctor, "doctor_profile", None)
        if doctor_profile and not getattr(checkup, "failure_refund", False):
            doctor_profile.credits = doctor_profile.credits + 100
            doctor_profile.save(update_fields=["credits"])
            checkup.failure_refund = True
        checkup.save(update_fields=["status", "error_message", "completed_at", "failure_refund"])
        raise
