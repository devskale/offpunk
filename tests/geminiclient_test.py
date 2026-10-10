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


class TestListAddTop:
    """Test the behavior of the `GeminiClient.list_add_top()` method."""

    def setup_method(self):
        self.gc = GeminiClient()

    @pytest.fixture(autouse=True)
    def install_mocks(self, mocker: "MockerFixture"):
        # Mocks for controlling what the method reads from the list and checking what it
        # writes to the list.
        self.mock_list_read = mocker.MagicMock()
        self.mock_list_write = mocker.MagicMock()

        def mock_open(file, mode):
            if mode == "r":
                return mocker.mock_open(read_data=self.mock_list_read)(file, mode)
            elif mode == "w":
                return mocker.mock_open(self.mock_list_write)(file, mode)
            else:
                raise TypeError(f"Unhandled open call: open({file!r}, {mode!r})")

        # Mocks to isolate tests from the real file system
        mocker.patch("offpunk.open", mock_open)
        mocker.patch.object(self.gc, "list_create")
        mocker.patch.object(self.gc, "list_path")

        # Mock dynamic values
        mocker.patch("offpunk.time.ctime", return_value=str(mocker.sentinel.ctime))
        mocker.patch.object(self.gc, "current_url", str(mocker.sentinel.current_url))
        mocker.patch.object(
            self.gc,
            "get_renderer",
            return_value=mocker.MagicMock(
                **{
                    "get_page_title.return_value": str(
                        mocker.sentinel.current_url_title
                    )
                }
            ),
        )

    def test_limit(self, mocker: "MockerFixture"):
        """
        Test that the `limit` argument limits the maximum number of entries in the list.
        """
        self.mock_list_read = (
            f"=> {mocker.sentinel.url1} {mocker.sentinel.title1}\n"
            f"=> {mocker.sentinel.url2} {mocker.sentinel.title2}\n"
            f"=> {mocker.sentinel.url3} {mocker.sentinel.title3}\n"
            f"=> {mocker.sentinel.url4} {mocker.sentinel.title4}\n"
            f"=> {mocker.sentinel.url5} {mocker.sentinel.title5}\n"
        )
        self.gc.list_add_top(str(mocker.sentinel.list_name), limit=5)

        # sentinel.url5 has been bumped off the list to make room for the new entry.
        self.mock_list_write.assert_has_calls(
            [
                mocker.call().write("#sentinel.list_name\n"),
                mocker.call().write(
                    "=> sentinel.current_url sentinel.current_url_title, "
                    "added to sentinel.list_name on sentinel.ctime\n"
                ),
                mocker.call().write("=> sentinel.url1 sentinel.title1\n"),
                mocker.call().write("=> sentinel.url2 sentinel.title2\n"),
                mocker.call().write("=> sentinel.url3 sentinel.title3\n"),
                mocker.call().write("=> sentinel.url4 sentinel.title4\n"),
                mocker.call().close(),
            ]
        )

    def test_truncate_lines(self, mocker: "MockerFixture"):
        """
        Test that the `truncate_lines` argument removes a given number of existing items
        in the list from the top.
        """
        self.mock_list_read = (
            f"=> {mocker.sentinel.url1} {mocker.sentinel.title1}\n"
            f"=> {mocker.sentinel.url2} {mocker.sentinel.title2}\n"
            f"=> {mocker.sentinel.url3} {mocker.sentinel.title3}\n"
            f"=> {mocker.sentinel.url4} {mocker.sentinel.title4}\n"
            f"=> {mocker.sentinel.url5} {mocker.sentinel.title5}\n"
        )
        self.gc.list_add_top(str(mocker.sentinel.list_name), truncate_lines=2)

        # url1 and url2 have been removed by truncation after the new entry.
        self.mock_list_write.assert_has_calls(
            [
                mocker.call().write("#sentinel.list_name\n"),
                mocker.call().write(
                    "=> sentinel.current_url sentinel.current_url_title, "
                    "added to sentinel.list_name on sentinel.ctime\n"
                ),
                mocker.call().write("=> sentinel.url3 sentinel.title3\n"),
                mocker.call().write("=> sentinel.url4 sentinel.title4\n"),
                mocker.call().write("=> sentinel.url5 sentinel.title5\n"),
                mocker.call().close(),
            ]
        )


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
