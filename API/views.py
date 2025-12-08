from rest_framework import permissions, viewsets, serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.conf import settings
import os

try:
    import torch
    from PIL import Image
    from torchvision import transforms
except Exception:
    torch = None

from AI_Engine.models import AIModel, ImageResult
from AI_Engine.serializers import ImageResultReadSerializer

# Cached model + type ('ultralytics' or 'torch')
_MODEL_CACHE = None
_MODEL_TYPE = None

def _load_model(path):
    """Load model from path. Prefer ultralytics.YOLO, otherwise attempt safe torch.load.

    Returns (model, model_type) where model_type is 'ultralytics' or 'torch'.
    Raises exception if load fails.
    """
    global _MODEL_CACHE, _MODEL_TYPE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE, _MODEL_TYPE

    # Try ultralytics loader first (recommended)
    try:
        from ultralytics import YOLO
        m = YOLO(path)
        _MODEL_CACHE = m
        _MODEL_TYPE = 'ultralytics'
        return _MODEL_CACHE, _MODEL_TYPE
    except Exception:
        pass

    # Try torch safe globals path if torch is available
    if torch is None:
        raise RuntimeError('Torch is not available in this environment.')

    # Attempt to allowlist ultralytics DetectionModel if ultralytics is importable
    try:
        import ultralytics
        try:
            from torch.serialization import safe_globals
            with safe_globals([ultralytics.nn.tasks.DetectionModel]):
                m = torch.load(path, map_location='cpu', weights_only=False)
        except Exception:
            # Fall back to load without safe_globals (only if trusted)
            m = torch.load(path, map_location='cpu', weights_only=False)

        try:
            m.eval()
        except Exception:
            pass

        _MODEL_CACHE = m
        _MODEL_TYPE = 'torch'
        return _MODEL_CACHE, _MODEL_TYPE
    except Exception as exc:
        raise RuntimeError(f'Failed to load model: {exc}')

from user.serializers import DoctorSerializer, DoctorWriteSerializer, AdminSerializer, AdminWriteSerializer
from user.models import User

# app imports
from AI_Engine.models import ImageSample, ImageResult
from AI_Engine.serializers import ImageSampleSerializer, ImageResultReadSerializer, ImageResultWriteSerializer
from biopsy_result.models import BiopsyResult
from biopsy_result.serializers import BiopsyResultSerializer
from checkup.models import SkinCancerCheckup
from checkup.serializers import (
    SkinCancerCheckupSerializer,
    SkinCancerCreateSerializer,
)



class DoctorViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(role=User.Role.DOCTOR).select_related('doctor_profile')
    permission_classes = [permissions.AllowAny]
    lookup_field = 'username'
    lookup_value_regex = '[^/]+'

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return DoctorWriteSerializer
        return DoctorSerializer

    def perform_destroy(self, instance):
        try:
            instance.doctor_profile.delete()
        except Exception:
            pass
        instance.delete()



class AdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(role=User.Role.ADMIN).select_related('admin_profile')
    permission_classes = [permissions.AllowAny]
    lookup_field = 'username'
    lookup_value_regex = '[^/]+'

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AdminWriteSerializer
        return AdminSerializer

    def perform_destroy(self, instance):
        try:
            instance.admin_profile.delete()
        except Exception:
            pass
        instance.delete()


