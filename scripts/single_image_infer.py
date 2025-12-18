#!/usr/bin/env python3
"""
Single-image prediction script for the EfficientNet-based skin lesion classifier.

This mirrors the original author's test script behavior:
- Loads a Keras/TensorFlow model (.h5)
- Loads and resizes the input image to 224x224
- Optional: artifact removal (morphological closing)
- Optional: segmentation (k-means based)
- Runs `model.predict` and prints malignant probability + label

Usage:
  python scripts/single_image_infer.py --image example_images/WEB06875.jpg \
      --model models/efficientnetb0_nosegmentation_noartifactremoval.h5 \
      [--segment] [--remove-artifacts]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import cv2

# Prefer tf.keras to match runtime; fall back to keras if needed.
try:
    import tensorflow as tf  # noqa: F401
    from tensorflow import keras
except Exception:
    import keras  # type: ignore


def load_image(filename: str) -> np.ndarray:
    img = cv2.imread(filename)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {filename}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def apply_morpho_closing(image: np.ndarray, disk_size: int = 4) -> np.ndarray:
    # Minimal dependency-free approximation using cv2 morphology (close) per channel
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (disk_size, disk_size))
    r = cv2.morphologyEx(image[..., 0], cv2.MORPH_CLOSE, kernel)
    g = cv2.morphologyEx(image[..., 1], cv2.MORPH_CLOSE, kernel)
    b = cv2.morphologyEx(image[..., 2], cv2.MORPH_CLOSE, kernel)
    return np.stack((r, g, b), axis=-1)


def kmeans_mask(image: np.ndarray) -> np.ndarray:
    K = 2
    Z = image.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(Z, K, None, criteria, 1, cv2.KMEANS_RANDOM_CENTERS)
    centers = np.uint8(centers)
    lesion_cluster = int(np.argmin(np.mean(centers, axis=1)))
    lesion_mask = labels.flatten() == lesion_cluster
    return lesion_mask


def kmeans_segmentation(
    image: np.ndarray, force_copy: bool = True, mask: np.ndarray | None = None
) -> np.ndarray:
    lesion_mask = mask if mask is not None else kmeans_mask(image)
    segmented_img = image.reshape((-1, 3))
    if force_copy and segmented_img.base is image:
        segmented_img = segmented_img.copy()
    segmented_img[~lesion_mask] = 255
    return segmented_img.reshape(image.shape)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Image to evaluate", type=str)
    parser.add_argument(
        "--model", required=True, help="Model (.h5) to use for classification", type=str
    )
    parser.add_argument(
        "--segment", action="store_true", help="Segment the image before classification"
    )
    parser.add_argument(
        "--remove-artifacts",
        action="store_true",
        help="Apply morphological closing before classification",
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    model_path = Path(args.model)
    if not image_path.exists():
        print(f"Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)
    if not model_path.exists():
        print(f"Model not found: {model_path}", file=sys.stderr)
        sys.exit(1)

    print("Loading model...")
    # Use compile=False to avoid optimizer/loss deserialization issues; also allow DepthwiseConv2D shim if needed.
    model = keras.models.load_model(str(model_path), compile=False)

    print("Loading image...")
    input_shape = (224, 224, 3)
    image = cv2.resize(load_image(str(image_path)), input_shape[:2])

    if args.remove_artifacts:
        image = apply_morpho_closing(image, disk_size=1)

    if args.segment:
        image = kmeans_segmentation(image, force_copy=False)

    # Prepare batch
    # IMPORTANT: Match training scale. The original training code fed uint8 (0-255) arrays
    # directly to the model without dividing by 255 or using EfficientNet preprocess.
    # To be consistent, do NOT normalize here.
    batch = image[np.newaxis].astype(np.float32)

    # Some saved models expect multiple inputs; if so, replicate the same tensor.
    num_inputs = len(model.inputs) if isinstance(model.inputs, (list, tuple)) else 1
    model_input = [batch] * num_inputs if num_inputs > 1 else batch

    prediction = float(np.ravel(model.predict(model_input))[0])
    label = "Benign" if prediction < 0.5 else "Malignant"
    print(f"{label} (malignant probability: {prediction:.2%})")


if __name__ == "__main__":
    main()
