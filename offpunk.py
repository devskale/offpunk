#!/usr/bin/env python3
# Offpunk Offline Gemini client
"""
Offline-First Gemini/Web/Gopher/RSS reader and browser
"""

__version__ = "3.0-beta1"

# Initial imports and conditional imports {{{
import argparse
import cmd
import os
import os.path
import shutil
import sys
import time
import urllib.parse
import gettext

import ansicat
import netcache
import offblocklist
import offthemes
import openk
from offutils import (
    is_local,
    looks_like_url,
    mode_url,
    run,
    term_width,
    unmode_url,
    xdg,
    init_config,
    send_email,
    _HAS_XDGOPEN,
    _LOCALE_DIR,
    find_root,
    urlify,
)

gettext.bindtextdomain('offpunk', _LOCALE_DIR)
gettext.textdomain('offpunk')
_ = gettext.gettext

try:
    import setproctitle

    setproctitle.setproctitle("offpunk")
    _HAS_SETPROCTITLE = True
except ModuleNotFoundError:
    _HAS_SETPROCTITLE = False


# This method copy a string to the system clipboard
def clipboard_copy(to_copy):
    copied = False
    if shutil.which("xsel"):
        run("xsel -b -i", input=to_copy, direct_output=True)
        copied = True
    if shutil.which("xclip"):
        run("xclip -selection clipboard", input=to_copy, direct_output=True)
        copied = True
    if shutil.which("wl-copy"):
        run("wl-copy", input=to_copy, direct_output=True)
        copied = True
    if not copied:
        print(_("Install xsel/xclip (X11) or wl-clipboard (Wayland) to use copy"))


# This method returns an array with all the values in all system clipboards
def clipboard_paste():
    # We use a set to avoid duplicates
    clipboards = set()
    commands = set()
    pasted = False
    if shutil.which("xsel"):
        pasted = True
        for selec in ["-p", "-s", "-b"]:
            commands.add("xsel " + selec)
    if shutil.which("xclip"):
        pasted = True
        for selec in ["clipboard", "primary", "secondary"]:
            commands.add("xsel " + selec)
    if shutil.which("wl-paste"):
        pasted = True
        for selec in ["", "-p"]:
            commands.add("wl-paste " + selec)
    for command in commands:
        try:
            clipboards.add(run(command))
        except Exception:
            # print("Skippink clipboard %s because %s"%(selec,err))
            pass
    if not pasted:
        print(
            _("Install xsel/xclip (X11) or wl-clipboard (Wayland) to get URLs from your clipboard")
        )
    return list(clipboards)


# }}} end of imports

# Command abbreviations
_ABBREVS = {# {{{
    "..": "up",
    "a": "add",
    "b": "back",
    "bb": "blackbox",
    "bm": "bookmarks",
    "book": "bookmarks",
    "cert": "certs",
    "cp": "copy",
    "coo": "cookies",
    "f": "forward",
    "g": "go",
    "h": "history",
    "hist": "history",
    "l": "view",
    "less": "view",
    "man": "help",
    "mv": "move",
    "n": "next",
    "off": "offline",
    "on": "online",
    "p": "previous",
    "prev": "previous",
    "q": "quit",
    "r": "reload",
    "s": "save",
    "se": "search",
    "/": "find",
    "t": "tour",
    "u": "up",
    "v": "view",
    "w": "wikipedia",
    "wen": "wikipedia en",
    "wfr": "wikipedia fr",
    "wes": "wikipedia es",
    "yy": "copy url",   # That’s an Easter Egg for Vimium users ;-)
    "abbrevs": "alias",
}# }}}

# GeminiClient Decorators
# decorator to be sure that self.current_url exists
def needs_gi(inner):
    def outer(self, *args, **kwargs):
        if not self.current_url:
            print(_("You need to 'go' somewhere, first"))
            return None
        else:
            return inner(self, *args, **kwargs)

    outer.__doc__ = inner.__doc__
    return outer

#red warning to print
REDERROR="\x1b[1;31m"+_("Error: ")+"\x1b[0m"

