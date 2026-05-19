class BaseAppException(Exception):
    http_status: int = 500
    type: str = "error"

    def __init__(self, code: str, message: str, detail=None):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)

    def to_dict(self):
        return {
            "type": self.type,
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "http_status": self.http_status,
        }


class ValidationError(BaseAppException):
    """用户输入格式不对 → 400"""
    http_status = 400
    type = "validation_error"


class BlockError(BaseAppException):
    """业务规则阻止，无法继续 → 409"""
    http_status = 409
    type = "block_error"


class WarningException(BaseAppException):
    """可能有问题，需要用户确认 → 200 + type=warning"""
    http_status = 200
    type = "warning"
