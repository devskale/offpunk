#!/usr/bin/env python3
# Following code has been originally written by Vincent Jousse - 2025.
# All credits to him

import argparse
import fileinput
import glob
import logging
import logging.config
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from urllib.parse import urlparse

from lxml import etree

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] [%(levelname)8s] [%(filename)s:%(lineno)s - %(funcName).20s…] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "default",
        }
    },
    "loggers": {"": {"handlers": ["stdout"], "level": "ERROR"}},
}


logging.config.dictConfig(LOGGING)


LOGGER = logging.getLogger(__name__)


def set_logging_level(level):
    LOGGING["loggers"][""]["level"] = level
    logging.config.dictConfig(LOGGING)


@dataclass
class Command:
    """Class for keeping track of a command item."""

    name: str
    accept_multiple_values: bool = False
    is_bool: bool = False
    xpath_value: bool = False
    has_capture_group: bool = False
    special_command: bool = False
    ignore: bool = False


COMMANDS: list[Command] = [
    Command("author", accept_multiple_values=True),
    Command("autodetect_on_failure", is_bool=True),
    Command("body", accept_multiple_values=True),
    Command("date", accept_multiple_values=True),
    Command("find_string", accept_multiple_values=True),
    Command("http_header", has_capture_group=True, special_command=True),
    Command("if_page_contains", special_command=True),
    Command("login_extra_fields", accept_multiple_values=True),
    Command("login_password_field"),
    Command("login_uri"),
    Command("login_username_field"),
    Command("native_ad_clue", accept_multiple_values=True),
    Command("next_page_link", accept_multiple_values=True),
    Command("not_logged_in_xpath"),
    Command("parser"),
    Command("prune", is_bool=True),
    Command("replace_string", has_capture_group=True, accept_multiple_values=True),
    Command("requires_login", is_bool=True),
    Command("src_lazy_load_attr"),
    Command("single_page_link", accept_multiple_values=True),
    Command("skip_json_ld", is_bool=True),
    Command("strip", accept_multiple_values=True),
    Command("strip_id_or_class", accept_multiple_values=True),
    Command("strip_image_src", accept_multiple_values=True),
    Command("test_contains", special_command=True),
    Command("test_url", accept_multiple_values=True, special_command=True),
    Command("tidy", is_bool=True),
    Command("title", accept_multiple_values=True),
    Command("wrap_in", has_capture_group=True, special_command=True),
]

COMMANDS_PER_NAME: dict[str, Command] = {
    COMMANDS[i].name: COMMANDS[i] for i in range(0, len(COMMANDS))
}


def get_config_files(
    site_config_dir: str, include_config_dir: bool = True
) -> list[str]:
    """
    Read the *.txt files from the site_config directory and returns the file list.

    Parameters:
        site_config_dir (str): The path to the directory containing the config files
        include_config_dir (bool): Should the config_dir be included in the returned list

    Returns:
        filenames (list[str]): The list of filenames found with the .txt extension
    """
    filenames: list[str] = []

    for file in glob.iglob(f"{site_config_dir}/*.txt", include_hidden=True):
        if file.endswith("LICENSE.txt"):
            continue

        if include_config_dir:
            filenames.append(file)
        else:
            filenames.append(file.removeprefix(f"{site_config_dir}/"))

    filenames.sort()
    return filenames


def get_host_for_url(url: str) -> str:
    parsed_uri = urlparse(url)
    return parsed_uri.netloc


def get_possible_config_file_names_for_host(
    host: str, file_extension: str = ".txt"
) -> list[str]:
    """
    The five filters config files can be of the form

    - .specific.domain.tld (for *.specific.domain.tld)
    - specific.domain.tld (for this specific domain)
    - .domain.tld (for *.domain.tld)
    - domain.tld (for domain.tld)
    """

    parts = host.split(".")

    if len(parts) < 2:
        raise ValueError(
            f"The host must be of the form `host.com`. It seems that there is no dot in the provided host: {host}"
        )

    tld = parts.pop()
    domain = parts.pop()

    first_possible_name = f"{domain}.{tld}{file_extension}"
    possible_names = [first_possible_name, f".{first_possible_name}"]

    # While we still have parts in the domain name, prepend the part
    # and create the 2 new possible names
    while len(parts) > 0:
        next_part = parts.pop()
        possible_name = f"{next_part}.{possible_names[-2]}"
        possible_names.append(possible_name)
        possible_names.append(f".{possible_name}")

    # Put the most specific file names first
    possible_names.reverse()

    return possible_names


