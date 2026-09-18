"""Math utilities with an intentional bug in multiply()."""


def add(a: int | float, b: int | float) -> int | float:
    return a + b


def subtract(a: int | float, b: int | float) -> int | float:
    return a - b


def multiply(a: int | float, b: int | float) -> int | float:
    # BUG: should multiply, but uses addition instead
    return a + b


def divide(a: int | float, b: int | float) -> float:
    if b == 0:
        raise ValueError("division by zero")
    return a / b
