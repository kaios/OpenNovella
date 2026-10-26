import pytest

from opennovella.expressions import (ExpressionError, check_expression, evaluate, interpolate,
                                     names_in, parse_value, run_statements)


def test_basic_comparisons():
    v = {"courage": 3, "name": "Sam", "met": True}
    assert evaluate("courage >= 3", v) is True
    assert evaluate("courage > 3 or met", v) is True
    assert evaluate('name == "Sam" and not met', v) is False
    assert evaluate("1 < courage < 5", v) is True


def test_friendly_spellings():
    assert evaluate("true && !false") is True
    assert evaluate("yes || no") is True
    assert evaluate('x == "Hi!"', {"x": "Hi!"}) is True  # "!" inside quotes untouched


def test_unknown_variables_are_zero_unless_strict():
    assert evaluate("missing + 1") == 1
    with pytest.raises(ExpressionError):
        evaluate("missing", strict=True)


def test_unsafe_code_is_rejected():
    for bad in ("__import__('os')", "open('x')", "().__class__", "[x for x in y]", "lambda: 1"):
        with pytest.raises(ExpressionError):
            evaluate(bad)
    with pytest.raises(ExpressionError):
        evaluate("2 ** 100000")


def test_check_expression():
    assert check_expression("courage >= 2") is None
    assert check_expression("courage >=") is not None
    assert check_expression("print(1)") is not None


def test_parse_value():
    assert parse_value("3") == 3
    assert parse_value("true") is True
    assert parse_value('"Sam"') == "Sam"
    assert parse_value("Sam") == "Sam"          # bare word becomes text
    assert parse_value("gold * 2", {"gold": 4}) == 8


def test_run_statements():
    v = {"courage": 1}
    run_statements("courage += 2; met_bob = true; name = \"Ann\"", v)
    assert v == {"courage": 3, "met_bob": True, "name": "Ann"}
    with pytest.raises(ExpressionError):
        run_statements("courage == 2", v)


def test_interpolate():
    v = {"name": "Sam", "gold": 5.0, "ok": True}
    assert interpolate("Hi {name}, you have {gold} gold ({ok})", v) == "Hi Sam, you have 5 gold (true)"
    assert interpolate("{{literal}} {unknown}", v) == "{literal} {unknown}"


def test_names_in():
    assert names_in("courage >= max(2, bonus) and true") == {"courage", "bonus"}
