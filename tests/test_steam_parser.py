import pytest
from app.steam import parse_steam_input


def test_parse_valid_steamid64():
    input_val = "76561198012345678"
    mode, identifier = parse_steam_input(input_val)
    assert mode == "steamid64"
    assert identifier == "76561198012345678"


def test_parse_profile_url():
    url = "https://steamcommunity.com/profiles/76561198012345678"
    mode, identifier = parse_steam_input(url)
    assert mode == "steamid64"
    assert identifier == "76561198012345678"


def test_parse_profile_url_with_trailing_slash_and_http():
    url = "http://steamcommunity.com/profiles/76561198012345678/"
    mode, identifier = parse_steam_input(url)
    assert mode == "steamid64"
    assert identifier == "76561198012345678"


def test_parse_vanity_url():
    url = "https://steamcommunity.com/id/gabelogannewell/"
    mode, identifier = parse_steam_input(url)
    assert mode == "vanity"
    assert identifier == "gabelogannewell"


def test_parse_vanity_no_scheme():
    url = "steamcommunity.com/id/gaben"
    mode, identifier = parse_steam_input(url)
    assert mode == "vanity"
    assert identifier == "gaben"


def test_parse_plain_vanity_name():
    name = "gaben_valve"
    mode, identifier = parse_steam_input(name)
    assert mode == "vanity"
    assert identifier == "gaben_valve"


def test_parse_prefixed_vanity():
    name = "id/gaben_valve"
    mode, identifier = parse_steam_input(name)
    assert mode == "vanity"
    assert identifier == "gaben_valve"


def test_parse_empty_input():
    with pytest.raises(ValueError):
        parse_steam_input("")


def test_parse_invalid_format():
    with pytest.raises(ValueError):
        parse_steam_input("https://google.com/malicious/path?attack=1")
