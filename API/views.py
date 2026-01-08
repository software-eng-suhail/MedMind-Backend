from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import connection, DatabaseError


class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        status_report = {'database': 'ok'}
        try:
            connection.ensure_connection()
        except DatabaseError as exc:
            status_report['database'] = f'error: {exc}'

        is_healthy = all(v == 'ok' for v in status_report.values())
        http_status = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response({'status': 'ok' if is_healthy else 'degraded', **status_report}, status=http_status)

