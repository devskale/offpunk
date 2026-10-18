from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

import offthemes
from ansicat import GemtextRenderer
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
        mock_renderer = mocker.MagicMock(
            **{"get_page_title.return_value": str(mocker.sentinel.current_url_title)}
        )
        mocker.patch.object(self.gc, "get_renderer", return_value=mock_renderer)

    def test_short_timeout(self, mocker: "MockerFixture"):
        """Test short_timeout affects the timeout for requests."""
        assert (
            self.gc.options["short_timeout"] == 5
        ), "Unexpected default value for short_timeout."
        self.gc.do_set("short_timeout 30")
        assert (
            self.gc.options["short_timeout"] == 30
        ), "short_timeout wasn't set to the expected value."
        mock_fetch = mocker.patch("offpunk.netcache.fetch")
        self.gc.sync_only = True
        self.gc.do_go("http://localhost")
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.kwargs["timeout"] == 30

    def test_width(self):
        """Test setting the width option affects the content display width."""
        assert self.gc.options["width"] == 72, "Unexpected default value for width."

        self.gc.do_set("width 20")
        assert self.gc.options["width"] == 20, "width wasn't set to the expected value."

        # Width is stored in a global `offutils.TERM_WIDTH` variable, which is
        # indirectly referenced by other classes like `GemtextRenderer`.
        unwrapped_text = (
            "Whereas recognition of the inherent dignity and of the equal and "
            "inalienable rights of all members of the human family is the foundation "
            "of freedom, justice and peace in the world"
        )
        wrapped_text = GemtextRenderer(unwrapped_text, "http://localhost").get_body()
        assert dedent(wrapped_text) == (
            "Whereas recognition\n"
            "of the inherent\n"
            "dignity and of the\n"
            "equal and\n"
            "inalienable rights\n"
            "of all members of\n"
            "the human family is\n"
            "the foundation of\n"
            "freedom, justice and\n"
            "peace in the world\n"
        ), "The gemtext wasn't wrapped at the expected line length."

    def test_archives_size(self, mocker: "MockerFixture"):
        """
        Test setting the archives_size option affects how many archive entries can be
        stored.
        """
        assert (
            self.gc.options["archives_size"] == 200
        ), "Unexpected default value for archives_size."
        self.gc.do_set("archives_size 10")
        assert (
            self.gc.options["archives_size"] == 10
        ), "archives_size wasn't set to the expected value."

        self.mock_list_read = (
            "=> url01 Title 01\n"
            "=> url02 Title 02\n"
            "=> url03 Title 03\n"
            "=> url04 Title 04\n"
            "=> url05 Title 05\n"
            "=> url06 Title 06\n"
            "=> url07 Title 07\n"
            "=> url08 Title 08\n"
            "=> url09 Title 09\n"
            "=> url10 Title 10"
        )
        self.gc.do_archive(None)

        # Demonstrate that url10 was bumped off the list by the new url.
        self.mock_list_write.assert_has_calls(
            [
                mocker.call().__enter__(),
                mocker.call().write("#archives\n"),
                mocker.call().write(
                    "=> sentinel.current_url sentinel.current_url_title, archived on sentinel.ctime\n"
                ),
                mocker.call().write("=> url01 Title 01\n"),
                mocker.call().write("=> url02 Title 02\n"),
                mocker.call().write("=> url03 Title 03\n"),
                mocker.call().write("=> url04 Title 04\n"),
                mocker.call().write("=> url05 Title 05\n"),
                mocker.call().write("=> url06 Title 06\n"),
                mocker.call().write("=> url07 Title 07\n"),
                mocker.call().write("=> url08 Title 08\n"),
                mocker.call().write("=> url09 Title 09\n"),
                mocker.call().close(),
                mocker.call().__exit__(None, None, None),
            ]
        )

    def test_history_size(self, mocker: "MockerFixture"):
        """
        Test setting the history_size option affects how many history entries can be
        stored.
        """
        assert (
            self.gc.options["history_size"] == 200
        ), "Unexpected default value for history_size."
        self.gc.do_set("history_size 10")
        assert (
            self.gc.options["history_size"] == 10
        ), "history_size wasn't set to the expected value."

        # Prevent network access
        mocker.patch.object(
            self.gc, "opencache", **{"openk.return_value": (True, "http://localhost/")}
        )
        self.mock_list_read = (
            "=> url01 Title 01\n"
            "=> url02 Title 02\n"
            "=> url03 Title 03\n"
            "=> url04 Title 04\n"
            "=> url05 Title 05\n"
            "=> url06 Title 06\n"
            "=> url07 Title 07\n"
            "=> url08 Title 08\n"
            "=> url09 Title 09\n"
            "=> url10 Title 10"
        )
        self.gc.do_go("http://localhost/")

        # Demonstrate that url10 was bumped off the list by the new url.
        self.mock_list_write.assert_has_calls(
            [
                mocker.call().__enter__(),
                mocker.call().write("#history\n"),
                mocker.call().write(
                    "=> http://localhost/ sentinel.current_url_title, visited on sentinel.ctime\n"
                ),
                mocker.call().write("=> url01 Title 01\n"),
                mocker.call().write("=> url02 Title 02\n"),
                mocker.call().write("=> url03 Title 03\n"),
                mocker.call().write("=> url04 Title 04\n"),
                mocker.call().write("=> url05 Title 05\n"),
                mocker.call().write("=> url06 Title 06\n"),
                mocker.call().write("=> url07 Title 07\n"),
                mocker.call().write("=> url08 Title 08\n"),
                mocker.call().write("=> url09 Title 09\n"),
                mocker.call().close(),
                mocker.call().__exit__(None, None, None),
            ]
        )

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
        assert (
            self.gc.options["accept_bad_ssl_certificates"] is False
        ), "Unexpected default value for accept_bad_ssl_certificates."
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
