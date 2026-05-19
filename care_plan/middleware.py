from django.http import JsonResponse

from .exceptions import BaseAppException


class AppExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, BaseAppException):
            return JsonResponse(exception.to_dict(), status=exception.http_status)

        # DRF ValidationError 兼容：DRF 未安装时安全跳过
        try:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            if isinstance(exception, DRFValidationError):
                return JsonResponse({
                    "type": "validation_error",
                    "code": "VALIDATION_FAILED",
                    "message": "Validation failed",
                    "detail": exception.detail,
                    "http_status": 400,
                }, status=400)
        except ImportError:
            pass

        return None  # 其他异常交给 Django 默认处理
