import offthemes
from offpunk import GeminiClient


def test_set_prompt():
    gc = GeminiClient()

    prompt_value = "ON"
    prompt = gc.set_prompt(prompt_value)

    # Default prompt should be green 32 and go back to default 39
    assert prompt == format_prompt("32", "39", prompt_value)


# Prompt should still be green if nothing is set
def test_set_prompt_without_themes(mocker):
    mocker.patch("offthemes.offpunk1", {})
    mocker.patch("offthemes.colors", {})
    gc = GeminiClient()

    prompt_value = "ON"
    prompt = gc.set_prompt(prompt_value)

    # Default prompt should be green 32 and go back to default 39
    assert prompt == format_prompt("32", "39", prompt_value)


# Prompt should still be green if nothing is set
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
