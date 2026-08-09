from pathlib import Path

import pytest

from src.sandbox.sensitive import match


@pytest.mark.parametrize("path", [
    "C:/Users/me/.ssh/id_rsa",
    "C:/Users/me/.aws/credentials",
    "C:/code/app/.env.production",
    "C:/Windows/System32/drivers/etc/hosts",
    "/etc/hosts",
    "/home/me/.config/gcloud/application_default_credentials.json",
])
def test_sensitive_classes(path: str):
    assert match(Path(path))[0]


def test_normal_source_file_is_not_sensitive():
    assert match(Path("C:/code/app/main.py")) == (False, "")


def test_custom_sensitive_pattern():
    assert match(Path("C:/code/app/.npmrc"), custom_patterns=["*/.npmrc"])[0]
