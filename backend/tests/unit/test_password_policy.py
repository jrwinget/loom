import pytest
from pydantic import ValidationError

from loom.schemas.user import UserCreate


def test_password_minimum_length_12():
    """reject passwords shorter than 12 characters."""
    with pytest.raises(ValidationError):
        UserCreate(
            email="a@b.com",
            display_name="Test",
            password="Short1Abc",
        )


def test_password_requires_uppercase():
    """reject passwords without uppercase letters."""
    with pytest.raises(ValidationError):
        UserCreate(
            email="a@b.com",
            display_name="Test",
            password="alllowercase1",
        )


def test_password_requires_lowercase():
    """reject passwords without lowercase letters."""
    with pytest.raises(ValidationError):
        UserCreate(
            email="a@b.com",
            display_name="Test",
            password="ALLUPPERCASE1",
        )


def test_password_requires_digit():
    """reject passwords without digits."""
    with pytest.raises(ValidationError):
        UserCreate(
            email="a@b.com",
            display_name="Test",
            password="NoDigitsHereX",
        )


def test_valid_password_accepted():
    """accept a password meeting all requirements."""
    user = UserCreate(
        email="a@b.com",
        display_name="Test",
        password="ValidPass123",
    )
    assert user.password == "ValidPass123"
