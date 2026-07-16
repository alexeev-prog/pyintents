# tests/test_exceptions.py

from pyintents.exceptions import IntentViolationError


class TestIntentViolationError:
    def test_error_creation(self):
        error = IntentViolationError("test_func", "os.system")
        assert error.func_name == "test_func"
        assert error.violation == "os.system"
        assert str(error) == "Function 'test_func' calls forbidden 'os.system'"

    def test_error_with_different_values(self):
        error = IntentViolationError("outer", "inner")
        assert error.func_name == "outer"
        assert error.violation == "inner"
        assert str(error) == "Function 'outer' calls forbidden 'inner'"

    def test_error_inheritance(self):
        error = IntentViolationError("func", "print")
        assert isinstance(error, Exception)
        assert isinstance(error, IntentViolationError)