def get_config_file_for_host(config_files: list[str], host: str) -> str | None:
    possible_config_file_names = get_possible_config_file_names_for_host(host)
    for config_file in config_files:
        basename = os.path.basename(config_file)
        for possible_config_file_name in possible_config_file_names:
            if basename == possible_config_file_name:
                return config_file

def is_unmerdifiable(url,ftr_site_config):
        config_files = get_config_files(ftr_site_config)
        if load_site_config_for_url(config_files,url):
            return True
        else:
            return False

def parse_site_config_file(config_file_path: str) -> dict | None:
    config = {}
    with open(config_file_path, "r") as file:
        previous_command = None
        while line := file.readline():
            line = line.strip()

            # skip comments, empty lines
            if line == "" or line.startswith("#") or line.startswith("//"):
                continue

            command_name = None
            command_value = None
            pattern = re.compile(r"^([a-z_]+)(?:\((.*)\))*:[ ]*(.*)$", re.I)

            result = pattern.search(line)

            if not result:
                logging.error(
                    f"-> 🚨 ERROR: unknown line format for line `{line}` in file `{config_file_path}`. Skipping."
                )
                continue

            command_name = result.group(1).lower()
            command_arg = result.group(2)
            command_value = result.group(3)

            # strip_attr is now an alias for strip, for example:
            # strip_attr: //img/@srcset
            if "strip_attr" == command_name:
                command_name = "strip"

            command = COMMANDS_PER_NAME.get(command_name)

            if command is None:
                logging.warning(
                    f"-> ⚠️ WARNING: unknown command name for line `{line}` in file `{config_file_path}`. Skipping."
                )
                continue

            # Check for commands where we accept multiple statements but we don't have args provided
            # It handles `replace_string: value` and not `replace_string(test): value`
            if (
                command.accept_multiple_values
                and command_arg is None
                and not command.special_command
            ):
                config.setdefault(command_name, []).append(command_value)
            # Single value command that should evaluate to a bool
            elif command.is_bool and not command.special_command:
                config[command_name] = "yes" == command_value or "true" == command_value
            # handle replace_string(test): value
            elif command.name == "replace_string" and command_arg is not None:
                config.setdefault("find_string", []).append(command_arg)
                config.setdefault("replace_string", []).append(command_value)
            # handle http_header(user-agent): Mozilla/5.2
            elif command.name == "http_header" and command_arg is not None:
                config.setdefault("http_header", []).append(
                    {command_arg: command_value}
                )
            # handle if_page_contains: Xpath value
            elif command.name == "if_page_contains":
                # Previous command should be applied only if this expression is true
                previous_command_value = config[previous_command.name]

                # Move the previous command into the "if_page_contains" command
                if (
                    previous_command.accept_multiple_values
                    and len(previous_command_value) > 0
                ):
                    config.setdefault("if_page_contains", {})[command_value] = {
                        previous_command.name: previous_command_value.pop()
                    }

                # Remove the entire key entry if the values are now empty
                if len(previous_command_value) == 0:
                    config.pop(previous_command.name)

            # handle if_page_contains: Xpath value
            elif command.name == "wrap_in":
                config.setdefault("wrap_in", []).append((command_arg, command_value))
            elif command.name == "test_url":
                config.setdefault("test_url", []).append(
                    {command.name: command_value, "test_contains": []}
                )
            elif command.name == "test_contains":
                test_url = config.get("test_url")
                if test_url is None or len(test_url) == 0:
                    logging.error(
                        "-> 🚨 ERROR: No test_url found for given test_contains. Skipping."
                    )
                    continue

                test_url[-1]["test_contains"].append(command_value)
            else:
                config[command_name] = command_value

            previous_command = command

    return config if config != {} else None


def load_site_config_for_host(config_files: list[str], host: str) -> dict | None:
    logging.debug(f"-> Loading site config for {host}")
    config_file = get_config_file_for_host(config_files, host)

    if config_file:
        logging.debug(f"-> Found config file, loading {config_file} config.")
        return parse_site_config_file(config_file)
    else:
        logging.debug(f"-> No config file found for host {host}.")


def load_site_config_for_url(config_files: list[str], url: str) -> dict | None:
    return load_site_config_for_host(config_files, get_host_for_url(url))


# Content extractor code


