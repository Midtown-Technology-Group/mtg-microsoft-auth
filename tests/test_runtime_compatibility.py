"""Runtime compatibility checks without authentication or cache access."""

import enum
import importlib
import json
import pkgutil

import pytest

import mtg_microsoft_auth
from mtg_microsoft_auth import AuthConfig, AuthMode


@pytest.mark.parametrize(
    "name,value",
    [
        ("AUTO", "auto"),
        ("AZURE_CLI", "azure-cli"),
        ("WAM", "wam"),
        ("INTERACTIVE", "interactive"),
        ("DEVICE_CODE", "device-code"),
    ],
)
def test_auth_mode_string_contract(name, value):
    mode = AuthMode[name]
    assert isinstance(mode, str)
    assert mode.value == value
    assert mode == value
    assert hash(mode) == hash(value)
    assert {mode: "selected"}[value] == "selected"
    assert AuthMode(value) is mode
    assert str(mode) == value
    assert f"{mode}" == value
    assert format(mode, ">20") == format(value, ">20")
    assert repr(mode) == f"<AuthMode.{name}: {value!r}>"
    assert json.dumps(mode) == json.dumps(value)
    assert json.dumps({mode: mode}) == json.dumps({value: value})

    config = AuthConfig(
        client_id="11111111-1111-1111-1111-111111111111",
        tenant_id="22222222-2222-2222-2222-222222222222",
        scopes=["User.Read"],
        mode=value,
    )
    assert config.mode is mode
    assert config.model_dump()["mode"] is mode
    assert config.model_dump(mode="json")["mode"] == value
    assert json.loads(config.model_dump_json())["mode"] == value
    assert AuthConfig.model_validate_json(config.model_dump_json()).mode is mode

    # Compare against the original base class where the interpreter provides it.
    if hasattr(enum, "StrEnum"):
        reference = enum.StrEnum("AuthMode", {name: value})[name]
        assert str(mode) == str(reference)
        assert repr(mode) == repr(reference)
        assert format(mode, ">20") == format(reference, ">20")
        assert mode == reference


def test_all_package_modules_import():
    for module in pkgutil.walk_packages(
        mtg_microsoft_auth.__path__, mtg_microsoft_auth.__name__ + "."
    ):
        importlib.import_module(module.name)


def test_cli_help_does_not_authenticate(monkeypatch, capsys):
    from mtg_microsoft_auth import cli

    def unexpected_session(*args, **kwargs):
        pytest.fail("CLI help must not initialize authentication or a cache")

    monkeypatch.setattr(cli, "GraphAuthSession", unexpected_session)
    with pytest.raises(SystemExit) as result:
        cli.main(["--help"])
    assert result.value.code == 0
    assert "login" in capsys.readouterr().out