class SkinCancerCheckupViewSet(viewsets.ModelViewSet):
    queryset = SkinCancerCheckup.objects.all().select_related('doctor')
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == 'create':
            return SkinCancerCreateSerializer
        return SkinCancerCheckupSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        with transaction.atomic():
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()

            # Attach files directly from request.FILES for robust handling across clients.
            files = request.FILES.getlist('images')
            if files:
                from django.contrib.contenttypes.models import ContentType
                ct = ContentType.objects.get_for_model(instance)
                for f in files:
                    ImageSample.objects.create(content_type=ct, object_id=instance.pk, image=f)

        out = SkinCancerCheckupSerializer(instance, context=self.get_serializer_context()).data
        headers = self.get_success_headers(out)
        return Response(out, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['get', 'post'], url_path='infer', permission_classes=[permissions.AllowAny])
    def infer(self, request, pk=None):
        """Run inference for images attached to this checkup.

        POST body may include `image_id` to run on a single ImageSample; otherwise all samples are processed.
        """
        checkup = self.get_object()
        # Accept image_id from POST body or GET query params
        if request.method == 'POST':
            image_id = request.data.get('image_id') or request.query_params.get('image_id')
        else:
            image_id = request.query_params.get('image_id')
        samples = checkup.image_samples.all()
        if image_id:
            samples = samples.filter(pk=image_id)

        if not samples.exists():
            return Response({'detail': 'No image samples found for this checkup.'}, status=status.HTTP_400_BAD_REQUEST)

        model_path = getattr(settings, 'AI_MODEL_PATH', None) or os.path.join(settings.BASE_DIR, 'AI.pt')
        try:
            model, model_type = _load_model(model_path)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Preprocess for raw torch models
        preprocess = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        created_results = []
        for s in samples:
            try:
                if model_type == 'ultralytics':
                    # ultralytics YOLO predict API
                    try:
                        res = model.predict(source=s.image.path)
                    except TypeError:
                        # fallback to calling the model directly
                        res = model(s.image.path)

                    # Try to extract first-class and confidence from results
                    label = None
                    confidence = 0.0
                    try:
                        r0 = res[0] if hasattr(res, '__len__') else res
                        boxes = getattr(r0, 'boxes', None)
                        if boxes is not None and len(boxes) > 0:
                            cls = getattr(boxes, 'cls', None)
                            conf = getattr(boxes, 'conf', None)
                            if cls is not None:
                                first = cls[0]
                                label = str(int(first.item())) if hasattr(first, 'item') else str(first)
                            if conf is not None:
                                firstc = conf[0]
                                confidence = float(firstc.item()) if hasattr(firstc, 'item') else float(firstc)
                    except Exception:
                        pass

                    result_text = label if label is not None else str(res)
                else:
                    # raw torch model path
                    img = Image.open(s.image.path).convert('RGB')
                    tensor = preprocess(img).unsqueeze(0)
                    with torch.no_grad():
                        out = model(tensor)
                        if isinstance(out, torch.Tensor):
                            probs = torch.nn.functional.softmax(out, dim=1)
                            conf, idx = probs.max(dim=1)
                            confidence = float(conf.item())
                            label_idx = int(idx.item())
                            result_text = f'label_{label_idx}'
                        else:
                            result_text = str(out)
                            confidence = 0.0

                # If this is a POST request, persist the ImageResult; if GET, return prediction only
                if request.method == 'POST':
                    ir = ImageResult.objects.create(
                        image_sample=s,
                        result=result_text,
                        model=AIModel.MODEL_A,
                        confidence=confidence,
                    )
                    created_results.append(ir)
                else:
                    created_results.append({
                        'image_sample': s.pk,
                        'result': result_text,
                        'model': AIModel.MODEL_A,
                        'confidence': confidence,
                    })
            except Exception as e:
                created_results.append({'image_sample': s.pk, 'error': str(e)})

        # Serialize created results
        serialized = []
        for r in created_results:
            if isinstance(r, dict):
                serialized.append(r)
            else:
                serialized.append(ImageResultReadSerializer(r).data)

        return Response({'results': serialized}, status=status.HTTP_200_OK)

class ImageSampleViewSet(viewsets.ModelViewSet):
    queryset = ImageSample.objects.select_related('content_type')
    permission_classes = [permissions.AllowAny]
    serializer_class = ImageSampleSerializer

    def perform_create(self, serializer):
        # Validator: max 5 images per checkup (check by content_type + object_id)
        ct = serializer.validated_data.get('content_type')
        object_id = serializer.validated_data.get('object_id')
        if ct and object_id:
            from django.contrib.contenttypes.models import ContentType
            # `ct` may be a ContentType instance or an app_label.model string handled in serializer
            if not isinstance(ct, ContentType):
                try:
                    app_label, model = str(ct).split('.')
                    ct = ContentType.objects.get(app_label=app_label, model=model)
                except Exception:
                    ct = None

            if ct is not None:
                existing = ImageSample.objects.filter(content_type=ct, object_id=object_id).count()
                if existing >= 5:
                    raise serializers.ValidationError('A maximum of 5 images is allowed per checkup.')

        serializer.save()


class ImageResultViewSet(viewsets.ModelViewSet):
    queryset = ImageResult.objects.select_related('image_sample')
    permission_classes = [permissions.AllowAny]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ImageResultWriteSerializer
        return ImageResultReadSerializer


class BiopsyResultViewSet(viewsets.ModelViewSet):
    queryset = BiopsyResult.objects.select_related('checkup', 'verified_by')
    permission_classes = [permissions.AllowAny]
    serializer_class = BiopsyResultSerializer