def replace_strings(site_config: dict, html: str) -> str:
    replace_string_cmds = site_config.get("replace_string", [])
    find_string_cmds = site_config.get("find_string", [])

    if len(replace_string_cmds) == 0 and len(find_string_cmds) == 0:
        return html

    if len(replace_string_cmds) != len(find_string_cmds):
        logging.error(
            "🚨 ERROR: `replace_string` and `find_string` counts are not the same but must be, skipping string replacement."
        )
    else:
        nb_replacement = 0

        for replace_string, find_string in zip(replace_string_cmds, find_string_cmds):
            nb_replacement += html.count(find_string)
            html = html.replace(find_string, replace_string)

        logging.debug(
            f"Replaced {nb_replacement} string{'s'[:nb_replacement ^ 1]} using replace_string/find_string commands."
        )

    logging.debug(f"Html after string replacement: {html}")

    return html


def wrap_in(site_config: dict, lxml_tree):
    for tag, pattern in site_config.get("wrap_in", []):
        logging.debug(f"Wrap in `{tag}` => `{pattern}`")
        elements = lxml_tree.xpath(pattern)
        for element in elements:
            parent = element.getparent()
            newElement = etree.Element(tag)
            newElement.append(deepcopy(element))
            parent.replace(element, newElement)


def strip_elements(site_config: dict, lxml_tree):
    for pattern in site_config.get("strip", []):
        remove_elements_by_xpath(pattern, lxml_tree)


def strip_elements_by_id_or_class(site_config: dict, lxml_tree):
    for pattern in site_config.get("strip_id_or_class", []):
        # Some entries contain " or '
        pattern = pattern.replace("'", "").replace('"', "")
        remove_elements_by_xpath(
            f"//*[contains(concat(' ',normalize-space(@class), ' '),' {pattern} ') or contains(concat(' ',normalize-space(@id),' '), ' {pattern} ')]",
            lxml_tree,
        )


def strip_image_src(site_config: dict, lxml_tree):
    for pattern in site_config.get("strip_image_src", []):
        # Some entries contain " or '
        pattern = pattern.replace("'", "").replace('"', "")
        remove_elements_by_xpath(f"//img[contains(@src,'{pattern}')]", lxml_tree)


def get_body_element(site_config: dict, lxml_tree):
    body_contents = []
    for pattern in site_config.get("body", []):
        elements = lxml_tree.xpath(pattern)
        for body_element in elements:
            body_contents.append(body_element)

    if len(body_contents) == 1:
        return body_contents[0]

    if len(body_contents) > 1:
        body = etree.Element("div")
        for element in elements:
            body.append(element)
        return body


def get_body_element_html(site_config: dict, lxml_tree):
    body = get_body_element(site_config, lxml_tree)
    if body is not None:
        return etree.tostring(body, encoding="unicode")

def remove_hidden_elements(lxml_tree):
    remove_elements_by_xpath(
        "//*[contains(@style,'display:none') or contains(@style,'visibility:hidden')]",
        lxml_tree,
    )


def remove_a_empty_elements(lxml_tree):
    remove_elements_by_xpath(
        "//a[not(./*) and normalize-space(.)='']",
        lxml_tree,
    )


def remove_elements_by_xpath(xpath_expression, lxml_tree):
    elements = lxml_tree.xpath(xpath_expression)
    for element in elements:
        if isinstance(element, etree._Element):
            element.getparent().remove(element)
        else:
            logging.error(
                f"🚨 ERROR: remove by xpath, element is not a Node, got {type(element)}."
            )


def get_xpath_value_for_command(
    site_config: dict, command_name: str, lxml_tree
) -> str | None:
    command_xpaths = site_config.get(command_name, [])

    for command_xpath in command_xpaths:
        value = get_xpath_value(site_config, command_xpath, lxml_tree)
        if value is not None:
            return value


def get_multiple_xpath_values_for_command(
    site_config: dict, command_name: str, lxml_tree
) -> list[str]:
    command_xpaths = site_config.get(command_name, [])
    values = []

    for command_xpath in command_xpaths:
        values = values + get_multiple_xpath_values(
            site_config, command_xpath, lxml_tree
        )

    return values


def get_xpath_value(site_config: dict, xpath: str, lxml_tree):
    elements = lxml_tree.xpath(xpath)

    if isinstance(elements, str) or isinstance(elements, etree._ElementUnicodeResult):
        return str(elements)

    for element in elements:
        # Return the first entry found
        if isinstance(element, str) or isinstance(element, etree._ElementUnicodeResult):
            return str(element)
        else:
            value = etree.tostring(element, method="text", encoding="unicode").strip()
            return " ".join(value.split()).replace("\n", "")


