from typing import TYPE_CHECKING

import pytest

import offthemes
from offpunk import GeminiClient

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_set_prompt():
    gc = GeminiClient()

    prompt_value = "ON"
    prompt = gc.set_prompt(prompt_value)

    # Default prompt should be yellow 33 and go back to default 39
    assert prompt == format_prompt("33", "39", prompt_value)


# Prompt should still be yellow if nothing is set
def test_set_prompt_without_themes(mocker):
    mocker.patch("offthemes.offpunk1", {})
    mocker.patch("offthemes.colors", {})
    gc = GeminiClient()

    prompt_value = "ON"
    prompt = gc.set_prompt(prompt_value)

    # Default prompt should be yellow 33 and go back to default 39
    assert prompt == format_prompt("33", "39", prompt_value)


# Prompt should still be yellow if nothing is set
def test_set_prompt_without_themes(mocker):
    new_theme = offthemes.default.copy()
    new_theme["prompt_on"] = ["blue"]

    mocker.patch("offthemes.default", new_theme)

    gc = GeminiClient()

    prompt_value = "ON"
    prompt = gc.set_prompt(prompt_value)

    # Default prompt should be green 32 and go back to default 39
    assert prompt == format_prompt("34", "39", prompt_value)


def format_prompt(open_color: str, close_color: str, prompt_value: str) -> str:
    return (
        "\001\x1b[%sm\002" % open_color
        + prompt_value
        + "\001\x1b[%sm\002" % close_color
        + "> "
    )


def test_complete_view(mocker: "MockerFixture"):
    """
    Test the `GeminiClient.complete_view()` method returns valid command arguments.
    """
    # Track `GeminiClient._go_to_url()` to determine if the `GeminiClient.do_view()`
    # call was successful.
    gc = GeminiClient()
    gc.current_url = "localhost"
    mock_go_to_url = mocker.patch.object(gc, "_go_to_url")

    results = gc.complete_view("", None, None, None)
    assert results, "At least one argument should be suggested from an empty string."
    for arg in results:
        gc.do_view(arg)
        assert mock_go_to_url.call_count == 1, (
            f"{arg!r} isn't a valid argument for the view command "
            "(GeminiClient._go_to_url() was't called)."
        )
        mock_go_to_url.reset_mock()

    # Test partial matches
    test_cases = [
        ("s", ["source", "switch"]),
        ("so", ["source"]),
        ("zz", []),
    ]
    for line, expected_suggestions in test_cases:
        assert gc.complete_view(line, None, None, None) == expected_suggestions


class TestDoSet:
    """Test the `GeminiClient.do_set()` method can configure options."""

    def setup_method(self):
        self.gc = GeminiClient()

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
        ],
    )
    def test_accept_bad_ssl_certificates(
        self,
        value: str,
        expected: bool,
        mocker: "MockerFixture",
    ):
        """
        Test accept_bad_ssl_certificates accepts different forms of boolean, and is
        passed to `netcache.fetch` when visiting a page.
        """
        self.gc.do_set(f"accept_bad_ssl_certificates {value}")
        assert self.gc.options["accept_bad_ssl_certificates"] is expected, (
            f"Setting accept_bad_ssl_certificates to {value!r} "
            f"did not produce the expected result ({expected!r})."
        )
        mock_fetch = mocker.patch("offpunk.netcache.fetch")
        self.gc.sync_only = True
        self.gc.do_go("http://localhost")
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.args == ("http://localhost",)
        assert mock_fetch.call_args.kwargs["accept_bad_ssl_certificates"] is expected
