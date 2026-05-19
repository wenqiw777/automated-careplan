"""
Unit tests for care_plan/exceptions.py
验证每种 exception 的 http_status、type、to_dict() 输出
"""
import pytest

from care_plan.exceptions import BaseAppException, BlockError, ValidationError, WarningException

pytestmark = pytest.mark.unit


class TestBaseAppException:

    def test_to_dict_full(self):
        exc = BaseAppException(code='TEST_CODE', message='Something broke', detail={'key': 'val'})
        d = exc.to_dict()
        assert d == {
            'type': 'error',
            'code': 'TEST_CODE',
            'message': 'Something broke',
            'detail': {'key': 'val'},
            'http_status': 500,
        }

    def test_to_dict_no_detail(self):
        exc = BaseAppException(code='BARE', message='no detail')
        assert exc.to_dict()['detail'] is None

    def test_inherits_from_exception(self):
        exc = BaseAppException(code='X', message='msg')
        assert isinstance(exc, Exception)
        assert str(exc) == 'msg'


class TestValidationError:

    def test_status_and_type(self):
        exc = ValidationError(code='BAD_INPUT', message='invalid')
        assert exc.http_status == 400
        assert exc.type == 'validation_error'

    def test_to_dict(self):
        exc = ValidationError(code='MISSING', message='field required', detail='name')
        d = exc.to_dict()
        assert d['http_status'] == 400
        assert d['type'] == 'validation_error'
        assert d['detail'] == 'name'


class TestBlockError:

    def test_status_and_type(self):
        exc = BlockError(code='BLOCKED', message='not allowed')
        assert exc.http_status == 409
        assert exc.type == 'block_error'

    def test_to_dict(self):
        exc = BlockError(code='DUP', message='duplicate', detail={'id': 1})
        d = exc.to_dict()
        assert d['http_status'] == 409
        assert d['type'] == 'block_error'


class TestWarningException:

    def test_status_and_type(self):
        exc = WarningException(code='WARN', message='heads up')
        assert exc.http_status == 200
        assert exc.type == 'warning'

    def test_to_dict(self):
        exc = WarningException(code='CHECK', message='please confirm', detail={'hint': 'confirm=true'})
        d = exc.to_dict()
        assert d['http_status'] == 200
        assert d['type'] == 'warning'
        assert d['detail'] == {'hint': 'confirm=true'}