def get_multiple_xpath_values(site_config: dict, xpath: str, lxml_tree):
    values = []

    elements = lxml_tree.xpath(xpath)

    if isinstance(elements, str) or isinstance(elements, etree._ElementUnicodeResult):
        return [str(elements)]

    for element in elements:
        # Return the first entry found

        if isinstance(element, str) or isinstance(element, etree._ElementUnicodeResult):
            values.append(str(element))
        else:
            value = etree.tostring(element, method="text", encoding="unicode").strip()
            value = " ".join(value.split()).replace("\n", "")
            values.append(value)

    return values


def get_body(site_config: dict, html: str):
    html = replace_strings(site_config, html)
    html_parser = etree.HTMLParser(remove_blank_text=True, remove_comments=True)

    tree = etree.fromstring(html, html_parser)

    wrap_in(site_config, tree)
    strip_elements(site_config, tree)
    strip_elements_by_id_or_class(site_config, tree)
    strip_image_src(site_config, tree)
    remove_hidden_elements(tree)
    remove_a_empty_elements(tree)

    return get_body_element_html(site_config, tree)

def unmerdify_from_file(content,url=None,ftr_site_config=None,loglevel=logging.ERROR,\
                NOCONF_FAIL=True):
    html = ""
    # We pass '-' as only file when argparse got no files which will cause fileinput to read from stdin
    for line in fileinput.input(
        files=content if len(content) > 0 else ("-",),
        openhook=fileinput.hook_encoded("utf-8"),
    ):
        html += line
    return unmerdify_html(html,url=url,ftr_site_config=ftr_site_config,loglevel=loglevel,\
                    NOCONF_FAIL=NOCONF_FAIL)

def unmerdify_html(html,url=None,ftr_site_config=None,loglevel=logging.ERROR,\
                NOCONF_FAIL=True):

    set_logging_level(loglevel)
    if not ftr_site_config:
        logging.error("Unmerdify requires a path to a local ftr_site_config directory,\
                      see https://github.com/fivefilters/ftr-site-config directory")
        return 1

    if os.path.isdir(ftr_site_config) and url is None:
        logging.error(
            "ERROR: You must provide an URL with --url if you don't provide a specific config file.",
        )
        return 1

    if os.path.isdir(ftr_site_config):
        config_files = get_config_files(ftr_site_config)
        loaded_site_config = load_site_config_for_url(config_files, url)
    else:
        loaded_site_config = parse_site_config_file(ftr_site_config)


    # If NOCONF_FAIL, we fail if no conf has been found for our content
    # Else, we simply return the full untouched HTML
    if loaded_site_config is None:
        if NOCONF_FAIL:
            logging.error(f"Unable to load site config for `{ftr_site_config}`.")
            return 1
        else:
            logging.debug(f"No config for `{url}`, returning full HTML.")
            return html

    html_replaced = replace_strings(loaded_site_config, html)
    html_parser = etree.HTMLParser(remove_blank_text=True, remove_comments=True)

    tree = etree.fromstring(html_replaced, html_parser)

    title = get_xpath_value_for_command(loaded_site_config, "title", tree)
    logging.debug(f"Got title `{title}`.")

    authors = get_multiple_xpath_values_for_command(loaded_site_config, "author", tree)

    logging.debug(f"Got authors {authors}.")

    date = get_xpath_value_for_command(loaded_site_config, "date", tree)

    logging.debug(f"Got date `{date}`.")

    body_html = get_body(loaded_site_config, html)
    return body_html


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Get the content, only the content: unenshittificator for the web"
    )

    parser.add_argument(
        "ftr_site_config",
        type=str,
        help="The path to the https://github.com/fivefilters/ftr-site-config directory, or a path to a config file.",
    )

    parser.add_argument(
        "-u",
        "--url",
        type=str,
        help="The url you want to unmerdify.",
    )

    parser.add_argument(
        "files",
        metavar="FILE",
        nargs="*",
        help="Files to read, if empty, stdin is used.",
    )

    parser.add_argument(
        "-l",
        "--loglevel",
        default=logging.ERROR,
        choices=logging.getLevelNamesMapping().keys(),
        help="Set log level",
    )

    # @TODO: extract open graph information if any
    #  https://github.com/j0k3r/graby/blob/master/src/Extractor/ContentExtractor.php#L1241
    args = parser.parse_args()
    bodyhtml = unmerdify_from_file(args.files,url=args.url,ftr_site_config=args.ftr_site_config,loglevel=args.loglevel)
    print(bodyhtml)


if __name__ == "__main__":
    main()
