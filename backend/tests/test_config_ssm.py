"""SSM Parameter Store settings source — no AWS calls, boto3.client is faked."""

import boto3
import pytest
from app.config import Settings

PREFIX = "/k-compliance/prod"


class FakeSSM:
    def __init__(self, params: dict[str, str]):
        self.params = params
        self.calls: list[dict] = []

    def get_paginator(self, name):
        assert name == "get_parameters_by_path"
        return self

    def paginate(self, **kwargs):
        self.calls.append(kwargs)
        yield {"Parameters": [{"Name": k, "Value": v} for k, v in self.params.items()]}


@pytest.fixture
def fake_ssm(monkeypatch):
    fake = FakeSSM(
        {
            f"{PREFIX}/JWT_SECRET_KEY": "jwt-from-ssm",
            f"{PREFIX}/ENCRYPTION_KEY": "enc-from-ssm",
            f"{PREFIX}/NOT_A_SETTING": "ignored",
        }
    )
    regions = []

    def client(service, region_name=None):
        assert service == "ssm"
        regions.append(region_name)
        return fake

    monkeypatch.setattr(boto3, "client", client)
    fake.regions = regions
    return fake


@pytest.fixture
def base_env(monkeypatch):
    for key in ("JWT_SECRET_KEY", "ENCRYPTION_KEY", "SSM_PARAMETER_PREFIX", "SSM_REGION"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u@localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://u@localhost/db")
    return monkeypatch


def test_secrets_loaded_from_ssm(base_env, fake_ssm):
    base_env.setenv("SSM_PARAMETER_PREFIX", PREFIX)
    base_env.setenv("SSM_REGION", "us-east-1")

    s = Settings(_env_file=None)

    assert s.JWT_SECRET_KEY == "jwt-from-ssm"
    assert s.ENCRYPTION_KEY == "enc-from-ssm"
    assert fake_ssm.calls == [{"Path": PREFIX + "/", "Recursive": False, "WithDecryption": True}]
    assert fake_ssm.regions == ["us-east-1"]


def test_env_overrides_ssm(base_env, fake_ssm):
    base_env.setenv("SSM_PARAMETER_PREFIX", PREFIX + "/")  # trailing slash tolerated
    base_env.setenv("JWT_SECRET_KEY", "jwt-from-env")

    s = Settings(_env_file=None)

    assert s.JWT_SECRET_KEY == "jwt-from-env"
    assert s.ENCRYPTION_KEY == "enc-from-ssm"
    assert fake_ssm.regions == ["ap-northeast-2"]


def test_no_prefix_skips_ssm(base_env, fake_ssm):
    base_env.setenv("JWT_SECRET_KEY", "jwt-from-env")
    base_env.setenv("ENCRYPTION_KEY", "enc-from-env")

    s = Settings(_env_file=None)

    assert s.JWT_SECRET_KEY == "jwt-from-env"
    assert fake_ssm.calls == []