class GeminiClient(cmd.Cmd):
    def __init__(self, completekey="tab", sync_only=False):
        super().__init__(completekey=completekey)
        # Set umask so that nothing we create can be read by anybody else.
        # The certificate cache and TOFU database contain "browser history"
        # type sensitivie information.
        os.umask(0o077)
        self.opencache = openk.opencache()
        self.theme = offthemes.default
        self.current_url = None
        self.hist_index = 0
        self.marks = {}
        self.page_index = 0
        # Sync-only mode is restricted by design
        self.offline_only = False
        self.sync_only = sync_only
        self.support_http = netcache._DO_HTTP
        self.options = {
            "debug": False,
            "beta": False,
            "timeout": 600,
            "short_timeout": 5,
            "width": 72,
            "auto_follow_redirects": True,
            "tls_mode": "tofu",
            "archives_size": 200,
            "history_size": 200,
            "max_size_download": 10,
            "editor": None,
            "images_mode": "readable",
            "redirects": True,
            # the wikipedia entry needs two %s, one for lang, other for search
            "wikipedia": "gemini://gemi.dev/cgi-bin/wp.cgi/view/%s?%s",
            "search": "gemini://kennedy.gemi.dev/search?%s",
            "websearch": "https://wiby.me/?q=%s",
            "accept_bad_ssl_certificates": False,
            "default_protocol": "gemini",
            "ftr_site_config": None,
            "preformat_wrap": False,
            # images_size should be an integer. If bigger than text width, 
            # it will be reduced
            "images_size": 100,
            # avaliable linkmode are "none" and "end".
            "linkmode": "none",
            #command that will be used on empty line,
            "default_cmd": "links 10",
            # user prompt in on and offline mode
            "prompt_on": "ON",
            "prompt_off": "OFF",
            "prompt_close": "> ",
            "gemini_images": True,
        }
        self.set_prompt("ON")
        self.opencache.redirects = offblocklist.redirects
        for i in offblocklist.blocked:
            self.opencache.redirects[i] = "blocked"
        term_width(new_width=self.options["width"])
        self.log = {
            "start_time": time.time(),
        }

    def set_prompt(self, prompt):
        key = "prompt_%s" % prompt.lower()

        # default color is green
        colors = self.theme.get(key, ["green"])

        open_color = ""
        close_color = ""
        for color in colors:
            # default to green 32 if color name `green` is not found
            ansi = offthemes.colors.get(color, ["32", "39"])

            open_color += "%s;" % ansi[0]
            close_color += "%s;" % ansi[1]

        # removing the last ";"
        open_color = open_color.rstrip(";")
        close_color = close_color.rstrip(";")

        self.prompt = (
            "\001\x1b[%sm\002" % open_color
            + self.options[key]
            + "\001\x1b[%sm\002" % close_color
            + self.options["prompt_close"]
        )
        # support for 256 color mode:
        # self.prompt = "\001\x1b[38;5;76m\002" + "ON" + "\001\x1b[38;5;255m\002" + "> " + "\001\x1b[0m\002"
        return self.prompt

    def complete_list(self, text, line, begidx, endidx):
        allowed = []
        cmds = ["create", "edit", "subscribe", "freeze", "normal", "delete", "help"]
        lists = self.list_lists()
        words = len(line.split())
        # We need to autocomplete listname for the first or second argument
        # If the first one is a cmds
        if words <= 1:
            allowed = lists + cmds
        elif words == 2:
            # if text, the completing word is the second
            if text:
                allowed = lists + cmds
            else:
                current_cmd = line.split()[1]
                if current_cmd in ["help", "create"]:
                    allowed = []
                elif current_cmd in cmds:
                    allowed = lists
        elif words == 3 and text != "":
            current_cmd = line.split()[1]
            if current_cmd in ["help", "create"]:
                allowed = []
            elif current_cmd in cmds:
                allowed = lists
        return [i + " " for i in allowed if i.startswith(text)]

    def complete_add(self, text, line, begidx, endidx):
        if len(line.split()) == 2 and text != "":
            allowed = self.list_lists()
        elif len(line.split()) == 1:
            allowed = self.list_lists()
        else:
            allowed = []
        return [i + " " for i in allowed if i.startswith(text)]

    def complete_move(self, text, line, begidx, endidx):
        return self.complete_add(text, line, begidx, endidx)

    def complete_tour(self, text, line, begidx, endidx):
        return self.complete_add(text, line, begidx, endidx)

    def complete_theme(self, text, line, begidx, endidx):
        elements = offthemes.default
        colors = offthemes.colors
        words = len(line.split())
        if words <= 1:
            allowed = elements
        elif words == 2 and text != "":
            allowed = elements
        else:
            allowed = colors
        return [i + " " for i in allowed if i.startswith(text)]

    def get_renderer(self, url=None):
        # If launched without argument, we return the renderer for the current URL
        if not url:
            url = self.current_url
        if url:
            # we should pass the options to the renderer
            return self.opencache.get_renderer(url, theme=self.theme,**self.options)

    def _go_to_url(
        self,
        url,
        update_hist=True,
        force_refresh=False,
        handle=True,
        grep=None,
        name=None,
        mode=None,
        limit_size=False,
        force_large_download=False,
    ):
        """This method might be considered "the heart of Offpunk".
        Everything involved in fetching a gemini resource happens here:
        sending the request over the network, parsing the response,
        storing the response in a temporary file, choosing
        and calling a handler program, and updating the history.
        Nothing is returned."""
        if not url:
            return
        url, newmode = unmode_url(url)
        if not mode:
            mode = newmode
        # we don’t handle the name anymore !
        if name:
            print(_("We don’t handle name of URL: %s") % name)
        # Code to translate URLs to better frontends (think twitter.com -> nitter)
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc
        if netloc.startswith("www."):
            netloc = netloc[4:]
        params = {}
        params["timeout"] = self.options["short_timeout"]
        if limit_size:
            params["max_size"] = int(self.options["max_size_download"]) * 1000000
        params["print_error"] = not self.sync_only
        params["interactive"] = not self.sync_only
        params["offline"] = self.offline_only
        params["accept_bad_ssl_certificates"] = self.options[
            "accept_bad_ssl_certificates"
        ]
        params["ftr_site_config"] = self.options["ftr_site_config"]
        params["preformat_wrap"] = self.options["preformat_wrap"]
        if mode:
            params["images_mode"] = mode
        else:
            params["images_mode"] = self.options["images_mode"]
        params["images_size"] = self.options["images_size"]
        params["gemini_images"] = self.options["gemini_images"]
        # avaliable linkmode are "none" and "end".
        params["linkmode"] = self.options["linkmode"]
        if force_refresh:
            params["validity"] = 1
        elif not self.offline_only:
            # A cache is always valid at least 60seconds
            params["validity"] = 60
        params["force_large_download"] = force_large_download
        # Use cache or mark as to_fetch if resource is not cached
        if handle and not self.sync_only:
            displayed, url = self.opencache.openk(
                url, mode=mode, grep=grep, theme=self.theme,**params
            )
            modedurl = mode_url(url, mode)
            if not displayed:
                # if we can’t display, we mark to sync what is not local
                if not is_local(url) and not netcache.is_cache_valid(url):
                    self.get_list("to_fetch")
                    r = self.list_add_line("to_fetch", url=modedurl, verbose=False)
                    if r:
                        print(_("%s not available, marked for syncing") % url)
                    else:
                        print(_("%s already marked for syncing") % url)
            else:
                self.page_index = 0
                # Update state (external files are not added to history)
                self.current_url = modedurl
                if update_hist and not self.sync_only:
                    self._update_history(modedurl)
        else:
            # we are asked not to handle or in sync_only mode
            if self.support_http or parsed.scheme not in ["http", "https"]:
                netcache.fetch(url, redirects=self.opencache.redirects,**params)

    @needs_gi
    def _show_lookup(self, offset=0, end=None, show_url=False):
        l = self.get_renderer().get_links()
        for n, u in enumerate(l[offset:end]):
            index = n + offset + 1
            line = "[%s] %s" % (index, u)
            print(line)

    def _update_history(self, url):
        # We never update while in sync_only
        # We don’t add history to itself.
        if self.sync_only or not url or url == "list:///history":
            return
        # First, we call get_list to create history if needed
        self.get_list("history")
        # Don’t update history if we are back/forwarding through it
        if self.hist_index > 0:
            links = self.list_get_links("history")
            length = len(links)
            if length > 0 and links[self.hist_index] == url:
                return
        self.list_add_top(
            "history",
            limit=self.options["history_size"],
            truncate_lines=self.hist_index,
        )
        self.hist_index = 0

    # Cmd implementation follows
    def default(self, line, verbose=True):
        if line.strip() == "EOF":
            self.onecmd("quit")
            return True
        elif line.startswith("/"):
            self.do_find(line[1:])
            return True
        # Expand abbreviated commands
        first_word = line.split()[0].strip()
        if first_word in _ABBREVS:
            full_cmd = _ABBREVS[first_word]
            expanded = line.replace(first_word, full_cmd, 1)
            self.onecmd(expanded)
            return True
        # Try to access it like an URL
        if looks_like_url(line):
            self.do_go(line)
            return True
        # Try to parse numerical index for lookup table
        try:
            n = int(line.strip())
        except ValueError:
            if verbose: print(_("What?"))
            return False
        # if we have no url, there's nothing to do
        if self.current_url is None:
            if verbose: print(_("No links to index"))
            return False
        else:
            r = self.get_renderer()
            if r:
                url = r.get_link(n)
                self._go_to_url(url)
            else:
                print(_("No page with links"))
                return False

    # Settings
    def do_redirect(self, line):
        """Display and manage the list of redirected URLs. This features is mostly useful to use privacy-friendly frontends for popular websites."""
        if len(line.split()) == 1:
            if line in self.opencache.redirects:
                print(_("%s is redirected to %s") % (line, self.opencache.redirects[line]))
            else:
                print(_("Please add a destination to redirect %s") % line)
        elif len(line.split()) >= 2:
            orig, dest = line.split(" ", 1)
            if dest.lower() == "none":
                if orig in self.opencache.redirects:
                    self.opencache.redirects.pop(orig)
                    print(_("Redirection for %s has been removed") % orig)
                else:
                    print(_("%s was not redirected. Nothing has changed.") % orig)
            elif dest.lower() == "block":
                self.opencache.redirects[orig] = "blocked"
                print(_("%s will now be blocked") % orig)
            else:
                self.opencache.redirects[orig] = dest
                print(_("%s will now be redirected to %s") % (orig, dest))
            #refreshing the cache for coloured redirects
            self.opencache.cleanup()
        else:
            toprint = _("Current redirections:\n")
            toprint += "--------------------\n"
            for r in self.opencache.redirects:
                toprint += "%s\t->\t%s\n" % (r, self.opencache.redirects[r])
            toprint += _('\nTo add new, use "redirect origine.com destination.org"')
            toprint += _('\nTo remove a redirect, use "redirect origine.com NONE"')
            toprint += (
                _('\nTo completely block a website, use "redirect origine.com BLOCK"')
            )
            toprint += _('\nTo block also subdomains, prefix with *: "redirect *origine.com BLOCK"')
            print(toprint)

    def do_set(self, line):
        """View or set various options."""
        if not line.strip():
            # Show all current settings
            for option in sorted(self.options.keys()):
                print("%s   %s" % (option, self.options[option]))
        elif len(line.split()) == 1:
            # Show current value of one specific setting
            option = line.strip()
            if option in self.options:
                print("%s   %s" % (option, self.options[option]))
            else:
                print(_("Unrecognised option %s") % option)
        else:
            # Set value of one specific setting
            option, value = line.split(" ", 1)
            if option not in self.options:
                print(_("Unrecognised option %s") % option)
                return
            # Validate / convert values
            elif option == "tls_mode":
                if value.lower() not in ("ca", "tofu"):
                    print(_("TLS mode must be `ca` or `tofu`!"))
                    return
            elif option == "accept_bad_ssl_certificates":
                if value.lower() == "false":
                    print(_("Only high security certificates are now accepted"))
                elif value.lower() == "true":
                    print(_("Low security SSL certificates are now accepted"))
                else:
                    #TRANSLATORS keep accept_bad_ssl_certificates, True, and False
                    print(_("accept_bad_ssl_certificates should be True or False"))
                    return
            elif option == "width":
                if value.isnumeric():
                    value = int(value)
                    print(_("changing width to "), value)
                    term_width(new_width=value)
                else:
                    print(_("%s is not a valid width (integer required)") % value)
            elif option == "linkmode":
                if value.lower() not in ("none", "end"):
                    print(_("Avaliable linkmode are `none` and `end`."))
                    return
            elif value.isnumeric():
                value = int(value)
            elif value.lower() == "false":
                value = False
            elif value.lower() == "true":
                value = True
            elif value.startswith('"') and value.endswith('"'):
                # unquote values if they are quoted
                value = value[1:-1]
            else:
                try:
                    value = float(value)
                except ValueError:
                    pass
            self.options[option] = value
            #We clean the cache for some options that affect rendering
            if option in ["preformat_wrap","width", "linkmode","gemini_images"]:
                self.opencache.cleanup()

    def do_theme(self, line):
        """Change the colors of your rendered text.

        "theme ELEMENT COLOR"

        ELEMENT is one of: window_title, window_subtitle, title,
        subtitle,subsubtitle,link,oneline_link,new_link,image_link,preformatted,blockquote,\
                blocked_link.

        COLOR is one or many (separated by space) of: bold, faint, italic, underline, black,
        red, green, yellow, blue, purple, cyan, white.

        Each color can alternatively be prefaced with "bright_".
        If color is "none", then that part of the theme is removed.

        theme can also be used with "preset" to load an existing theme.

        "theme preset"  : show available themes
        "theme preset PRESET_NAME" : swith to a given preset"""

        words = line.split()
        le = len(words)
        if le == 0:
            t = self.get_renderer("list:///").get_theme()
            for e in t:
                print("%s set to %s" % (e, t[e]))
        else:
            element = words[0]
            if element == "preset":
                if le == 1:
                    print(_("Available preset themes are: ")) 
                    print(" - default")
                    for k in offthemes.themes.keys():
                        print(" - %s"%k)
                elif words[1] == "default":
                    for key in offthemes.default:
                        self.theme[key] = offthemes.default[key]
                        self.opencache.cleanup()
                elif words[1] in offthemes.themes.keys():
                    #every preset is applied assuming default
                    #so we must apply default first!
                    for theme in [offthemes.default,offthemes.themes[words[1]]]:
                        for key in theme:
                            self.theme[key] = theme[key]
                    self.opencache.cleanup()
                else:
                    print(_("%s is not a valid preset theme")%words[1])
            elif element not in offthemes.default.keys():
                print(_("%s is not a valid theme element") % element)
                print(_("Valid theme elements are: "))
                valid = []
                for k in offthemes.default:
                    valid.append(k)
                print(valid)
                return
            else:
                if le == 1:
                    if element in self.theme.keys():
                        value = self.theme[element]
                    else:
                        value = offthemes.default[element]
                    print(_("%s is set to %s") % (element, str(value)))
                elif le == 2 and words[1].lower() in ["none"]:
                    if element in self.theme.keys():
                        value = self.theme[element]
                        self.theme.pop(element)
                        print(_("%s reset (it was set to %s)"%(element,value)))
                        self.opencache.cleanup()
                    else:
                        print(_("%s is not set. Nothing to do"%element))
                else:
                    # Now we parse the colors
                    for w in words[1:]:
                        if w not in offthemes.colors.keys():
                            print(_("%s is not a valid color") % w)
                            print(_("Valid colors are one of: "))
                            valid = []
                            for k in offthemes.colors:
                                valid.append(k)
                            print(valid)
                            return
                    self.theme[element] = words[1:]
                    self.opencache.cleanup()
        # now we update the prompt
        if self.offline_only:
            self.set_prompt("OFF")
        else:
            self.set_prompt("ON")

    def do_handler(self, line):
        """View or set handler commands for different MIME types.
        handler MIMETYPE : see handler for MIMETYPE
        handler MIMETYPE CMD : set handler for MIMETYPE to CMD
        in the CMD, %s will be replaced by the filename.
        if no %s, it will be added at the end.
        MIMETYPE can be the true mimetype or the file extension.

        Examples: 
            handler application/pdf zathura %s
            handler .odt lowriter
            handler docx lowriter"""
        if not line.strip():
            # Show all current handlers
            h = self.opencache.get_handlers()
            for mime in sorted(h.keys()):
                print("%s   %s" % (mime, h[mime]))
        elif len(line.split()) == 1:
            mime = line.strip()
            h = self.opencache.get_handlers(mime=mime)
            if h:
                print("%s   %s" % (mime, h))
            else:
                print(_("No handler set for MIME type %s") % mime)
        else:
            mime, handler = line.split(" ", 1)
            self.opencache.set_handler(mime, handler)

    def do_alias(self, line):
        """Create or modifiy an alias
        alias : show all existing aliases
        alias ALIAS : show the command linked to ALIAS
        alias ALIAS CMD : create or replace existing ALIAS to be linked to command CMD"""
        #building the list of existing commands to avoid conflicts
        commands = []
        for name in self.get_names():
            if name.startswith("do_"):
                commands.append(name[3:])
        if not line.strip():
            header = "Command Aliases:"
            self.stdout.write("\n{}\n".format(str(header)))
            if self.ruler:
                self.stdout.write("{}\n".format(str(self.ruler * len(header))))
            for k, v in _ABBREVS.items():
                self.stdout.write("{:<7}  {}\n".format(k, v))
            self.stdout.write("\n")
        elif len(line.split()) == 1:
            alias = line.strip()
            if alias in commands:
                print(_("%s is a command and cannot be aliased")%alias)
            elif alias in _ABBREVS:
                print(_("%s is currently aliased to \"%s\"") %(alias,_ABBREVS[alias]))
            else:
                print(_("there’s no alias for \"%s\"")%alias)
        else:
            alias, cmd = line.split(None,1)
            if alias in commands:
                print(_("%s is a command and cannot be aliased")%alias)
            else:
                _ABBREVS[alias] = cmd
                print(_("%s has been aliased to \"%s\"")%(alias,cmd))
        

    def do_offline(self, *args):
        """Use Offpunk offline by only accessing cached content"""
        if self.offline_only:
            print(_("Offline and undisturbed."))
        else:
            self.offline_only = True
            self.set_prompt("OFF")
            print(_("Offpunk is now offline and will only access cached content"))

    def do_online(self, *args):
        """Use Offpunk online with a direct connection"""
        if self.offline_only:
            self.offline_only = False
            self.set_prompt("ON")
            print(_("Offpunk is online and will access the network"))
        else:
            print(_("Already online. Try offline."))

    def do_copy(self, arg):
        """Copy the content of the last visited page as gemtext/html in the clipboard.
        Use with "url" as argument to only copy the adress.
        Use with "raw" to copy ANSI content as seen in your terminal (with colour codes).
        Use with "cache" to copy the path of the cached content.
        Use with "title" to copy the title of the page.
        Use with "link" to copy a link in the gemtext format to that page with the title."""

        if self.current_url:
            args = arg.split()
            if args and args[0] == "url":
                if len(args) > 1 and args[1].isdecimal():
                    url = self.get_renderer().get_link(int(args[1]))
                else:
                    url = unmode_url(self.current_url)[0]
                print(url)
                clipboard_copy(url)
            elif args and args[0] == "raw":
                tmp = self.opencache.get_temp_filename(self.current_url)
                if tmp:
                    clipboard_copy(open(tmp, "rb"))
            elif args and args[0] == "cache":
                clipboard_copy(netcache.get_cache_path(self.current_url))
            elif args and args[0] == "title":
                title = self.get_renderer().get_page_title()
                clipboard_copy(title)
                print(title)
            elif args and args[0] == "link":
                link = "=> %s %s" % (
                    unmode_url(self.current_url)[0],
                    self.get_renderer().get_page_title(),
                )
                print(link)
                clipboard_copy(link)
            else:
                clipboard_copy(open(netcache.get_cache_path(self.current_url), "rb"))
        else:
            print(_("No content to copy, visit a page first"))

    #Share current page by email
    def do_share(self, arg):
        """Send current page by email to someone else.
        Use with "url" as first argument to send only the address.
        Use with "text" as first argument to send the full content. TODO
        Without argument, "url" is assumed.
        Next arguments are the email adresses of the recipients.
        If no destination, you will need to fill it in your mail client."""

        # default "share" case were users has to give the recipient
        if self.current_url:
            # we will not consider the url argument (which is the default)
            # if other argument, we will see if it is an URL
            if is_local(self.current_url):
                print(_("We cannot share %s because it is local only")%self.current_url)
                return
            else:
                r = self.get_renderer()
                #default share case
                dest = ""
                subject= r.get_page_title()
                body = unmode_url(self.current_url)[0]
            args = arg.split()
            if args :
                if args[0] == "text":
                    args.pop(0)
                    print(_("TODO: sharing text is not yet implemented"))
                    return
                # we will not consider the url argument (which is the default)
                # if other argument, we will see if it is an URL
                elif args[0] == "url":
                    args.pop(0)
                if len(args) > 0:
                    for a in args:
                        # we only takes arguments with @ as email adresses
                        if "@" in a:
                            dest += "," + a
            send_email(dest,subject=subject,body=body,toconfirm=False)
            #quick debug
           # print("Send mail to %s"%dest)
           # print("Subject is %s"%subject)
           # print("Body is %s"%body)
        else:
            print(_("Nothing to share, visit a page first"))

    #Reply to a page by finding a mailto link in the page
    def do_reply(self, arg):
        """Reply by email to a page by trying to find a good email for the author.
        If an email is provided as an argument, it will be used.
        arguments:
        - "save" : allows to detect and save email without actually sending an email.
        - "save new@email" : save a new reply email to replace an existing one"""
        args = arg.split(" ")
        if self.current_url:
            r = self.get_renderer()
            # The reply intelligence where we try to find a email address
            # Reply is not allowed for local URL (at least for now)
            if not is_local(self.current_url):
                potential_replies = []
                # Add email adresses from arguments
                for a in args:
                    if "@" in a: potential_replies.append(a)
                saved_replies = []
                # First we look if we have a mail recorder for that URL
                # emails are recorded according to URL in XDG_DATA/offpunk/reply
                # We don’t care about the protocol because it is assumed that 
                # a given URL will always have the same contact, even on different
                # protocols
                parents = find_root(self.current_url, return_value = "list")
                while len(potential_replies) == 0 and len(parents) > 0 :
                    parurl = parents.pop(0)
                    replyfile = netcache.get_cache_path(parurl,\
                                include_protocol=False, xdgfolder="data",subfolder="reply")
                    if os.path.exists(replyfile):
                        with open(replyfile) as f:
                            for li in f.readlines():
                                #just a rough check that we have an email address
                                l = li.strip()
                                if "@" in l: 
                                    potential_replies.append(l)
                                    saved_replies.append(l)
                            f.close()
                #No mail recorded? Let’s look at the current page
                #We check for any mailto: link
                if len(potential_replies) == 0:
                    for l in r.get_links():
                        if l.startswith("mailto:"):
                            #parse mailto link to remove mailto:
                            l = l.removeprefix("mailto:").split("?")[0]
                            if l not in potential_replies:
                                potential_replies.append(l)
                # if we have no reply address, we investigate parents page
                # Until we are at the root of users capsule/website/hole
                parents = find_root(self.current_url, return_value = "list")
                while len(potential_replies) == 0 and len(parents) > 0 :
                    parurl = parents.pop(0)
                    replydir = netcache.get_cache_path(parurl,xdgfolder="data",\
                                include_protocol=False,subfolder="reply")
                    #print(replydir)
                    par_rend = self.get_renderer(parurl)
                    if par_rend:
                        for l in par_rend.get_links():
                            if l.startswith("mailto:"):
                                #parse mailto link to remove mailto:
                                l = l.removeprefix("mailto:").split("?")[0]
                                if l not in potential_replies:
                                    potential_replies.append(l)
                #print("replying to %s"%potential_replies)
                if len(potential_replies) > 1:
                    stri = _("Multiple emails addresse were found:") + "\n"
                    counter = 1
                    for mail in potential_replies:
                        stri += "[%s] %s\n" %(counter,mail)
                        counter += 1
                    stri += "[0] "+ _("None of the above") + "\n"
                    stri += "---------------------\n"
                    stri += _("Which email will you use to reply?") +" > "
                    ans = input(stri)
                    if ans.isdigit() and len(potential_replies) >= int(ans):
                        if int(ans) == 0:
                            dest = ""
                        else :
                            dest = potential_replies[int(ans)-1]
                    else:
                        dest = ""
                elif len(potential_replies) == 1:
                    dest = potential_replies[0]
                else:
                    stri = _("Enter the contact email for this page?") + "\n"
                    stri += "> "
                    ans = input(stri)
                    dest = ans.strip()
                # Now, let’s save the email (if it is not already the case)
                tosaveurl = None
                if dest and dest not in saved_replies:
                    rootname = find_root(self.current_url,return_value="name")
                    rooturl = find_root(self.current_url)
                    stri = _("Email address:") + " \t\x1b[1;32m" + dest + "\x1b[0m\n"
                    stri += _("Do you want to save this email as a contact for") + "\n"
                    stri += "[1] " + _("Current page only") + "\n"
                    stri += "[2] " + _("The whole %s space")%rootname + " - " + rooturl + "\n"
                    stri += "[0] " + _("Don’t save this email") + "\n"
                    stri += "---------------------\n"
                    stri += _("Your choice?") + " > "
                    ans = input(stri)
                    if ans.strip() == "1":
                        tosaveurl = self.current_url
                    elif ans.strip() == "2":
                        tosaveurl = rooturl
                    if tosaveurl:
                        savefile = netcache.get_cache_path(tosaveurl,\
                                include_protocol=False, xdgfolder="data",subfolder="reply")
                        # first, let’s creat all the folders needed
                        savefolder = os.path.dirname(savefile)
                        os.makedirs(savefolder, exist_ok=True)
                        # Then we write the email
                        with open(savefile,"w") as f:
                            f.write(dest)
                            f.close()
                if "save" in args:
                    if tosaveurl and dest:
                        print(_("Email %s has been recorded as contact for %s")%(dest,tosaveurl))
                    else: print(_("Nothing to save"))
                else:
                    subject = "RE: "+ r.get_page_title()
                    body = _("In reply to ") + unmode_url(self.current_url)[0]
                    send_email(dest,subject=subject,body=body,toconfirm=False)
            else:
                print(_("We cannot reply to %s because it is local only")%self.current_url)
        else:
            print(_("Nothing to share, visit a page first"))


    def do_cookies(self, arg):
        """Manipulate cookies:
        "cookies import <file> [url]" - import cookies from file to be used with [url]
        "cookies list [url]" - list existing cookies for current url
        default is listing cookies for current domain.
        
        To get a cookie as a txt file,use the cookie-txt extension for Firefox."""
        al = arg.split()
        if len(al) == 0:
            al = ["list"]
        mode = al[0]
        url = self.current_url
        if mode == "list":
            if len(al) == 2:
                url = al[1]
            elif len(al) > 2:
                print(_("Too many arguments to list."))
                return
            if not url:
                print(_("URL required (or visit a page)."))
                return
            cj = netcache.get_cookiejar(url)
            if not cj:
                print(_("Cookies not enabled for url"))
                return
            print(_("Cookies for url:"))
            for c in cj:
                #TRANSLATORS domain, path, expiration time, name, value
                print(_("%s %s expires:%s %s=%s") % (c.domain, c.path,
                    time.ctime(c.expires), c.name, c.value))
            return
        elif mode == "import":
            if len(al) < 2:
                print(_("File parameter required for import."))
                return
            if len(al) == 3:
                url = al[2]
            elif len(al) > 3:
                print(_("Too many arguments to import"))
                return
            if not url:
                print(_("URL required (or visit a page)."))
                return
            cj = netcache.get_cookiejar(url, create=True)
            try:
                cj.load(os.path.expanduser(al[1]))
                cj.save()
            except FileNotFoundError:
                print(_("File not found"))
                return
            print(_("Imported."))
            return
        print(_("Huh?"))
        return

    def do_go(self, line):
        """Go to a gemini URL or marked item."""
        line = line.strip()
        if not line:
            clipboards = clipboard_paste()
            urls = []
            for u in clipboards:
                if "://" in u and looks_like_url(u) and u not in urls:
                    urls.append(u)
            if len(urls) > 1:
                stri = _("URLs in your clipboard\n")
                counter = 0
                for u in urls:
                    counter += 1
                    stri += "[%s] %s\n" % (counter, u)
                stri += _("Where do you want to go today ?> ")
                ans = input(stri)
                if ans.isdigit() and 0 < int(ans) <= len(urls):
                    self.do_go(urls[int(ans) - 1])
            elif len(urls) == 1:
                self.do_go(urls[0])
            else:
                print(_("Go where? (hint: simply copy an URL in your clipboard)"))

        # First, check for possible marks
        elif line in self.marks:
            url = self.marks[line]
            self._go_to_url(url)
        # or a local file
        elif os.path.exists(os.path.expanduser(line)):
            self._go_to_url(line)
        # If this isn't a mark, treat it as a URL
        elif looks_like_url(line):
            self._go_to_url(line)
        elif (
            "://" not in line
            and "default_protocol" in self.options.keys()
            and looks_like_url(self.options["default_protocol"] + "://" + line)
        ):
            self._go_to_url(self.options["default_protocol"] + "://" + line)
        else:
            print(_("%s is not a valid URL to go") % line)

    @needs_gi
    def do_reload(self, *args):
        """Reload the current URL."""
        if self.offline_only and not is_local(self.current_url):
            self.get_list("to_fetch")
            r = self.list_add_line("to_fetch", url=self.current_url, verbose=False)
            if r:
                print(_("%s marked for syncing") % self.current_url)
            else:
                print(_("%s already marked for syncing") % self.current_url)
            self.opencache.clean_url(self.current_url)
        else:
            self.opencache.clean_url(self.current_url)
            self._go_to_url(self.current_url, force_refresh=False)

    @needs_gi
    def do_up(self, *args):
        """Go up one directory in the path.
        Take an integer as argument to go up multiple times.
        Use "~" to go to the user root"
        Use "/" to go to the server root."""
        level = 1
        if args[0].isnumeric():
            level = int(args[0])
        elif args[0] == "/":
            #yep, this is a naughty hack to go to root
            level = 1000
        elif args[0] == "~":
            self.do_root()
        elif args[0] != "":
            print(_("Up only take integer as arguments"))
        url = unmode_url(self.current_url)[0]
        # UP code using the new find_root
        urllist = find_root(url,absolute=True,return_value="list")
        if len(urllist) > level:
            newurl = urllist[level]
        else:
            newurl = urllist[-1]
        # new up code ends up here
        self._go_to_url(newurl)

    def do_back(self, *args):
        """Go back to the previous gemini item."""
        links = self.list_get_links("history")
        if self.hist_index >= len(links) - 1:
            return
        self.hist_index += 1
        url = links[self.hist_index]
        self._go_to_url(url, update_hist=False)

    def do_forward(self, *args):
        """Go forward to the next gemini item."""
        links = self.list_get_links("history")
        if self.hist_index <= 0:
            return
        self.hist_index -= 1
        url = links[self.hist_index]
        self._go_to_url(url, update_hist=False)

    @needs_gi
    def do_root(self, *args):
        """Go to the root of current capsule/gemlog/page
        If arg is "/", the go to the real root of the server"""
        absolute = False
        if len(args) > 0 and args[0] == "/":
            absolute = True
        root = find_root(self.current_url,absolute=absolute)
        self._go_to_url(root)

    def do_tour(self, line):
        """Add index items as waypoints on a tour, which is basically a FIFO
        queue of gemini items.

        `tour` or `t` alone brings you to the next item in your tour.
        Items can be added with `tour 1 2 3 4` or ranges like `tour 1-4`.
        All items in current menu can be added with `tour *`.
        All items in $LIST can be added with `tour $LIST`.
        Current item can be added back to the end of the tour with `tour .`.
        Current tour can be listed with `tour ls` and scrubbed with `tour clear`."""
        # Creating the tour list if needed
        self.get_list("tour")
        line = line.strip()
        if not line:
            # Fly to next waypoint on tour
            if len(self.list_get_links("tour")) < 1:
                print(_("End of tour."))
            else:
                url = self.list_go_to_line("1", "tour")
                if url:
                    self.list_rm_url(url, "tour")
        elif line == "ls":
            self.list_show("tour")
        elif line == "clear":
            for l in self.list_get_links("tour"):
                self.list_rm_url(l, "tour")
        elif line == "*":
            for l in self.get_renderer().get_links():
                self.list_add_line("tour", url=l, verbose=False)
        elif line == ".":
            self.list_add_line("tour", verbose=False)
        elif looks_like_url(line):
            self.list_add_line("tour", url=line)
        elif line in self.list_lists():
            list_path = self.list_path(line)
            if not list_path:
                print(REDERROR+_("List %s does not exist. Cannot add it to tour") % (list))
            else:
                url = "list:///%s" % line
                for l in self.get_renderer(url).get_links():
                    self.list_add_line("tour", url=l, verbose=False)
        elif self.current_url:
            for index in line.split():
                try:
                    pair = index.split("-")
                    if len(pair) == 1:
                        # Just a single index
                        n = int(index)
                        url = self.get_renderer().get_link(n)
                        self.list_add_line("tour", url=url, verbose=False)
                    elif len(pair) == 2:
                        # Two endpoints for a range of indices
                        if int(pair[0]) < int(pair[1]):
                            for n in range(int(pair[0]), int(pair[1]) + 1):
                                url = self.get_renderer().get_link(n)
                                self.list_add_line("tour", url=url, verbose=False)
                        else:
                            for n in range(int(pair[0]), int(pair[1]) - 1, -1):
                                url = self.get_renderer().get_link(n)
                                self.list_add_line("tour", url=url, verbose=False)

                    else:
                        # Syntax error
                        print(_("Invalid use of range syntax %s, skipping") % index)
                except ValueError:
                    print(_("Non-numeric index %s, skipping.") % index)
                except IndexError:
                    print(_("Invalid index %d, skipping.") % n)

    @needs_gi
    def do_certs(self, line) -> None:
        """Manage your client certificates (identities) for a site.
        `certs` will display all valid certificates for the current site
        `certs new <name> <days-valid> <url[optional]>` will create a new certificate, if no url is specified, the current open site will be used."""
        line = line.strip()
        if not line:
            url_with_identity = netcache.ask_certs(self.current_url)
            if url_with_identity != self.current_url:
                self.onecmd("go " + url_with_identity)
        else:
            lineparts = line.split(" ")
            if lineparts[0] == "new":
                if len(lineparts) == 4:
                    name = lineparts[1]
                    days = lineparts[2]
                    site = lineparts[3]
                    netcache.create_certificate(name, int(days), site)
                elif len(lineparts) == 3:
                    name = lineparts[1]
                    days = lineparts[2]
                    site = urllib.parse.urlparse(self.current_url)
                    netcache.create_certificate(name, int(days), site.hostname)

                else:
                    print("usage")

    @needs_gi
    def do_mark(self, line):
        """Mark the current item with a single letter.  This letter can then
        be passed to the 'go' command to return to the current item later.
        Think of it like marks in vi: 'mark a'='ma' and 'go a'=''a'.
        Marks are temporary until shutdown (not saved to disk)."""
        line = line.strip()
        if not line:
            for mark, gi in self.marks.items():
                print("[%s] %s (%s)" % (mark, gi.name, gi.url))
        elif line.isalpha() and len(line) == 1:
            self.marks[line] = self.current_url
        else:
            print(_("Invalid mark, must be one letter"))

    @needs_gi
    def do_info(self, line):
        """Display information about current page."""
        renderer = self.get_renderer()
        url = unmode_url(self.current_url)[0]
        out = renderer.get_page_title() + "\n\n"
        #TRANSLATORS: this string and "Mime", "Cache", "Renderer" are formatted to align.
        #if you can obtain the same effect in your language, try to do it ;)
        #they are displayed with the "info" command
        out += _("URL      :   ") + url + "\n"
        out += _("Mime     :   ") + renderer.get_mime() + "\n"
        out += _("Cache    :   ") + netcache.get_cache_path(url) + "\n"
        if self.get_renderer():
            rend = str(self.get_renderer().__class__)
            rend = rend.lstrip("<class '__main__.").rstrip("'>")
        else:
            rend = "None"
        out += _("Renderer :   ") + rend + "\n"
        out += _("Cleaned with : ") + renderer.get_cleanlib() + "\n\n"
        lists = []
        for l in self.list_lists():
            if self.list_has_url(url, l):
                lists.append(l)
        if len(lists) > 0:
            out += _("Page appeard in following lists :\n")
            for l in lists:
                if not self.list_is_system(l):
                    status = _("normal list")
                    if self.list_is_subscribed(l):
                        status = _("subscription")
                    elif self.list_is_frozen(l):
                        status = _("frozen list")
                    out += " • %s\t(%s)\n" % (l, status)
            for l in lists:
                if self.list_is_system(l):
                    out += " • %s\n" % l
        else:
            out += _("Page is not save in any list")
        print(out)

    def do_version(self, line):
        """Display version and system information."""

        def has(value):
            if value:
                return "\t\x1b[1;32mInstalled\x1b[0m\n"
            else:
                return "\t\x1b[1;31mNot Installed\x1b[0m\n"

        output = "Offpunk " + __version__ + "\n"
        output += "===========\n"
        output += _("System: ") + sys.platform + "\n"
        output += _("Python: ") + sys.version + "\n"
        output += _("\nHighly recommended:\n")
        output += " - xdg-open            : " + has(_HAS_XDGOPEN)
        output += _("\nWeb browsing:\n")
        output += " - python-requests     : " + has(netcache._DO_HTTP)
        output += " - python-feedparser   : " + has(ansicat._DO_FEED)
        output += " - python-bs4          : " + has(ansicat._HAS_SOUP)
        output += " - python-readability  : " + has(ansicat._HAS_READABILITY)
        output += " - timg 1.3.2+         : " + has(ansicat._HAS_TIMG)
        output += " - chafa 1.10+         : " + has(ansicat._HAS_CHAFA)
        output += _("\nNice to have:\n")
        output += " - python-setproctitle             : " + has(_HAS_SETPROCTITLE)
        output += " - python-cryptography             : " + has(netcache._HAS_CRYPTOGRAPHY)
        clip_support = shutil.which("xsel") or shutil.which("xclip")
        output += " - X11 clipboard (xsel or xclip)   : " + has(clip_support)
        output += " - Wayland clipboard (wl-clipboard): " + has(shutil.which("wl-copy"))

        output += _("\nFeatures :\n")
        output += _(" - Render images (chafa or timg)              : ") + has(
                ansicat._RENDER_IMAGE
            )
        output += _(" - Render HTML (bs4, readability)             : ") + has(
            ansicat._DO_HTML
        )
        output += _(" - Render Atom/RSS feeds (feedparser)         : ") + has(
            ansicat._DO_FEED
        )
        output += _(" - Connect to http/https (requests)           : ") + has(
            netcache._DO_HTTP
        )
        output += _(" - Detect text encoding (python-chardet)      : ") + has(
            netcache._HAS_CHARDET
        )
        output += _(" - restore last position (less 572+)          : ") + has(
            openk._LESS_RESTORE_POSITION
        )
        output += "\n"
        output += _("Config directory    : ") + xdg("config") + "\n"
        output += _("User Data directory : ") + xdg("data") + "\n"
        output += _("Cache directoy      : ") + xdg("cache")

        print(output)

    # Stuff that modifies the lookup table
    def do_search(self, line):
        """Search on Gemini using the engine configured (by default kennedy.gemi.dev)
        You can configure it using "set search URL".
        URL should contains one "%s" that will be replaced by the search term."""
        search = urllib.parse.quote(line)
        url = self.options["search"] % search
        self._go_to_url(url)

    def do_websearch(self, line):
        """Search on the web using the engine configured (by default wiby.me)
        You can configure it using "set websearch URL".
        URL should contains one "%s" that will be replaced by the search term."""
        search = urllib.parse.quote(line)
        url = self.options["websearch"] % search
        self._go_to_url(url)

    def do_wikipedia(self, line):
        """Search on wikipedia using the configured Gemini interface.
        The first word should be the two letters code for the language.
        Exemple : "wikipedia en Gemini protocol"
        But you can also use abbreviations to go faster:
        "wen Gemini protocol". (your abbreviation might be missing, report the bug)
        The interface used can be modified with the command:
        "set wikipedia URL" where URL should contains two "%s", the first
        one used for the language, the second for the search string."""
        words = line.split(" ", maxsplit=1)
        if len(words[0]) == 2:
            lang = words[0]
            search = urllib.parse.quote(words[1])
        else:
            lang = "en"
            search = urllib.parse.quote(line)
        url = self.options["wikipedia"] % (lang, search)
        self._go_to_url(url)

    def do_xkcd(self,line):
        """Open the specified XKCD comics (a number is required as parameter)"""
        words = line.split(" ")
        if len(words) > 0 and words[0].isalnum():
            self._go_to_url("https://xkcd.com/%s"%words[0])
        else:
            print(_("Please enter the number of the XKCD comic you want to see"))

    def do_gus(self, line):
        """Submit a search query to the geminispace.info search engine."""
        if not line:
            print(_("What?"))
            return
        search = urllib.parse.quote(line)
        self._go_to_url("gemini://geminispace.info/search?%s" % search)

    def do_history(self, *args):
        """Display history."""
        self.list_show("history")

    @needs_gi
    def do_find(self, searchterm):
        """Find in current page by displaying only relevant lines (grep)."""
        self._go_to_url(self.current_url, update_hist=False, grep=searchterm)

    def do_links(self, line):
        """Display all the links for the current page.
           If argument N is provided, then page through N links at a time.
           "links 10" show you the first 10 links, then 11 to 20, etc.
           if N = 0, then all the links are displayed"""
        args = line.split()
        increment = 0
        if len(args) > 0 and args[0].isdigit():
            increment = int(args[0])
        elif len(args) == 0:
            # without argument, we reset the page index
            self.page_index = 0
        i = self.page_index
        if not self.get_renderer() or i > len(self.get_renderer().get_links()):
            return
        if increment: 
            self._show_lookup(offset=i, end=i + increment)
            self.page_index += increment
        else:
            self._show_lookup()

    def do_ls(self, line):
        """DEPRECATED: List contents of current index."""
        print("ls is deprecated. Use links instead")
        self.do_links(line)


    def emptyline(self):
        """Default action when line is empty"""
        if "default_cmd" in self.options:
            cmd = self.options["default_cmd"]
        else:
            #fallback to historical links command
            cmd = "links"
        #if there’s a default command, we first run it
        #through default, in case it is an alias
        if cmd:
            success = self.default(cmd, verbose=False)
            # if no alias, we call onecmd()
            if not success:
                self.onecmd(cmd)

    @needs_gi
    def do_feed(self, *args):
        """Display RSS or Atom feeds linked to the current page."""
        subs = self.get_renderer().get_subscribe_links()
        # No feed found
        if len(subs) == 1:
            if "rss" in subs[0][1] or "atom" in subs[0][1]:
                print(_("Current page is already a feed"))
            else:
                print(_("No feed found on current page"))
        # Multiple feeds found
        elif len(subs) > 2:
            stri = _("Available feeds :\n")
            counter = 0
            for s in subs:
                counter += 1
                stri += "[%s] %s [%s]\n" % (counter, s[0], s[1])
            stri += _("Which view do you want to see ? >")
            ans = input(stri)
            if ans.isdigit() and 0 < int(ans) <= len(subs):
                self.do_go(subs[int(ans) - 1][0])
        # Only one feed found
        else:
            self.do_go(subs[1][0])

    @needs_gi
    def do_view(self, *args):
        """Run most recently visited item through "less" command, restoring \
previous position.
Use "view normal" to see the default article view on html page.
Use "view full" to see a complete html page instead of the article view.
Use "view swich" to switch between normal and full
Use "view XX" where XX is a number to view information about link XX.
(full, feed, feeds have no effect on non-html content)."""
        if self.current_url and args and args[0] != "":
            if args[0] in ["full", "debug", "source"]:
                self._go_to_url(self.current_url, mode=args[0])
            elif args[0] in ["normal", "readable"]:
                self._go_to_url(self.current_url, mode="readable")
            elif args[0] == "feed":
                #TRANSLATORS keep "view feed" and "feed" in english, those are literal commands
                print(_("view feed is deprecated. Use the command feed directly"))
                self.do_feed()
            elif args[0] == "switch":
                mode = unmode_url(self.current_url)[1]
                new_mode = "readable" if mode is not None and mode not in ["normal", "readable"] else "full"
                self._go_to_url(self.current_url, mode=new_mode)
            elif args[0].isdigit():
                link_url = self.get_renderer().get_link(int(args[0]))
                if link_url:
                    print(_("Link %s is: %s") % (args[0], link_url))
                    if netcache.is_cache_valid(link_url):
                        last_modified = netcache.cache_last_modified(link_url)
                        link_renderer = self.get_renderer(link_url)
                        if link_renderer:
                            link_title = link_renderer.get_page_title()
                            print(link_title)
                        else:
                            print(_("Empty cached version"))
                        print(_("Last cached on %s") % time.ctime(last_modified))
                    else:
                        print(_("No cached version for this link"))

            else:
                print(
                    #TRANSLATORS keep "normal, full, switch, source" in english
                    _("Valid arguments for view are : normal, full, switch, source or a number")
                )
        else:
            self._go_to_url(self.current_url)

    @needs_gi
    def do_open(self, *args):
        """Open current item with the configured handler or xdg-open.
        Use "open url" to open current URL in a browser.
        Use "open 2 4" to open links 2 and 4
        You can combine with "open url 2 4" to open URL of links
        see "handler" command to set your handler."""
        # do we open the URL (true) or the cached file (false)
        url_list = []
        urlmode = False
        arglist = args[0].split()
        if len(arglist) > 0 and arglist[0] == "url":
            arglist.pop(0)
            urlmode = True
        if len(arglist) > 0:
            # we try to match each argument with a link
            for a in arglist:
                try:
                    n = int(a)
                    u = self.get_renderer().get_link(n)
                    url_list.append(u)
                except ValueError:
                    print(_("Non-numeric index %s, skipping.") % a)
                except IndexError:
                    print(_("Invalid index %d, skipping.") % n)

        else:
            # if no argument, we use current url
            url = unmode_url(self.current_url)[0]
            url_list.append(url)
        for u in url_list:
            if urlmode:
                run("xdg-open %s", parameter=u, direct_output=True)
            else:
                self.opencache.openk(u, terminal=False)

    def do_shell(self, line):
        """Send the content of the current page to the shell and pipe it.
        You are supposed to write what will come after the pipe. For example,
        if you want to count the number of lines containing STRING in the 
        current page:
        > shell grep STRING|wc -l
        '!' is an useful shortcut.
        > !grep STRING|wc -l"""
        # input is used if we wand to send something else than current page
        # to the shell
        tmp = None
        if self.current_url:
            tmp = self.opencache.get_temp_filename(self.current_url)
        if tmp:
            input = open(tmp, "rb")
            run(line, input=input, direct_output=True)
        else:
            run(line,direct_output=True)


    @needs_gi
    def do_save(self, line):
        """Save an item to the filesystem.
        'save n filename' saves menu item n to the specified filename.
        'save filename' saves the last viewed item to the specified filename.
        'save n' saves menu item n to an automagic filename."""
        args = line.strip().split()
        # First things first, figure out what our arguments are
        if len(args) == 0:
            # No arguments given at all
            # Save current item, if there is one, to a file whose name is
            # inferred from the gemini path
            if not netcache.is_cache_valid(self.current_url):
                print(_("You cannot save if not cached!"))
                return
            else:
                index = None
                filename = None
        elif len(args) == 1:
            # One argument given
            # If it's numeric, treat it as an index, and infer the filename
            try:
                index = int(args[0])
                filename = None
            # If it's not numeric, treat it as a filename and
            # save the current item
            except ValueError:
                index = None
                filename = os.path.expanduser(args[0])
        elif len(args) == 2:
            # Two arguments given
            # Treat first as an index and second as filename
            index, filename = args
            try:
                index = int(index)
            except ValueError:
                print(_("First argument is not a valid item index!"))
                return
            filename = os.path.expanduser(filename)
        else:
            print(_("You must provide an index, a filename, or both."))
            return
        # Next, fetch the item to save, if it's not the current one.
        if index:
            last_url = self.current_url
            try:
                url = self.get_renderer().get_link(index)
                self._go_to_url(url, update_hist=False, handle=False)
            except IndexError:
                print(_("Index too high!"))
                self.current_url = last_url
                return
        else:
            url = self.current_url

        # Derive filename from current GI's path, if one hasn't been set
        if not filename:
            filename = os.path.basename(netcache.get_cache_path(self.current_url))
        # Check for filename collisions and actually do the save if safe
        if os.path.exists(filename):
            print(_("File %s already exists!") % filename)
        else:
            # Don't use _get_active_tmpfile() here, because we want to save the
            # "source code" of menus, not the rendered view - this way Offpunk
            # can navigate to it later.
            path = netcache.get_cache_path(url)
            if os.path.isdir(path):
                print(_("Can’t save %s because it’s a folder, not a file") % path)
            else:
                print(_("Saved to %s") % filename)
                shutil.copyfile(path, filename)

        # Restore gi if necessary
        if index is not None:
            self._go_to_url(last_url, handle=False)

    @needs_gi
    def do_url(self, args):
        """Print the url of the current page.
        Use "url XX" where XX is a number to print the url of link XX.
        "url" can also be piped to the shell, using the pipe "|"."""
        splitted = args.split("|",maxsplit=1)
        url = None
        final_url = None
        if splitted[0].strip().isdigit():
            link_id = int(splitted[0])
            link_url = self.get_renderer().get_link(link_id)
            if link_url:
                url = link_url
        else:
            url = self.current_url
        if url:
            final_url = unmode_url(url)[0]
            print(final_url)
        if final_url and len(splitted) > 1:
            run(splitted[1], input=final_url, direct_output=True)

    # Bookmarking stuff
    @needs_gi
    def do_add(self, line):
        """Add the current URL to the list specified as argument.
        If no argument given, URL is added to Bookmarks.
        You can pass a link number as the second argument to add the link.
        "add $LIST XX" will add link number XX to $LIST"""
        args = line.split()
        if len(args) < 1:
            list = "bookmarks"
            if not self.list_path(list):
                self.list_create(list)
            self.list_add_line(list)
        elif len(args) > 1 and args[1].isdigit():
            link_id = int(args[1])
            link_url = self.get_renderer().get_link(link_id)
            if link_url:
                self.list_add_line(args[0],url=link_url)
        else:
            self.list_add_line(args[0])

    # Get the list file name, creating or migrating it if needed.
    # Migrate bookmarks/tour/to_fetch from XDG_CONFIG to XDG_DATA
    # We migrate only if the file exists in XDG_CONFIG and not XDG_DATA
    def get_list(self, list):
        list_path = self.list_path(list)
        if not list_path:
            old_file_gmi = os.path.join(xdg("config"), list + ".gmi")
            old_file_nogmi = os.path.join(xdg("config"), list)
            target = os.path.join(xdg("data"), "lists")
            if os.path.exists(old_file_gmi):
                shutil.move(old_file_gmi, target)
            elif os.path.exists(old_file_nogmi):
                targetgmi = os.path.join(target, list + ".gmi")
                shutil.move(old_file_nogmi, targetgmi)
            else:
                if list == "subscribed":
                    title = _("Subscriptions #subscribed (new links in those pages will be added to tour)")
                elif list == "to_fetch":
                    title = _("Links requested and to be fetched during the next --sync")
                else:
                    title = None
                self.list_create(list, title=title, quite=True)
                list_path = self.list_path(list)
        return list_path

    @needs_gi
    def do_subscribe(self, line):
        """Subscribe to current page by saving it in the "subscribed" list.
        If a new link is found in the page during a --sync, the new link is automatically
        fetched and added to your next tour.
        To unsubscribe, remove the page from the "subscribed" list."""
        subs = self.get_renderer().get_subscribe_links()
        if len(subs) > 1:
            stri = _("Multiple feeds have been found :\n")
        elif "rss" in subs[0][1] or "atom" in subs[0][1]:
            stri = _("This page is already a feed:\n")
        else:
            stri = _("No feed detected. You can still watch the page :\n")
        counter = 0
        for l in subs:
            link = l[0]
            already = []
            for li in self.list_lists():
                if self.list_is_subscribed(li):
                    if self.list_has_url(link, li):
                        already.append(li)
            stri += "[%s] %s [%s]\n" % (counter + 1, link, l[1])
            if len(already) > 0:
                stri += _("\t -> (already subscribed through lists %s)\n") % (str(already))
            counter += 1
        stri += "\n"
        stri += _("Which feed do you want to subscribe ? > ")
        ans = input(stri)
        if ans.isdigit() and 0 < int(ans) <= len(subs):
            sublink = subs[int(ans) - 1][0]
        else:
            sublink = None
        if sublink:
            added = self.list_add_line("subscribed", url=sublink, verbose=False)
            if added:
                print(_("Subscribed to %s") % sublink)
            else:
                print(_("You are already subscribed to %s") % sublink)
        else:
            print(_("No subscription registered"))

    def do_bookmarks(self, line):
        """Show or access the bookmarks menu.
        'bookmarks' shows all bookmarks.
        'bookmarks n' navigates immediately to item n in the bookmark menu.
        Bookmarks are stored using the 'add' command."""
        args = line.strip()
        if len(args.split()) > 1 or (args and not args.isnumeric()):
            print(_("bookmarks command takes a single integer argument!"))
        elif args:
            self.list_go_to_line(args, "bookmarks")
        else:
            self.list_show("bookmarks")

    @needs_gi
    def do_archive(self, args):
        """Archive current page by removing it from every list and adding it to
        archives, which is a special historical list limited in size. It is similar to `move archives`."""
        url = unmode_url(self.current_url)[0]
        for li in self.list_lists():
            if li not in ["archives", "history"]:
                deleted = self.list_rm_url(url, li)
                if deleted:
                    print(_("Removed from %s") % li)
        self.list_add_top("archives", limit=self.options["archives_size"])
        r = self.get_renderer()
        title = r.get_page_title()
        print(_("Archiving: %s") % title)
        print(
            _("\x1b[2;34mCurrent maximum size of archives : %s\x1b[0m")
            % self.options["archives_size"]
        )

    # what is the line to add to a list for this url ?
    def to_map_line(self, url=None):
        if not url:
            url = self.current_url
        r = self.get_renderer(url)
        if r:
            title = r.get_page_title()
        else:
            title = ""
        toreturn = "=> {} {}\n".format(url, title)
        return toreturn

    def list_add_line(self, list, url=None, verbose=True):
        list_path = self.list_path(list)
        if not list_path and self.list_is_system(list):
            self.list_create(list, quite=True)
            list_path = self.list_path(list)
        if not list_path:
            print(REDERROR+
                _("List %s does not exist. Create it with "
                "list create %s"
                "") % (list, list)
            )
            return False
        else:
            if not url:
                url = self.current_url
            unmoded_url, mode = unmode_url(url)
            # first we check if url already exists in the file
            if self.list_has_url(url, list, exact_mode=True):
                if verbose:
                    print(_("%s already in %s.") % (url, list))
                return False
            # If the URL already exists but without a mode, we update the mode
            # FIXME: this doesn’t take into account the case where you want to remove the mode
            elif url != unmoded_url and self.list_has_url(unmoded_url, list):
                self.list_update_url_mode(unmoded_url, list, mode)
                if verbose:
                    print(_("%s has updated mode in %s to %s") % (url, list, mode))
            else:
                with open(list_path, "a") as l_file:
                    l_file.write(self.to_map_line(url))
                    l_file.close()
                if verbose:
                    #TRANSLATORS parameters are url, list
                    print(_("%s added to %s") % (url, list))
                return True

    @needs_gi
    def list_add_top(self, list, limit=0, truncate_lines=0):
        stri = self.to_map_line().strip("\n")
        if list == "archives":
            stri += _(", archived on ")
        elif list == "history":
            stri += _(", visited on ")
        else:
            #TRANSLATORS parameter is a "list" name
            stri += _(", added to %s on ") % list
        stri += time.ctime() + "\n"
        list_path = self.get_list(list)
        with open(list_path, "r") as l_file:
            lines = l_file.readlines()
            l_file.close()
        with open(list_path, "w") as l_file:
            l_file.write("#%s\n" % list)
            l_file.write(stri)
            counter = 0
            # Truncating is useful in case we open a new branch
            # after a few back in history
            to_truncate = truncate_lines
            for l in lines:
                if not l.startswith("#"):
                    if to_truncate > 0:
                        to_truncate -= 1
                    elif limit == 0 or counter < limit:
                        l_file.write(l)
                        counter += 1
            l_file.close()

    # remove an url from a list.
    # return True if the URL was removed
    # return False if the URL was not found
    def list_rm_url(self, url, list):
        return self.list_has_url(url, list, deletion=True)

    def list_update_url_mode(self, url, list, mode):
        return self.list_has_url(url, list, update_mode=mode)

    # deletion and has_url are so similar, I made them the same method
    # deletion : true or false if you want to delete the URL
    # exact_mode : True if you want to check only for the exact url, not the canonical one
    # update_mode : a new mode to update the URL
    def list_has_url(
        self, url, list, deletion=False, exact_mode=False, update_mode=None
    ):
        list_path = self.list_path(list)
        if list_path:
            to_return = False
            with open(list_path, "r") as lf:
                lines = lf.readlines()
                lf.close()
            to_write = []
            # let’s remove the mode
            if not exact_mode:
                url = unmode_url(url)[0]
            for l in lines:
                # we separate components of the line
                # to ensure we identify a complete URL, not a part of it
                splitted = l.split()
                if url not in splitted and len(splitted) > 1:
                    current = unmode_url(splitted[1])[0]
                    # sometimes, we must remove the ending "/"
                    if url == current or (url.endswith("/") and url[:-1] == current):
                        to_return = True
                        if update_mode:
                            new_line = l.replace(current, mode_url(url, update_mode))
                            to_write.append(new_line)
                        elif not deletion:
                            to_write.append(l)
                    else:
                        to_write.append(l)
                elif url in splitted:
                    to_return = True
                    # We update the mode if asked by replacing the old url
                    # by a moded one in the same line
                    if update_mode:
                        new_line = l.replace(url, mode_url(url, update_mode))
                        to_write.append(new_line)
                    elif not deletion:
                        to_write.append(l)
                else:
                    to_write.append(l)
            if deletion or update_mode:
                with open(list_path, "w") as lf:
                    for l in to_write:
                        lf.write(l)
                    lf.close()
            return to_return
        else:
            return False

    def list_get_links(self, list):
        list_path = self.list_path(list)
        if list_path and os.path.exists(list_path):
            return self.get_renderer("list:///%s" % list).get_links()
        else:
            return []

    def list_go_to_line(self, line, list):
        list_path = self.list_path(list)
        if not list_path:
            print(
                _("List %s does not exist. Create it with "
                "list create %s"
                "") % (list, list)
            )
        elif not line.isnumeric():
            #TRANSLATORS keep 'go_to_line' as is
            print(_("go_to_line requires a number as parameter"))
        else:
            r = self.get_renderer("list:///%s" % list)
            url = r.get_link(int(line))
            display = not self.sync_only
            if url:
                self._go_to_url(url, handle=display)
                return url

    def list_show(self, list):
        list_path = self.list_path(list)
        if not list_path:
            print(REDERROR+
                _("List %s does not exist. Create it with "
                "list create %s"
                "") % (list, list)
            )
        else:
            url = "list:///%s" % list
            display = not self.sync_only
            self._go_to_url(url, handle=display)

    # return the path of the list file if list exists.
    # return None if the list doesn’t exist.
    def list_path(self, list):
        listdir = os.path.join(xdg("data"), "lists")
        list_path = os.path.join(listdir, "%s.gmi" % list)
        if os.path.exists(list_path):
            return list_path
        else:
            return None

    def list_create(self, list, title=None, quite=False):
        list_path = self.list_path(list)
        if list in ["create", "edit", "delete", "help"]:
            print(_("%s is not allowed as a name for a list") % list)
        elif not list_path:
            listdir = os.path.join(xdg("data"), "lists")
            os.makedirs(listdir, exist_ok=True)
            list_path = os.path.join(listdir, "%s.gmi" % list)
            with open(list_path, "a") as lfile:
                if title:
                    lfile.write("# %s\n" % title)
                else:
                    lfile.write("# %s\n" % list)
                lfile.close()
            if not quite:
                print(_("list created. Display with `list %s`") % list)
        else:
            print(_("list %s already exists") % list)

    def do_move(self, arg):
        """move LIST will add the current page to the list LIST.
        With a major twist: current page will be removed from all other lists.
        If current page was not in a list, this command is similar to `add LIST`."""
        if not arg:
            print(_("LIST argument is required as the target for your move"))
        elif arg[0] == "archives":
            self.do_archive()
        else:
            args = arg.split()
            list_path = self.list_path(args[0])
            if not list_path:
                print(_("%s is not a list, aborting the move") % args[0])
            else:
                lists = self.list_lists()
                for l in lists:
                    if l != args[0] and l not in ["archives", "history"]:
                        url = unmode_url(self.current_url)[0]
                        isremoved = self.list_rm_url(url, l)
                        if isremoved:
                            print(_("Removed from %s") % l)
                self.list_add_line(args[0])

    def list_lists(self):
        listdir = os.path.join(xdg("data"), "lists")
        to_return = []
        if os.path.exists(listdir):
            lists = os.listdir(listdir)
            if len(lists) > 0:
                for l in lists:
                    # Taking only files with .gmi
                    if l.endswith(".gmi"):
                        # removing the .gmi at the end of the name
                        to_return.append(l[:-4])
        return to_return

    def list_has_status(self, list, status):
        path = self.list_path(list)
        toreturn = False
        if path:
            with open(path) as f:
                line = f.readline().strip()
                f.close()
            if line.startswith("#") and status in line:
                toreturn = True
        return toreturn

    def list_is_subscribed(self, list):
        return self.list_has_status(list, "#subscribed")

    def list_is_frozen(self, list):
        return self.list_has_status(list, "#frozen")

    def list_is_system(self, list):
        return list in ["history", "to_fetch", "archives", "tour"]

    # This modify the status of a list to one of :
    # normal, frozen, subscribed
    # action is either #frozen, #subscribed or None
    def list_modify(self, list, action=None):
        path = self.list_path(list)
        with open(path) as f:
            lines = f.readlines()
            f.close()
        if lines[0].strip().startswith("#"):
            first_line = lines.pop(0).strip("\n")
        else:
            first_line = "# %s " % list
        first_line = first_line.replace("#subscribed", "").replace("#frozen", "")
        if action:
            first_line += " " + action
            print(_("List %s has been marked as %s") % (list, action))
        else:
            print(_("List %s is now a normal list") % list)
        first_line += "\n"
        lines.insert(0, first_line)
        with open(path, "w") as f:
            for line in lines:
                f.write(line)
            f.close()

    def do_list(self, arg):
        """Manage list of bookmarked pages.
        - list : display available lists
        - list $LIST : display pages in $LIST
        - list create $NEWLIST : create a new list
        - list edit $LIST : edit the list
        - list subscribe $LIST : during sync, add new links found in listed pages to tour
        - list freeze $LIST : don’t update pages in list during sync if a cache already exists
        - list normal $LIST : update pages in list during sync but don’t add anything to tour
        - list delete $LIST : delete a list permanently (a confirmation is required)
        - list help : print this help
        See also :
        - add $LIST (to add current page to $LIST or, by default, to bookmarks)
        - move $LIST (to add current page to list while removing from all others)
        - archive (to remove current page from all lists while adding to archives)

        There’s no "delete" on purpose. The use of "archive" is recommended.

        The following lists cannot be removed or frozen but can be edited with "list edit"
        - list archives  : contains last 200 archived URLs
        - history        : contains last 200 visisted URLs
        - to_fetch       : contains URLs that will be fetch during the next sync
        - tour           : contains the next URLs to visit during a tour (see "help tour")"""

        listdir = os.path.join(xdg("data"), "lists")
        os.makedirs(listdir, exist_ok=True)
        if not arg:
            lists = self.list_lists()
            if len(lists) > 0:
                lurl = "list:///"
                self._go_to_url(lurl)
            else:
                print(_("No lists yet. Use `list create`"))
        else:
            args = arg.split()
            if args[0] == "create":
                if len(args) > 2:
                    name = " ".join(args[2:])
                    self.list_create(args[1].lower(), title=name)
                elif len(args) == 2:
                    self.list_create(args[1].lower())
                else:
                    print(
                        _("A name is required to create a new list. Use `list create NAME`")
                    )
            elif args[0] == "edit":
                editor = None
                if "editor" in self.options and self.options["editor"]:
                    editor = self.options["editor"]
                elif os.environ.get("VISUAL"):
                    editor = os.environ.get("VISUAL")
                elif os.environ.get("EDITOR"):
                    editor = os.environ.get("EDITOR")
                if editor:
                    if len(args) > 1 and args[1] in self.list_lists():
                        path = os.path.join(listdir, args[1] + ".gmi")
                        try:
                            # Note that we intentionally don't quote the editor.
                            # In the unlikely case `editor` includes a percent
                            # sign, we also escape it for the %-formatting.
                            cmd = editor.replace("%", "%%") + " %s"
                            run(cmd, parameter=path, direct_output=True)
                        except Exception as err:
                            print(err)
                            print(_('Please set a valid editor with "set editor"'))
                    else:
                        print(_("A valid list name is required to edit a list"))
                else:
                    print(_("No valid editor has been found."))
                    print(
                        _("You can use the following command to set your favourite editor:")
                    )
                    #TRANSLATORS keep 'set editor', it's a command
                    print(_("set editor EDITOR"))
                    print(_("or use the $VISUAL or $EDITOR environment variables."))
            elif args[0] == "delete":
                if len(args) > 1:
                    if self.list_is_system(args[1]):
                        print(_("%s is a system list which cannot be deleted") % args[1])
                    elif args[1] in self.list_lists():
                        size = len(self.list_get_links(args[1]))
                        stri = _("Are you sure you want to delete %s ?\n") % args[1]
                        confirm = "YES"
                        if size > 0:
                            stri += _("! %s items in the list will be lost !\n") % size
                            confirm = "YES DELETE %s" % size
                        else:
                            stri += (
                                _("The list is empty, it should be safe to delete it.\n")
                            )
                        stri += (
                            _('Type "%s" (in capital, without quotes) to confirm :')
                            % confirm
                        )
                        answer = input(stri)
                        if answer == confirm:
                            path = os.path.join(listdir, args[1] + ".gmi")
                            os.remove(path)
                            print(_("* * * %s has been deleted") % args[1])
                    else:
                        print(_("A valid list name is required to be deleted"))
                else:
                    print(_("A valid list name is required to be deleted"))
            elif args[0] in ["subscribe", "freeze", "normal"]:
                if len(args) > 1:
                    if self.list_is_system(args[1]):
                        print(_("You cannot modify %s which is a system list") % args[1])
                    elif args[1] in self.list_lists():
                        if args[0] == "subscribe":
                            action = "#subscribed"
                        elif args[0] == "freeze":
                            action = "#frozen"
                        else:
                            action = None
                        self.list_modify(args[1], action=action)
                else:
                    print(_("A valid list name is required after %s") % args[0])
            elif args[0] == "help":
                self.onecmd("help list")
            elif len(args) == 1:
                self.list_show(args[0].lower())
            else:
                self.list_go_to_line(args[1], args[0].lower())

    def do_help(self, arg):
        """ALARM! Recursion detected! ALARM! Prepare to eject!"""
        if arg == "help":
            print(_("Need help from a fellow human? Simply send an email to the offpunk-users list."))
            dest = "~lioploum/offpunk-users@lists.sr.ht"
            subject = "Getting started with Offpunk"
            body = "Describe your problem/question as clearly as possible.\n" + \
                   "Don’t forget to present yourself and why you would like to use Offpunk!\n"\
                    + "\n" + \
                    "Another point: always use \"reply-all\" when replying to this list."
            send_email(dest,subject=subject,body=body,toconfirm=True)
        elif arg == "!":
            print(_("! is an alias for 'shell'"))
        elif arg == "?":
            print(_("? is an alias for 'help'"))
        elif arg in _ABBREVS:
            full_cmd = _ABBREVS[arg]
            print(_("%s is an alias for '%s'") % (arg, full_cmd))
            print(_("See the list of aliases with 'abbrevs'"))
            print(_("'help %s':") % full_cmd)
            self.do_help(full_cmd)
        else:
            try:
                print(_(getattr(self, 'do_' + arg).__doc__))
            except AttributeError:
                cmd.Cmd.do_help(self, arg)

    def do_tutorial(self, arg):
        """Access the offpunk.net tutorial (online)"""
        self._go_to_url("gemini://offpunk.net/firststeps.gmi")

    def do_sync(self, line):
        """Synchronize all bookmarks lists and URLs from the to_fetch list.
        - New elements in pages in subscribed lists will be added to tour
        - Elements in list to_fetch will be retrieved and added to tour
        - Normal lists will be synchronized and updated
        - Frozen lists will be fetched only if not present.

        Before a sync, you can edit the list of URLs that will be fetched with the
        following command: "list edit to_fetch"

        Argument : duration of cache validity (in seconds)."""
        if self.offline_only:
            print(_("Sync can only be achieved online. Change status with `online`."))
            return
        args = line.split()
        if len(args) > 0:
            if not args[0].isdigit():
                print(_("sync argument should be the cache validity expressed in seconds"))
                return
            else:
                validity = int(args[0])
        else:
            validity = 0
        self.call_sync(refresh_time=validity)

    def call_sync(self, refresh_time=0, depth=1, lists=None):
        # fetch_url is the core of the sync algorithm.
        # It takes as input :
        # - an URL to be fetched
        # - depth : the degree of recursion to build the cache (0 means no recursion)
        # - validity : the age, in seconds, existing caches need to have before
        #               being refreshed (0 = never refreshed if it already exists)
        # - savetotour : if True, newly cached items are added to tour
        def add_to_tour(url):
            if url and netcache.is_cache_valid(url):
                toprint = _("  -> adding to tour: %s") % url
                width = term_width() - 1
                toprint = toprint[:width]
                toprint += " " * (width - len(toprint))
                print(toprint)
                self.list_add_line("tour", url=url, verbose=False)
                return True
            else:
                return False

        def fetch_url(
            url, depth=0, validity=0, savetotour=False, count=[0, 0], strin="",
            force_large_download=False
        ):
            # savetotour = True will save to tour newly cached content
            # else, do not save to tour
            # regardless of valitidy
            if not url:
                return
            if not netcache.is_cache_valid(url, validity=validity):
                if strin != "":
                    endline = "\r"
                else:
                    endline = None
                # Did we already had a cache (even an old one) ?
                isnew = not netcache.is_cache_valid(url)
                toprint = _("%s [%s/%s] Fetch ") % (strin, count[0], count[1]) + url
                width = term_width() - 1
                toprint = toprint[:width]
                toprint += " " * (width - len(toprint))
                print(toprint, end=endline)
                # If not saving to tour, then we should limit download size
                limit = not savetotour
                self._go_to_url(url, update_hist=False, limit_size=limit,\
                        force_large_download=force_large_download)
                if savetotour and isnew and netcache.is_cache_valid(url):
                    # we add to the next tour only if we managed to cache
                    # the ressource
                    add_to_tour(url)
            # Now, recursive call, even if we didn’t refresh the cache
            # This recursive call is impacting performances a lot but is needed
            # For the case when you add a address to a list to read later
            # You then expect the links to be loaded during next refresh, even
            # if the link itself is fresh enough
            # see fetch_list()
            if depth > 0:
                # we should only savetotour at the first level of recursion
                # The code for this was removed so, currently, we savetotour
                # at every level of recursion.
                r = self.get_renderer(url)
                url, oldmode = unmode_url(url)
                if oldmode == "full":
                    mode = "full_links_only"
                else:
                    mode = "links_only"
                if r:
                    links = r.get_links(mode=mode)
                    subcount = [0, len(links)]
                    d = depth - 1
                    for k in links:
                        # recursive call (validity is always 0 in recursion)
                        substri = strin + " -->"
                        subcount[0] += 1
                        fetch_url(
                            k,
                            depth=d,
                            validity=0,
                            savetotour=savetotour,
                            count=subcount,
                            strin=substri,
                        )

        def fetch_list(
            list, validity=0, depth=1, tourandremove=False, tourchildren=False,
            force_large_download=False
        ):
            links = self.list_get_links(list)
            end = len(links)
            counter = 0
            print(_(" * * * %s to fetch in %s * * *") % (end, list))
            for l in links:
                counter += 1
                # If cache for a link is newer than the list
                fetch_url(
                    l,
                    depth=depth,
                    validity=validity,
                    savetotour=tourchildren,
                    count=[counter, end],
                    force_large_download=force_large_download
                )
                if tourandremove:
                    if add_to_tour(l):
                        self.list_rm_url(l, list)

        self.sync_only = True
        if not lists:
            lists = self.list_lists()
        # We will fetch all the lists except "archives" and "history"
        # We keep tour for the last round
        subscriptions = []
        normal_lists = []
        fridge = []
        for l in lists:
            # only try existing lists
            if l in self.list_lists():
                if not self.list_is_system(l):
                    if self.list_is_frozen(l):
                        fridge.append(l)
                    elif self.list_is_subscribed(l):
                        subscriptions.append(l)
                    else:
                        normal_lists.append(l)
        # We start with the "subscribed" as we need to find new items
        starttime = int(time.time())
        for l in subscriptions:
            fetch_list(l, validity=refresh_time, depth=depth, tourchildren=True)
        # Then the to_fetch list (item are removed from the list after fetch)
        # We fetch regarless of the refresh_time
        if "to_fetch" in lists:
            nowtime = int(time.time())
            short_valid = nowtime - starttime
            fetch_list(
                "to_fetch", validity=short_valid, depth=depth, tourandremove=True,
                force_large_download=True
            )
        # then we fetch all the rest (including bookmarks and tour)
        for l in normal_lists:
            fetch_list(l, validity=refresh_time, depth=depth)
        for l in fridge:
            fetch_list(l, validity=0, depth=depth)
        # tour should be the last one as item my be added to it by others
        fetch_list("tour", validity=refresh_time, depth=depth)
        print(_("End of sync"))
        self.sync_only = False

    # The end!
    def do_quit(self, *args):
        """Exit Offpunk."""
        self.opencache.cleanup()
        print(_("You can close your screen!"))
        sys.exit()

    do_exit = do_quit


