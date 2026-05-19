"""
Unit tests for care_plan/middleware.py
验证自定义 exception → JSON response 的转换
"""
import json

import pytest
from django.test import RequestFactory

from care_plan.exceptions import BlockError, ValidationError, WarningException
from care_plan.middleware import AppExceptionMiddleware

pytestmark = pytest.mark.unit


@pytest.fixture
def middleware():
    return AppExceptionMiddleware(get_response=lambda r: 'passthrough')


@pytest.fixture
def fake_request():
    return RequestFactory().get('/')


class TestProcessException:

    def test_block_error_returns_409(self, middleware, fake_request):
        exc = BlockError(code='BLOCKED', message='cannot proceed')
        response = middleware.process_exception(fake_request, exc)
        assert response.status_code == 409
        data = json.loads(response.content)
        assert data['type'] == 'block_error'
        assert data['code'] == 'BLOCKED'

    def test_validation_error_returns_400(self, middleware, fake_request):
        exc = ValidationError(code='BAD', message='invalid input')
        response = middleware.process_exception(fake_request, exc)
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['type'] == 'validation_error'

    def test_warning_returns_200(self, middleware, fake_request):
        exc = WarningException(code='WARN', message='check this', detail={'hint': 'confirm'})
        response = middleware.process_exception(fake_request, exc)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['type'] == 'warning'
        assert data['detail'] == {'hint': 'confirm'}

    def test_non_app_exception_returns_none(self, middleware, fake_request):
        exc = ValueError('unhandled')
        response = middleware.process_exception(fake_request, exc)
        assert response is None

    def test_runtime_error_returns_none(self, middleware, fake_request):
        exc = RuntimeError('crash')
        assert middleware.process_exception(fake_request, exc) is None


class TestCallPassthrough:

    def test_normal_request_passes_through(self):
        sentinel = object()
        mw = AppExceptionMiddleware(get_response=lambda r: sentinel)
        result = mw(RequestFactory().get('/'))
        assert result is sentinel
