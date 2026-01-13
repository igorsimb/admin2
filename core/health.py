from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views import View
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError


class HealthCheckView(View):
    def get(self, request, *args, **kwargs):
        # Check database
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_status = True
        except Exception:
            db_status = False

        # Check Redis
        try:
            redis_conn = Redis.from_url(settings.CELERY_BROKER_URL)
            redis_status = redis_conn.ping()
        except (RedisConnectionError, ValueError):
            redis_status = False

        status = 200 if all([db_status, redis_status]) else 503

        return JsonResponse(
            {
                "status": "ok" if status == 200 else "error",
                "database": "ok" if db_status else "error",
                "redis": "ok" if redis_status else "error",
            },
            status=status,
        )