# Main function
def main():
    # Parse args
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bookmarks", action="store_true", help=_("start with your list of bookmarks")
    )
    parser.add_argument(
        "--command",
        metavar="COMMAND",
        nargs="*",
        help=_("Launch this command after startup"),
    )
    parser.add_argument(
        "--config-file",
        metavar="FILE",
        help=_("use this particular config file instead of default"),
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help=_("run non-interactively to build cache by exploring lists passed \
                                as argument. Without argument, all lists are fetched."),
    )
    parser.add_argument(
        "--assume-yes",
        action="store_true",
        help=_("assume-yes when asked questions about certificates/redirections during sync (lower security)"),
    )
    parser.add_argument(
        "--disable-http",
        action="store_true",
        help=_("do not try to get http(s) links (but already cached will be displayed)"),
    )
    parser.add_argument(
        "--fetch-later",
        action="store_true",
        help=_("run non-interactively with an URL as argument to fetch it later"),
    )
    parser.add_argument(
        "--depth",
        help=_("depth of the cache to build. Default is 1. More is crazy. Use at your own risks!"),
    )
    parser.add_argument(
        "--images-mode",
        help=_("the mode to use to choose which images to download in a HTML page.\
                             one of (None, readable, full). Warning: full will slowdown your sync."),
    )
    parser.add_argument(
        "--cache-validity",
        help=_("duration for which a cache is valid before sync (seconds)"),
    )
    parser.add_argument(
        "--version", action="store_true", help=_("display version information and quit")
    )
    parser.add_argument(
        "--features",
        action="store_true",
        help=_("display available features and dependancies then quit"),
    )
    parser.add_argument(
        "url",
        metavar="URL",
        nargs="*",
        help=_("Arguments should be URL to be fetched or, if --sync is used, lists"),
    )
    args = parser.parse_args()

    # Handle --version
    if args.version:
        print("Offpunk " + __version__)
        sys.exit()
    elif args.features:
        GeminiClient.do_version(None, None)
        sys.exit()
    else:
        for f in [xdg("config"), xdg("data")]:
            if not os.path.exists(f):
                print(_("Creating config directory {}").format(f))
                os.makedirs(f)

    # Instantiate client
    gc = GeminiClient(sync_only=args.sync)
    torun_queue = []

    # Act on args
    if args.bookmarks:
        torun_queue.append("bookmarks")
    elif args.url and not args.sync:
        if len(args.url) == 1:
            torun_queue.append("go %s" % args.url[0])
        else:
            for url in args.url:
                torun_queue.append("tour %s" % url)
            torun_queue.append("tour")

    if args.disable_http:
        gc.support_http = False

    # Endless interpret loop (except while --sync or --fetch-later)
    if args.fetch_later:
        if args.url:
            gc.sync_only = True
            for u in args.url:
                if looks_like_url(u):
                    if netcache.is_cache_valid(u):
                        gc.list_add_line("tour", u)
                    else:
                        gc.list_add_line("to_fetch", u)
                else:
                    print(_("%s is not a valid URL to fetch") % u)
        else:
            print(_("--fetch-later requires an URL (or a list of URLS) as argument"))
    elif args.sync:
        if args.assume_yes:
            gc.onecmd("set accept_bad_ssl_certificates True")
        if args.cache_validity:
            refresh_time = int(args.cache_validity)
        else:
            # if no refresh time, a default of 0 is used (which means "infinite")
            refresh_time = 0
        if args.images_mode and args.images_mode in [
            "none",
            "readable",
            "normal",
            "full",
        ]:
            gc.options["images_mode"] = args.images_mode
        if args.depth:
            depth = int(args.depth)
        else:
            depth = 1
        torun_queue += init_config(rcfile=args.config_file, interactive=False)
        for line in torun_queue:
            # This doesn’t seem to run on sync. Why?
            gc.onecmd(line)
        gc.call_sync(refresh_time=refresh_time, depth=depth, lists=args.url)
    else:
        # We are in the normal mode. First process config file
        torun_queue += init_config(rcfile=args.config_file,interactive=True)
        print(_("Welcome to Offpunk!"))
        #TRANSLATORS keep 'help', it's a literal command
        print(_("Type `help` to get the list of available command."))
        for line in torun_queue:
            gc.onecmd(line)
        if args.command:
            for cmd in args.command:
                gc.onecmd(cmd)
        while True:
            try:
                gc.cmdloop()
            except KeyboardInterrupt:
                print("")


if __name__ == "__main__":
    main()
