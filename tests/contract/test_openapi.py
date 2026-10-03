from pathlib import Path

import yaml
from openapi_spec_validator import validate

CONTRACT = Path(__file__).resolve().parents[2] / "contract" / "openapi-v1.yaml"


def test_contract_is_valid_openapi() -> None:
    validate(yaml.safe_load(CONTRACT.read_text(encoding="utf-8")))


def test_contract_declares_v1_paths() -> None:
    document = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert set(document["paths"]) == {"/api/v1/health", "/api/v1/catalog", "/api/v1/selections"}
