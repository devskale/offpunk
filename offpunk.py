#!/usr/bin/env python3
# Offpunk Offline Gemini client
"""
Offline-First Gemini/Web/Gopher/RSS reader and browser
"""

__version__ = "2.3"

## Initial imports and conditional imports {{{
import argparse
import cmd
import datetime
import io
import os
import os.path
import filecmp
import random
import shlex
import shutil
import socket
import sys
import time
import urllib.parse
import subprocess
import netcache
import opnk
import ansicat
import offthemes
from offutils import run,term_width,is_local,mode_url,unmode_url, looks_like_url
from offutils import xdg
import offblocklist
try:
    import setproctitle
    setproctitle.setproctitle("offpunk")
    _HAS_SETPROCTITLE = True
except ModuleNotFoundError:
    _HAS_SETPROCTITLE = False

#This method copy a string to the system clipboard
def clipboard_copy(to_copy):
    copied = False
    if shutil.which('xsel'):
        run("xsel -b -i", input=to_copy, direct_output=True)
        copied = True
    if shutil.which('xclip'):
        run("xclip -selection clipboard", input=to_copy, direct_output=True)
        copied = True
    if shutil.which('wl-copy'):
        run("wl-copy", input=to_copy, direct_output=True)
        copied = True
    if not copied:
        print("Install xsel/xclip (X11) or wl-clipboard (Wayland) to use copy")
#This method returns an array with all the values in all system clipboards
def clipboard_paste():
    #We use a set to avoid duplicates
    clipboards = set()
    cmds = set()
    pasted = False
    if shutil.which('xsel'):
        pasted = True
        for selec in ["-p","-s","-b"]:
            cmds.add("xsel "+selec)
    if shutil.which('xclip'):
        pasted = True
        for selec in ["clipboard","primary","secondary"]:
            cmds.add("xsel "+selec)
    if shutil.which('wl-paste'):
        pasted = True
        for selec in ["", "-p"]:
            cmds.add("wl-paste "+selec)
    for cmd in cmds:
        try:
            clipboards.add(run(cmd))
        except Exception as err:
            #print("Skippink clipboard %s because %s"%(selec,err))
            pass
    if not pasted: 
        print("Install xsel/xclip (X11) or wl-clipboard (Wayland) to get URLs from your clipboard")
    return list(clipboards)


## }}} end of imports

# Command abbreviations
_ABBREVS = {
    "..":   "up",
    "a":    "add",
    "b":    "back",
    "bb":   "blackbox",
    "bm":   "bookmarks",
    "book": "bookmarks",
    "cp":   "copy",
    "f":   "forward",
    "g":    "go",
    "h":    "history",
    "hist": "history",
    "l":    "view",
    "less": "view",
    "man":  "help",
    "mv":   "move",
    "n":    "next",
    "off":  "offline",
    "on":   "online",
    "p":    "previous",
    "prev": "previous",
    "q":    "quit",
    "r":    "reload",
    "s":    "save",
    "se":   "search",
    "/":    "find",
    "t":    "tour",
    "u":    "up",
    "v":    "view",
    "w":    "wikipedia",
    "wen":  "wikipedia en",
    "wfr":  "wikipedia fr",
    "wes":  "wikipedia es",
}

_MIME_HANDLERS = {
}

# GeminiClient Decorators
def needs_gi(inner):
    def outer(self, *args, **kwargs):
        if not self.current_url:
            print("You need to 'go' somewhere, first")
            return None
        else:
            return inner(self, *args, **kwargs)
    outer.__doc__ = inner.__doc__
    return outer

class GeminiClient(cmd.Cmd):
    def __init__(self, completekey="tab", synconly=False):
        cmd.Cmd.__init__(self)
        # Set umask so that nothing we create can be read by anybody else.
        # The certificate cache and TOFU database contain "browser history"
        # type sensitivie information.
        os.umask(0o077)
        self.opencache = opnk.opencache()
        self.theme = offthemes.default
        self.set_prompt("ON")
        self.current_url = None
        self.hist_index = 0
        self.marks = {}
        self.page_index = 0
        self.permanent_redirects = {}
        # Sync-only mode is restriced by design
        self.offline_only = False
        self.sync_only = False
        self.support_http = netcache._DO_HTTP
        self.automatic_choice = "n"
        self.client_certs = {
            "active": None
        }
        self.active_cert_domains = []
        self.active_is_transient = False
        self.options = {
            "debug" : False,
            "beta" : False,
            "timeout" : 600,
            "short_timeout" : 5,
            "width" : 72,
            "auto_follow_redirects" : True,
            "tls_mode" : "tofu",
            "archives_size" : 200,
            "history_size" : 200,
            "max_size_download" : 10,
            "editor" : None,
            "download_images_first" : True,
            "images_mode" : "readable",
            "redirects" : True,
            # the wikipedia entry needs two %s, one for lang, other for search
            "wikipedia" : "gemini://vault.transjovian.org:1965/search/%s/%s",
            "search"    : "gemini://kennedy.gemi.dev/search?%s",
            "accept_bad_ssl_certificates" : False,
            "default_protocol" : "gemini",
        }
        self.redirects = offblocklist.redirects
        for i in offblocklist.blocked:
            self.redirects[i] = "blocked"
        term_width(new_width=self.options["width"])
        self.log = {
            "start_time": time.time(),
        }

    def set_prompt(self,prompt):
        key = "prompt_%s"%prompt.lower()
        if key in self.theme:
            colors = self.theme[key]
        else:
            #default color is green
            colors = ["green"]
        open_color = ""
        close_color = ""
        for c in colors:
            if c in offthemes.colors:
                ansi = offthemes.colors[c]
            else:
                ansi = ["32","39"]
            open_color += "%s;"%ansi[0]
            close_color += "%s;"%ansi[1]
        #removing the last ";"
        if open_color.endswith(";"):
            open_color = open_color[:-1]
        if close_color.endswith(";"):
            close_color = close_color[:-1]
        self.prompt = "\001\x1b[%sm\002"%open_color + prompt + "\001\x1b[%sm\002"%close_color + "> "
        #support for 256 color mode:
        #self.prompt = "\001\x1b[38;5;76m\002" + "ON" + "\001\x1b[38;5;255m\002" + "> " + "\001\x1b[0m\002"
        return self.prompt

    def complete_list(self,text,line,begidx,endidx):
        allowed = []
        cmds = ["create","edit","subscribe","freeze","normal","delete","help"]
        lists = self.list_lists()
        words = len(line.split())
        # We need to autocomplete listname for the first or second argument
        # If the first one is a cmds
        if words <= 1:
            allowed = lists + cmds
        elif words == 2:
            # if text, the completing word is the second
            cond = bool(text)
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
        return [i+" " for i in allowed if i.startswith(text)]

    def complete_add(self,text,line,begidx,endidx):
        if len(line.split()) == 2 and text != "":
            allowed = self.list_lists()
        elif len(line.split()) == 1:
            allowed = self.list_lists()
        else:
            allowed = []
        return [i+" " for i in allowed if i.startswith(text)]
    def complete_move(self,text,line,begidx,endidx):
        return self.complete_add(text,line,begidx,endidx)
    def complete_tour(self,text,line,begidx,endidx):
        return self.complete_add(text,line,begidx,endidx)
    
    def complete_theme(self,text,line,begidx,endidx):
        elements = offthemes.default
        colors = offthemes.colors
        words = len(line.split())
        if words <= 1:
            allowed = elements
        elif words == 2 and text != "":
            allowed = elements
        else:
            allowed = colors
        return [i+" " for i in allowed if i.startswith(text)]


    def get_renderer(self,url=None):
        # If launched without argument, we return the renderer for the current URL
        if not url: url = self.current_url
        return self.opencache.get_renderer(url,theme=self.theme)

    def _go_to_url(self, url, update_hist=True, force_refresh=False, handle=True,\
                                    grep=None,name=None, mode=None,limit_size=False):
        """This method might be considered "the heart of Offpunk".
        Everything involved in fetching a gemini resource happens here:
        sending the request over the network, parsing the response,
        storing the response in a temporary file, choosing
        and calling a handler program, and updating the history.
        Nothing is returned."""
        if not url:
            return
        url,newmode = unmode_url(url)
        if not mode: mode = newmode
        #we don’t handle the name anymore !
        if name:
            print("We don’t handle name of URL: %s"%name)
        # Obey permanent redirects
        if url in self.permanent_redirects:
            self._go_to_url(self.permanent_redirects[url],update_hist=update_hist,\
                            force_refresh=force_refresh, handle=handle, name=name,mode=mode,\
                            limit_size=limit_size,grep=grep)
            return
        # Code to translate URLs to better frontends (think twitter.com -> nitter)
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc
        if netloc.startswith("www."):
            netloc = netloc[4:]
        #we block/redirect even subdomains
        for key in self.redirects.keys():
            match = key == netloc
            if key.startswith("*"):
                match = netloc.endswith(key[1:])
            if match:
                if self.redirects[key] == "blocked":
                    text = "This website has been blocked.\n"
                    text += "Use the redirect command to unblock it."
                    if handle and not self.sync_only:
                        print(text)
                    return
                else:
                    parsed = parsed._replace(netloc = self.redirects[key])
                    url = urllib.parse.urlunparse(parsed)
        params = {}
        params["timeout"] = self.options["short_timeout"]
        if limit_size:
            params["max_size"] = int(self.options["max_size_download"])*1000000
        params["print_error"] = not self.sync_only
        params["interactive"] = not self.sync_only
        params["offline"] = self.offline_only
        params["accept_bad_ssl_certificates"] = self.options["accept_bad_ssl_certificates"]
        if mode:
            params["images_mode"] = mode
        else:
            params["images_mode"] = self.options["images_mode"]
        if force_refresh:
            params["validity"] = 1
        elif not self.offline_only:
            #A cache is always valid at least 60seconds
            params["validity"] = 60
        # Use cache or mark as to_fetch if resource is not cached
        if handle and not self.sync_only:
            displayed, url = self.opencache.opnk(url,mode=mode,grep=grep,theme=self.theme,**params)
            modedurl = mode_url(url,mode)
            if not displayed:
                #if we can’t display, we mark to sync what is not local
                if not is_local(url) and not netcache.is_cache_valid(url):
                    self.get_list("to_fetch")
                    r = self.list_add_line("to_fetch",url=modedurl,verbose=False)
                    if r:
                        print("%s not available, marked for syncing"%url)
                    else:
                        print("%s already marked for syncing"%url)
            else:
                self.page_index = 0
                # Update state (external files are not added to history)
                self.current_url = modedurl
                if update_hist and not self.sync_only:
                    self._update_history(modedurl)
        else:
            #we are asked not to handle or in sync_only mode
            if self.support_http or not parsed.scheme in ["http","https"] :
                netcache.fetch(url,**params)

    @needs_gi
    def _show_lookup(self, offset=0, end=None, show_url=False):
        for n, u in enumerate(self.get_renderer().get_links()[offset:end]):
            index = n+offset+1
            line = "[%s] %s" %(index,u)
            #TODO: implement proper listing of url (with protocol and show_url)
             #   protocol = "" if gi.scheme == "gemini" else " %s" % gi.scheme
             #   line = "[%d%s] %s" % (index, protocol, gi.name or gi.url)
             # line += " (%s)" % gi.url
            print(line)

    def _update_history(self, url):
        # We never update while in sync_only
        # We don’t add history to itself.
        if self.sync_only or not url or url == "list:///history":
            return
        #First, we call get_list to create history if needed
        self.get_list("history")
        links = self.list_get_links("history")
        length = len(links)
        #Don’t update history if we are back/forwarding through it
        if length > 0 and links[self.hist_index] == url:
            return
        if length > self.options["history_size"]:
            length = self.options["history_size"]
        self.list_add_top("history",limit=self.options["history_size"],truncate_lines=self.hist_index)
        self.hist_index = 0

    # Cmd implementation follows
    def default(self, line):
        if line.strip() == "EOF":
            return self.onecmd("quit")
        elif line.startswith("/"):
            return self.do_find(line[1:])
        # Expand abbreviated commands
        first_word = line.split()[0].strip()
        if first_word in _ABBREVS:
            full_cmd = _ABBREVS[first_word]
            expanded = line.replace(first_word, full_cmd, 1)
            return self.onecmd(expanded)
        # Try to access it like an URL
        if looks_like_url(line):
            return self.do_go(line)
        # Try to parse numerical index for lookup table
        try:
            n = int(line.strip())
        except ValueError:
            print("What?")
            return
        # if we have no url, there's nothing to do
        if self.current_url is None:
            print("No links to index")
            return
        else:
            r = self.get_renderer()
            if r:
                url = r.get_link(n)
                self._go_to_url(url)
            else:
                print("No page with links")
                return

    ### Settings
    def do_redirect(self,line):
        """Display and manage the list of redirected URLs. This features is mostly useful to use privacy-friendly frontends for popular websites."""
        if len(line.split()) == 1:
            if line in self.redirects:
                print("%s is redirected to %s" %(line,self.redirects[line]))
            else:
                print("Please add a destination to redirect %s" %line)
        elif len(line.split()) >= 2:
            orig, dest = line.split(" ",1)
            if dest.lower() == "none":
                if orig in self.redirects:
                    self.redirects.pop(orig)
                    print("Redirection for %s has been removed"%orig)
                else:
                    print("%s was not redirected. Nothing has changed."%orig)
            elif dest.lower() == "block":
                self.redirects[orig] = "blocked"
                print("%s will now be blocked"%orig)
            else:
                self.redirects[orig] = dest
                print("%s will now be redirected to %s" %(orig,dest))
        else:
            toprint="Current redirections:\n"
            toprint+="--------------------\n"
            for r in self.redirects:
                toprint += ("%s\t->\t%s\n" %(r,self.redirects[r]))
            toprint +="\nTo add new, use \"redirect origine.com destination.org\""
            toprint +="\nTo remove a redirect, use \"redirect origine.com NONE\""
            toprint +="\nTo completely block a website, use \"redirect origine.com BLOCK\""
            toprint +="\nTo block also subdomains, prefix with *: \"redirect *origine.com BLOCK\""
            print(toprint)

    def do_set(self, line):
        """View or set various options."""
        if not line.strip():
            # Show all current settings
            for option in sorted(self.options.keys()):
                print("%s   %s" % (option, self.options[option]))
        elif len(line.split()) == 1 :
            # Show current value of one specific setting
            option = line.strip()
            if option in self.options:
                print("%s   %s" % (option, self.options[option]))
            else:
                print("Unrecognised option %s" % option)
        else:
            # Set value of one specific setting
            option, value = line.split(" ", 1)
            if option not in self.options:
                print("Unrecognised option %s" % option)
                return
            # Validate / convert values
            elif option == "tls_mode":
                if value.lower() not in ("ca", "tofu"):
                    print("TLS mode must be `ca` or `tofu`!")
                    return
            elif option == "accept_bad_ssl_certificates":
                if value.lower() == "false":
                    print("Only high security certificates are now accepted")
                elif value.lower() == "true":
                    print("Low security SSL certificates are now accepted")
                else:
                    print("accept_bad_ssl_certificates should be True or False")
                    return
            elif option == "width":
                if value.isnumeric():
                    value = int(value)
                    print("changing width to ",value)
                    term_width(new_width=value)
                    self.opencache.cleanup()
                else:
                    print("%s is not a valid width (integer required)"%value)
            elif value.isnumeric():
                value = int(value)
            elif value.lower() == "false":
                value = False
            elif value.lower() == "true":
                value = True
            else:
                try:
                    value = float(value)
                except ValueError:
                    pass
            self.options[option] = value
    def do_theme(self,line):
        """Change the colors of your rendered text.

"theme ELEMENT COLOR"

ELEMENT is one of: window_title, window_subtitle, title,
subtitle,subsubtitle,link,oneline_link,new_link,image_link,preformatted,blockquote.

COLOR is one or many (separated by space) of: bold, faint, italic, underline, black,
red, green, yellow, blue, purple, cyan, white.

Each color can alternatively be prefaced with "bright_"."""
        words = line.split()
        le = len(words)
        if le == 0: 
            t = self.get_renderer("list:///").get_theme()
            for e in t:
                print("%s set to %s"%(e,t[e]))
        else:
            element = words[0]
            if element not in offthemes.default.keys():
                print("%s is not a valid theme element"%element)
                print("Valid theme elements are: ")
                valid = []
                for k in offthemes.default:
                    valid.append(k)
                print(valid)
            else:
                if le == 1:
                    if element in self.theme.keys():
                        value = self.theme[element]
                    else:
                        value = offthemes.default[element]
                    print("%s is set to %s"%(element,str(value))) 
                else:
                    #Now we parse the colors
                    for w in words[1:]:
                        if w not in offthemes.colors.keys():
                            print("%s is not a valid color"%w)
                            print("Valid colors are one of: ")
                            valid = []
                            for k in offthemes.colors:
                                valid.append(k)
                            print(valid)
                            return
                    self.theme[element] = words[1:]
                    self.opencache.cleanup()
        #now we upadte the prompt
        if self.offline_only:
            self.set_prompt("OFF")
        else:
            self.set_prompt("ON")

    def do_handler(self, line):
        """View or set handler commands for different MIME types."""
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
                print("No handler set for MIME type %s" % mime)
        else:
            mime, handler = line.split(" ", 1)
            self.opencache.set_handler(mime,handler)

    def do_abbrevs(self, *args):
        """Print all Offpunk command abbreviations."""
        header = "Command Abbreviations:"
        self.stdout.write("\n{}\n".format(str(header)))
        if self.ruler:
            self.stdout.write("{}\n".format(str(self.ruler * len(header))))
        for k, v in _ABBREVS.items():
            self.stdout.write("{:<7}  {}\n".format(k, v))
        self.stdout.write("\n")

    def do_offline(self, *args):
        """Use Offpunk offline by only accessing cached content"""
        if self.offline_only:
            print("Offline and undisturbed.")
        else:
            self.offline_only = True
            self.set_prompt("OFF")
            print("Offpunk is now offline and will only access cached content")

    def do_online(self, *args):
        """Use Offpunk online with a direct connection"""
        if self.offline_only:
            self.offline_only = False
            self.set_prompt("ON")
            print("Offpunk is online and will access the network")
        else:
            print("Already online. Try offline.")

    def do_copy(self, arg):
        """Copy the content of the last visited page as gemtext/html in the clipboard.
Use with "url" as argument to only copy the adress.
Use with "raw" to copy ANSI content as seen in your terminal (with colour codes).
Use with "cache" to copy the path of the cached content.
Use with "title" to copy the title of the page.
Use with "link" to copy a link in the gemtext format to that page with the title.
"""
        if self.current_url:
            args = arg.split()
            if args and args[0] == "url":
                if len(args) > 1 and args[1].isdecimal():
                    url = self.get_renderer().get_link(int(args[1])-1)
                else:
                    url,mode = unmode_url(self.current_url)
                print(url)
                clipboard_copy(url)
            elif args and args[0] == "raw":
                tmp = self.opencache.get_temp_filename(self.current_url)
                if tmp:
                    clipboard_copy(open(tmp,"rb"))
            elif args and args[0] == "cache":
                clipboard_copy(netcache.get_cache_path(self.current_url))
            elif args and args[0] == "title":
                title = self.get_renderer().get_page_title()
                clipboard_copy(title)
                print(title)
            elif args and args[0] == "link":
                link = "=> %s %s"%(unmode_url(self.current_url)[0],\
                                    self.get_renderer().get_page_title())
                print(link)
                clipboard_copy(link)
            else:
                clipboard_copy(open(netcache.get_cache_path(self.current_url),"rb"))
        else:
            print("No content to copy, visit a page first")

    ### Stuff for getting around
    def do_go(self, line):
        """Go to a gemini URL or marked item."""
        line = line.strip()
        if not line:
            clipboards = clipboard_paste()
            urls = []
            for u in clipboards:
                if "://" in u and looks_like_url(u) and u not in urls :
                    urls.append(u)
            if len(urls) > 1:
                stri = "URLs in your clipboard\n"
                counter = 0
                for u in urls:
                    counter += 1
                    stri += "[%s] %s\n"%(counter,u)
                stri += "Where do you want to go today ?> "
                ans = input(stri)
                if ans.isdigit() and 0 < int(ans) <= len(urls):
                    self.do_go(urls[int(ans)-1])
            elif len(urls) == 1:
                self.do_go(urls[0])
            else:
                print("Go where? (hint: simply copy an URL in your clipboard)")

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
        elif "://" not in line and "default_protocol" in self.options.keys()\
                            and looks_like_url(self.options["default_protocol"]+"://"+line):
            self._go_to_url(self.options["default_protocol"]+"://"+line)
        else:
            print("%s is not a valid URL to go"%line)

    @needs_gi
    def do_reload(self, *args):
        """Reload the current URL."""
        if self.offline_only and not is_local(self.current_url):
            self.get_list("to_fetch")
            r = self.list_add_line("to_fetch",url=self.current_url,verbose=False)
            if r:
                print("%s marked for syncing" %self.current_url)
            else:
                print("%s already marked for syncing" %self.current_url)
        else:
            self.opencache.cleanup()
            self._go_to_url(self.current_url, force_refresh=False)

    @needs_gi
    def do_up(self, *args):
        """Go up one directory in the path.
Take an integer as argument to go up multiple times."""
        level = 1
        if args[0].isnumeric():
            level = int(args[0])
        elif args[0] != "":
            print("Up only take integer as arguments")
        #TODO : implement up, this code is copy/pasted from GeminiItem
        url, mode = unmode_url(self.current_url)
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.rstrip('/')
        count = 0
        while count < level:
            pathbits = list(os.path.split(path))
            # Don't try to go higher than root or in config
            if is_local(url) or len(pathbits) == 1 :
                break
            # Get rid of bottom component
            if len(pathbits) > 1:
                pathbits.pop()
            path = os.path.join(*pathbits)
            count += 1
        if parsed.scheme == "gopher":
            path = "/1" + path
        newurl = urllib.parse.urlunparse((parsed.scheme,parsed.netloc,path,"","",""))
        self._go_to_url(newurl)

    def do_back(self, *args):
        """Go back to the previous gemini item."""
        histfile = self.get_list("history")
        links = self.list_get_links("history")
        if self.hist_index >= len(links) -1:
            return
        self.hist_index += 1
        url = links[self.hist_index]
        self._go_to_url(url, update_hist=False)

    def do_forward(self, *args):
        """Go forward to the next gemini item."""
        histfile = self.get_list("history")
        links = self.list_get_links("history")
        if self.hist_index <= 0:
            return
        self.hist_index -= 1
        url = links[self.hist_index]
        self._go_to_url(url, update_hist=False)

    @needs_gi
    def do_root(self, *args):
        """Go to root selector of the server hosting current item."""
        parse = urllib.parse.urlparse(self.current_url)
        self._go_to_url(urllib.parse.urlunparse((parse.scheme,parse.netloc,"/","","","")))

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
                print("End of tour.")
            else:
                url = self.list_go_to_line("1","tour")
                if url:
                    self.list_rm_url(url,"tour")
        elif line == "ls":
            self.list_show("tour")
        elif line == "clear":
            for l in self.list_get_links("tour"):
                self.list_rm_url(l,"tour")
        elif line == "*":
            for l in self.get_renderer().get_links():
                self.list_add_line("tour",url=l,verbose=False)
        elif line == ".":
            self.list_add_line("tour",verbose=False)
        elif looks_like_url(line):
            self.list_add_line("tour",url=line)
        elif line in self.list_lists():
            list_path = self.list_path(line)
            if not list_path:
                print("List %s does not exist. Cannot add it to tour"%(list))
            else:
                url = "list:///%s"%line
                display = not self.sync_only
                for l in self.get_renderer(url).get_links():
                    self.list_add_line("tour",url=l,verbose=False)
        elif self.current_url:
            for index in line.split():
                try:
                    pair = index.split('-')
                    if len(pair) == 1:
                        # Just a single index
                        n = int(index)
                        url = self.get_renderer().get_link(n)
                        self.list_add_line("tour",url=url,verbose=False)
                    elif len(pair) == 2:
                        # Two endpoints for a range of indices
                        if int(pair[0]) < int(pair[1]):
                            for n in range(int(pair[0]), int(pair[1]) + 1):
                                url = self.get_renderer().get_link(n)
                                self.list_add_line("tour",url=url,verbose=False)
                        else:
                            for n in range(int(pair[0]), int(pair[1]) - 1, -1):
                                url = self.get_renderer().get_link(n)
                                self.list_add_line("tour",url=url,verbose=False)

                    else:
                        # Syntax error
                        print("Invalid use of range syntax %s, skipping" % index)
                except ValueError:
                    print("Non-numeric index %s, skipping." % index)
                except IndexError:
                    print("Invalid index %d, skipping." % n)

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
            print("Invalid mark, must be one letter")

    @needs_gi
    def do_info(self,line):
        """Display information about current page."""
        renderer = self.get_renderer()
        url,mode = unmode_url(self.current_url)
        out = renderer.get_page_title() + "\n\n"
        out += "URL      :   " + url + "\n"
        out += "Mime     :   " + renderer.get_mime() + "\n"
        out += "Cache    :   " + netcache.get_cache_path(url) + "\n"
        if self.get_renderer() :
            rend = str(self.get_renderer().__class__)
            rend = rend.lstrip("<class '__main__.").rstrip("'>")
        else:
            rend = "None"
        out += "Renderer :   " + rend + "\n\n"
        lists = []
        for l in self.list_lists():
            if self.list_has_url(url,l):
                lists.append(l)
        if len(lists) > 0:
            out += "Page appeard in following lists :\n"
            for l in lists:
                if not self.list_is_system(l):
                    status = "normal list"
                    if self.list_is_subscribed(l):
                        status = "subscription"
                    elif self.list_is_frozen(l):
                        status = "frozen list"
                    out += " • %s\t(%s)\n" %(l,status)
            for l in lists:
                if self.list_is_system(l):
                    out += " • %s\n" %l
        else:
            out += "Page is not save in any list"
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
        output += "Highly recommended:\n"
        output += " - python-cryptography : " + has(netcache._HAS_CRYPTOGRAPHY)
        output += " - xdg-open            : " + has(opnk._HAS_XDGOPEN)
        output += "\nWeb browsing:\n"
        output += " - python-requests     : " + has(netcache._DO_HTTP)
        output += " - python-feedparser   : " + has(ansicat._DO_FEED)
        output += " - python-bs4          : " + has(ansicat._HAS_SOUP)
        output += " - python-readability  : " + has(ansicat._HAS_READABILITY)
        output += " - timg 1.3.2+         : " + has(ansicat._NEW_TIMG)
        if ansicat._NEW_CHAFA:
            output += " - chafa 1.10+         : " + has(ansicat._HAS_CHAFA)
        else:
            output += " - chafa               : " + has(ansicat._HAS_CHAFA)
            output += " - python-pil          : " + has(ansicat._HAS_PIL)
        output += "\nNice to have:\n"
        output += " - python-setproctitle       : " + has(_HAS_SETPROCTITLE)
        clip_support = shutil.which("xsel") or shutil.which("xclip")
        output += " - X11 clipboard (xsel or xclip)   : " + has(clip_support)
        output += " - Wayland clipboard (wl-clipboard): " + has(shutil.which("wl-copy"))

        output += "\nFeatures :\n"
        if ansicat._NEW_CHAFA:
            output += " - Render images (chafa or timg)              : " + has(ansicat._RENDER_IMAGE)
        else:
            output += " - Render images (python-pil, chafa or timg)  : " + has(ansicat._RENDER_IMAGE)
        output += " - Render HTML (bs4, readability)             : " + has(ansicat._DO_HTML)
        output += " - Render Atom/RSS feeds (feedparser)         : " + has(ansicat._DO_FEED)
        output += " - Connect to http/https (requests)           : " + has(netcache._DO_HTTP)
        output += " - Detect text encoding (python-chardet)      : " + has(netcache._HAS_CHARDET)
        output += " - restore last position (less 572+)          : " + has(opnk._LESS_RESTORE_POSITION)
        output += "\n"
        output += "Config directory    : " +  xdg("config") + "\n"
        output += "User Data directory : " +  xdg("data") + "\n"
        output += "Cache directoy      : " +  xdg("cache")

        print(output)

    ### Stuff that modifies the lookup table
    def do_ls(self, line):
        """List contents of current index.
Use 'ls -l' to see URLs."""
        self._show_lookup(show_url = "-l" in line)
        self.page_index = 0

    def do_search(self,line):
        """Search on Gemini using the engine configured (by default kennedy.gemi.dev)
        You can configure it using "set search URL".
        URL should contains one "%s" that will be replaced by the search term."""
        search = urllib.parse.quote(line)
        url = self.options["search"]%search
        self._go_to_url(url)

    def do_wikipedia(self,line):
        """Search on wikipedia using the configured Gemini interface.
        The first word should be the two letters code for the language.
        Exemple : "wikipedia en Gemini protocol"
        But you can also use abbreviations to go faster:
        "wen Gemini protocol". (your abbreviation might be missing, report the bug)
        The interface used can be modified with the command:
        "set wikipedia URL" where URL should contains two "%s", the first
        one used for the language, the second for the search string."""
        words = line.split(" ",maxsplit=1)
        if len(words[0]) == 2:
            lang = words[0]
            search = urllib.parse.quote(words[1])
        else:
            lang = "en"
            search = urllib.parse.quote(line)
        url = self.options["wikipedia"]%(lang,search)
        self._go_to_url(url)

    def do_gus(self, line):
        """Submit a search query to the geminispace.info search engine."""
        if not line:
            print("What?")
            return 
        search = line.replace(" ","%20")
        self._go_to_url("gemini://geminispace.info/search?%s"%search)

    def do_history(self, *args):
        """Display history."""
        self.list_show("history")

    @needs_gi
    def do_find(self, searchterm):
        """Find in current page by displaying only relevant lines (grep)."""
        self._go_to_url(self.current_url,update_hist=False,grep=searchterm)

    def emptyline(self):
        """Page through index ten lines at a time."""
        i = self.page_index
        if not self.current_url or i > len(self.get_renderer().get_links()):
            return
        self._show_lookup(offset=i, end=i+10)
        self.page_index += 10

    ### Stuff that does something to most recently viewed item
    @needs_gi
    def do_cat(self, *args):
        """Run most recently visited item through "cat" command."""
        run("cat", input=open(self.opencache.get_temp_filename(self.current_url), "rb"),\
                                                                    direct_output=True)

    @needs_gi
    def do_view(self, *args):
        """Run most recently visited item through "less" command, restoring \
previous position.
Use "view normal" to see the default article view on html page.
Use "view full" to see a complete html page instead of the article view.
Use "view feed" to see the the linked feed of the page (in any).
Use "view feeds" to see available feeds on this page.
Use "view XX" where XX is a number to view information about link XX.
(full, feed, feeds have no effect on non-html content)."""
        if self.current_url and args and args[0] != "":
            u, m = unmode_url(self.current_url)
            if args[0] in ["full","debug","source"]:
                self._go_to_url(self.current_url,mode=args[0])
            elif args[0] in ["normal","readable"]:
                self._go_to_url(self.current_url,mode="readable")
            elif args[0] == "feed":
                subs = self.get_renderer().get_subscribe_links()
                if len(subs) > 1:
                    self.do_go(subs[1][0])
                elif "rss" in subs[0][1] or "atom" in subs[0][1]:
                    print("%s is already a feed" %u)
                else:
                    print("No other feed found on %s"%u)
            elif args[0] == "feeds":
                subs = self.get_renderer().get_subscribe_links()
                stri = "Available views :\n"
                counter = 0
                for s in subs:
                    counter += 1
                    stri += "[%s] %s [%s]\n"%(counter,s[0],s[1])
                stri += "Which view do you want to see ? >"
                ans = input(stri)
                if ans.isdigit() and 0 < int(ans) <= len(subs):
                    self.do_go(subs[int(ans)-1][0])
            elif args[0].isdigit():
                link_url = self.get_renderer().get_link(int(args[0]))
                if link_url:
                    print("Link %s is: %s"%(args[0],link_url))
                    if netcache.is_cache_valid(link_url):
                        last_modified = netcache.cache_last_modified(link_url)
                        link_renderer = self.get_renderer(link_url)
                        if link_renderer:
                            link_title = link_renderer.get_page_title()
                            print(link_title)
                        else:
                            print("Empty cached version")
                        print("Last cached on %s"%time.ctime(last_modified))
                    else:
                        print("No cached version for this link")

            else:
                print("Valid argument for view are : normal, full, feed, feeds or a number")
        else:
            self._go_to_url(self.current_url)

    @needs_gi
    def do_open(self, *args):
        """Open current item with the configured handler or xdg-open.
Uses "open url" to open current URL in a browser.
see "handler" command to set your handler."""
        u, m = unmode_url(self.current_url)
        if args[0] == "url":
            run("xdg-open %s", parameter=u, direct_output=True)
        else:
            self.opencache.opnk(u,terminal=False)

    @needs_gi
    def do_shell(self, line):
        """'cat' most recently visited item through a shell pipeline.
'!' is an useful shortcut."""
        tmp = self.opencache.get_temp_filename(self.current_url)
        if tmp:
            run(line, input=open(tmp, "rb"), direct_output=True)

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
                print("You cannot save if not cached!")
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
                print("First argument is not a valid item index!")
                return
            filename = os.path.expanduser(filename)
        else:
            print("You must provide an index, a filename, or both.")
            return
        # Next, fetch the item to save, if it's not the current one.
        if index:
            last_url = self.current_url
            try:
                url = self.get_renderer().get_link(index)
                self._go_to_url(url, update_hist = False, handle = False)
            except IndexError:
                print ("Index too high!")
                self.current_url = last_url
                return
        else:
            url = self.current_url

        # Derive filename from current GI's path, if one hasn't been set
        if not filename:
            filename = os.path.basename(netcache.get_cache_path(self.current_url))
        # Check for filename collisions and actually do the save if safe
        if os.path.exists(filename):
            print("File %s already exists!" % filename)
        else:
            # Don't use _get_active_tmpfile() here, because we want to save the
            # "source code" of menus, not the rendered view - this way Offpunk
            # can navigate to it later.
            path = netcache.get_cache_path(url)
            if os.path.isdir(path):
                print("Can’t save %s because it’s a folder, not a file"%path)
            else:
                print("Saved to %s" % filename)
                shutil.copyfile(path, filename)

        # Restore gi if necessary
        if index != None:
            self._go_to_url(last_url, handle=False)

    @needs_gi
    def do_url(self, *args):
        """Print URL of most recently visited item."""
        url,mode = unmode_url(self.current_url)
        print(url)

    ### Bookmarking stuff
    @needs_gi
    def do_add(self, line):
        """Add the current URL to the list specied as argument.
If no argument given, URL is added to Bookmarks."""
        args = line.split()
        if len(args) < 1 :
            list = "bookmarks"
            if not self.list_path(list):
                self.list_create(list)
            self.list_add_line(list)
        else:
            self.list_add_line(args[0])

    # Get the list file name, creating or migrating it if needed.
    # Migrate bookmarks/tour/to_fetch from XDG_CONFIG to XDG_DATA
    # We migrate only if the file exists in XDG_CONFIG and not XDG_DATA
    def get_list(self,list):
        list_path = self.list_path(list)
        if not list_path:
            old_file_gmi = os.path.join(xdg("config"),list + ".gmi")
            old_file_nogmi = os.path.join(xdg("config"),list)
            target = os.path.join(xdg("data"),"lists")
            if os.path.exists(old_file_gmi):
                shutil.move(old_file_gmi,target)
            elif os.path.exists(old_file_nogmi):
                targetgmi = os.path.join(target,list+".gmi")
                shutil.move(old_file_nogmi,targetgmi)
            else:
                if list == "subscribed":
                    title = "Subscriptions #subscribed (new links in those pages will be added to tour)"
                elif list == "to_fetch":
                    title = "Links requested and to be fetched during the next --sync"
                else:
                    title = None
                self.list_create(list, title=title,quite=True)
                list_path = self.list_path(list)
        return list_path

    @needs_gi
    def do_subscribe(self,line):
        """Subscribe to current page by saving it in the "subscribed" list.
If a new link is found in the page during a --sync, the new link is automatically
fetched and added to your next tour.
To unsubscribe, remove the page from the "subscribed" list."""
        subs = self.get_renderer().get_subscribe_links()
        if len(subs) > 1:
            stri = "Multiple feeds have been found :\n"
        elif "rss" in subs[0][1] or "atom" in subs[0][1] :
            stri = "This page is already a feed:\n"
        else:
            stri = "No feed detected. You can still watch the page :\n"
        counter = 0
        for l in subs:
            link = l[0]
            already = []
            for li in self.list_lists():
                if self.list_is_subscribed(li):
                    if self.list_has_url(link,li):
                        already.append(li)
            stri += "[%s] %s [%s]\n"%(counter+1,link,l[1])
            if len(already) > 0:
                stri += "\t -> (already subscribed through lists %s)\n"%(str(already))
            counter += 1
        stri += "\n"
        stri += "Which feed do you want to subscribe ? > "
        ans = input(stri)
        if ans.isdigit() and 0 < int(ans) <= len(subs):
            sublink,mime,title = subs[int(ans)-1]
        else:
            sublink,title = None,None
        if sublink:
            list_path = self.get_list("subscribed")
            added = self.list_add_line("subscribed",url=sublink,verbose=False)
            if added :
                print("Subscribed to %s" %sublink)
            else:
                print("You are already subscribed to %s"%sublink)
        else:
            print("No subscription registered")

    def do_bookmarks(self, line):
        """Show or access the bookmarks menu.
'bookmarks' shows all bookmarks.
'bookmarks n' navigates immediately to item n in the bookmark menu.
Bookmarks are stored using the 'add' command."""
        list_path = self.get_list("bookmarks")
        args = line.strip()
        if len(args.split()) > 1 or (args and not args.isnumeric()):
            print("bookmarks command takes a single integer argument!")
        elif args:
            self.list_go_to_line(args,"bookmarks")
        else:
            self.list_show("bookmarks")

    @needs_gi
    def do_archive(self,args):
        """Archive current page by removing it from every list and adding it to
archives, which is a special historical list limited in size. It is similar to `move archives`."""
        for li in self.list_lists():
            if li not in ["archives", "history"]:
                u,m = unmode_url(self.current_url)
                deleted = self.list_rm_url(u,li)
                if deleted:
                    print("Removed from %s"%li)
        self.list_add_top("archives",limit=self.options["archives_size"])
        print("Archiving: %s"%self.get_renderer().get_page_title())
        print("\x1b[2;34mCurrent maximum size of archives : %s\x1b[0m" %self.options["archives_size"])

    #what is the line to add to a list for this url ?
    def to_map_line(self,url=None):
        if not url:
            url = self.current_url
        r = self.get_renderer(url)
        if r:
            title = r.get_page_title()
        else:
            title = ""
        toreturn = "=> {} {}\n".format(url,title)
        return toreturn

    def list_add_line(self,list,url=None,verbose=True):
        list_path = self.list_path(list)
        if not list_path and self.list_is_system(list):
            self.list_create(list,quite=True)
            list_path = self.list_path(list)
        if not list_path:
            print("List %s does not exist. Create it with ""list create %s"""%(list,list))
            return False
        else:
            if not url:
                url = self.current_url 
            unmoded_url,mode = unmode_url(url)
            # first we check if url already exists in the file
            if self.list_has_url(url,list,exact_mode=True):
                if verbose:
                    print("%s already in %s."%(url,list))
                return False
            # If the URL already exists but without a mode, we update the mode
            # FIXME: this doesn’t take into account the case where you want to remove the mode
            elif url != unmoded_url and self.list_has_url(unmoded_url,list):
                self.list_update_url_mode(unmoded_url,list,mode)    
                if verbose:
                    print("%s has updated mode in %s to %s"%(url,list,mode))
            else:
                with open(list_path,"a") as l_file:
                    l_file.write(self.to_map_line(url))
                    l_file.close()
                if verbose:
                    print("%s added to %s" %(url,list))
                return True

    @needs_gi
    def list_add_top(self,list,limit=0,truncate_lines=0):
        stri = self.to_map_line().strip("\n")
        if list == "archives":
            stri += ", archived on "
        elif list == "history":
            stri += ", visited on "
        else:
            stri += ", added to %s on "%list
        stri += time.ctime() + "\n"
        list_path = self.get_list(list)
        with open(list_path,"r") as l_file:
            lines = l_file.readlines()
            l_file.close()
        with open(list_path,"w") as l_file:
            l_file.write("#%s\n"%list)
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
    def list_rm_url(self,url,list):
        return self.list_has_url(url,list,deletion=True)

    def list_update_url_mode(self,url,list,mode):
        return self.list_has_url(url,list,update_mode = mode)

    # deletion and has_url are so similar, I made them the same method
    # deletion : true or false if you want to delete the URL
    # exact_mode : True if you want to check only for the exact url, not the canonical one
    # update_mode : a new mode to update the URL
    def list_has_url(self,url,list,deletion=False, exact_mode=False, update_mode = None):
        list_path = self.list_path(list)
        if list_path:
            to_return = False
            with open(list_path,"r") as lf:
                lines = lf.readlines()
                lf.close()
            to_write = []
            # let’s remove the mode
            if not exact_mode:
                url=unmode_url(url)[0]
            for l in lines:
                # we separate components of the line
                # to ensure we identify a complete URL, not a part of it
                splitted = l.split()
                if url not in splitted and len(splitted) > 1:
                    current = unmode_url(splitted[1])[0]
                    #sometimes, we must remove the ending "/"
                    if url == current or (url.endswith("/") and url[:-1] == current):
                        to_return = True
                        if update_mode:
                            new_line = l.replace(current,mode_url(url,update_mode))
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
                        new_line = l.replace(url,mode_url(url,update_mode))
                        to_write.append(new_line)
                    elif not deletion:
                        to_write.append(l)
                else:
                    to_write.append(l)
            if deletion or update_mode:
                with open(list_path,"w") as lf:
                    for l in to_write:
                        lf.write(l)
                    lf.close()
            return to_return
        else:
            return False

    def list_get_links(self,list):
        list_path = self.list_path(list)
        if list_path and os.path.exists(list_path):
            return self.get_renderer("list:///%s"%list).get_links()
        else:
            return []

    def list_go_to_line(self,line,list):
        list_path = self.list_path(list)
        if not list_path:
            print("List %s does not exist. Create it with ""list create %s"""%(list,list))
        elif not line.isnumeric():
            print("go_to_line requires a number as parameter")
        else:
            r = self.get_renderer("list:///%s"%list)
            url = r.get_link(int(line))
            display = not self.sync_only
            if url:
                self._go_to_url(url,handle=display)
                return url

    def list_show(self,list):
        list_path = self.list_path(list)
        if not list_path:
            print("List %s does not exist. Create it with ""list create %s"""%(list,list))
        else:
            url = "list:///%s"%list
            display = not self.sync_only
            self._go_to_url(url,handle=display)

    #return the path of the list file if list exists.
    #return None if the list doesn’t exist.
    def list_path(self,list):
        listdir = os.path.join(xdg("data"),"lists")
        list_path = os.path.join(listdir, "%s.gmi"%list)
        if os.path.exists(list_path):
            return list_path
        else:
            return None

    def list_create(self,list,title=None,quite=False):
        list_path = self.list_path(list)
        if list in ["create","edit","delete","help"]:
            print("%s is not allowed as a name for a list"%list)
        elif not list_path:
            listdir = os.path.join(xdg("data"),"lists")
            os.makedirs(listdir,exist_ok=True)
            list_path = os.path.join(listdir, "%s.gmi"%list)
            with open(list_path,"a") as lfile:
                if title:
                    lfile.write("# %s\n"%title)
                else:
                    lfile.write("# %s\n"%list)
                lfile.close()
            if not quite:
                print("list created. Display with `list %s`"%list)
        else:
            print("list %s already exists" %list)

    def do_move(self,arg):
        """move LIST will add the current page to the list LIST.
With a major twist: current page will be removed from all other lists.
If current page was not in a list, this command is similar to `add LIST`."""
        if not arg:
            print("LIST argument is required as the target for your move")
        elif arg[0] == "archives":
            self.do_archive()
        else:
            args = arg.split()
            list_path = self.list_path(args[0])
            if not list_path:
                print("%s is not a list, aborting the move" %args[0])
            else:
                lists = self.list_lists()
                for l in lists:
                    if l != args[0] and l not in ["archives", "history"]:
                        url, mode = unmode_url(self.current_url)
                        isremoved = self.list_rm_url(url,l)
                        if isremoved:
                            print("Removed from %s"%l)
                self.list_add_line(args[0])

    def list_lists(self):
        listdir = os.path.join(xdg("data"),"lists")
        to_return = []
        if os.path.exists(listdir):
            lists = os.listdir(listdir)
            if len(lists) > 0:
                for l in lists:
                    #removing the .gmi at the end of the name
                    to_return.append(l[:-4])
        return to_return

    def list_has_status(self,list,status):
        path = self.list_path(list)
        toreturn = False
        if path:
            with open(path) as f:
                line = f.readline().strip()
                f.close()
            if line.startswith("#") and status in line:
                toreturn = True
        return toreturn

    def list_is_subscribed(self,list):
        return self.list_has_status(list,"#subscribed")
    def list_is_frozen(self,list):
        return self.list_has_status(list,"#frozen")
    def list_is_system(self,list):
        return list in ["history","to_fetch","archives","tour"]

    # This modify the status of a list to one of :
    # normal, frozen, subscribed
    # action is either #frozen, #subscribed or None
    def list_modify(self,list,action=None):
        path = self.list_path(list)
        with open(path) as f:
            lines = f.readlines()
            f.close()
        if lines[0].strip().startswith("#"):
            first_line = lines.pop(0).strip("\n")
        else:
            first_line = "# %s "%list
        first_line = first_line.replace("#subscribed","").replace("#frozen","")
        if action:
            first_line += " " + action
            print("List %s has been marked as %s"%(list,action))
        else:
            print("List %s is now a normal list" %list)
        first_line += "\n"
        lines.insert(0,first_line)
        with open(path,"w") as f:
            for line in lines:
                f.write(line)
            f.close()
    def do_list(self,arg):
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
- tour           : contains the next URLs to visit during a tour (see "help tour")

"""
        listdir = os.path.join(xdg("data"),"lists")
        os.makedirs(listdir,exist_ok=True)
        if not arg:
            lists = self.list_lists()
            if len(lists) > 0:
                lurl = "list:///"
                self._go_to_url(lurl)
            else:
                print("No lists yet. Use `list create`")
        else:
            args = arg.split()
            if args[0] == "create":
                if len(args) > 2:
                    name = " ".join(args[2:])
                    self.list_create(args[1].lower(),title=name)
                elif len(args) == 2:
                    self.list_create(args[1].lower())
                else:
                    print("A name is required to create a new list. Use `list create NAME`")
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
                        path = os.path.join(listdir,args[1]+".gmi")
                        try:
                            # Note that we intentionally don't quote the editor.
                            # In the unlikely case `editor` includes a percent
                            # sign, we also escape it for the %-formatting.
                            cmd = editor.replace("%", "%%") + " %s"
                            run(cmd, parameter=path, direct_output=True)
                        except Exception as err:
                            print(err)
                            print("Please set a valid editor with \"set editor\"")
                    else:
                        print("A valid list name is required to edit a list")
                else:
                    print("No valid editor has been found.")
                    print("You can use the following command to set your favourite editor:")
                    print("set editor EDITOR")
                    print("or use the $VISUAL or $EDITOR environment variables.")
            elif args[0] == "delete":
                if len(args) > 1:
                    if self.list_is_system(args[1]):
                        print("%s is a system list which cannot be deleted"%args[1])
                    elif args[1] in self.list_lists():
                        size = len(self.list_get_links(args[1]))
                        stri = "Are you sure you want to delete %s ?\n"%args[1]
                        confirm = "YES"
                        if size > 0:
                            stri += "! %s items in the list will be lost !\n"%size
                            confirm = "YES DELETE %s" %size
                        else :
                            stri += "The list is empty, it should be safe to delete it.\n"
                        stri += "Type \"%s\" (in capital, without quotes) to confirm :"%confirm
                        answer = input(stri)
                        if answer == confirm:
                            path = os.path.join(listdir,args[1]+".gmi")
                            os.remove(path)
                            print("* * * %s has been deleted" %args[1])
                    else:
                        print("A valid list name is required to be deleted")
                else:
                    print("A valid list name is required to be deleted")
            elif args[0] in ["subscribe","freeze","normal"]:
                if len(args) > 1:
                    if self.list_is_system(args[1]):
                        print("You cannot modify %s which is a system list"%args[1])
                    elif args[1] in self.list_lists():
                        if args[0] == "subscribe":
                            action = "#subscribed"
                        elif args[0] == "freeze":
                            action = "#frozen"
                        else:
                            action = None
                        self.list_modify(args[1],action=action)
                else:
                    print("A valid list name is required after %s" %args[0])
            elif args[0] == "help":
                self.onecmd("help list")
            elif len(args) == 1:
                self.list_show(args[0].lower())
            else:
                self.list_go_to_line(args[1],args[0].lower())

    def do_help(self, arg):
        """ALARM! Recursion detected! ALARM! Prepare to eject!"""
        if arg == "!":
            print("! is an alias for 'shell'")
        elif arg == "?":
            print("? is an alias for 'help'")
        elif arg in _ABBREVS:
            full_cmd = _ABBREVS[arg]
            print("%s is an alias for '%s'" %(arg,full_cmd))
            print("See the list of aliases with 'abbrevs'")
            print("'help %s':"%full_cmd)
            cmd.Cmd.do_help(self, full_cmd)
        else:
            cmd.Cmd.do_help(self, arg)

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
            print("Sync can only be achieved online. Change status with `online`.")
            return
        args = line.split()
        if len(args) > 0:
            if not args[0].isdigit():
                print("sync argument should be the cache validity expressed in seconds")
                return
            else:
                validity = int(args[0])
        else:
            validity = 0
        self.call_sync(refresh_time=validity)

    def call_sync(self,refresh_time=0,depth=1,lists=None):
        # fetch_url is the core of the sync algorithm.
        # It takes as input :
        # - an URL to be fetched
        # - depth : the degree of recursion to build the cache (0 means no recursion)
        # - validity : the age, in seconds, existing caches need to have before
        #               being refreshed (0 = never refreshed if it already exists)
        # - savetotour : if True, newly cached items are added to tour
        def add_to_tour(url):
            if url and netcache.is_cache_valid(url):
                toprint = "  -> adding to tour: %s" %url
                width = term_width() - 1
                toprint = toprint[:width]
                toprint += " "*(width-len(toprint))
                print(toprint)
                self.list_add_line("tour",url=url,verbose=False)
                return True
            else:
                return False
        def fetch_url(url,depth=0,validity=0,savetotour=False,count=[0,0],strin=""):
            #savetotour = True will save to tour newly cached content
            # else, do not save to tour
            #regardless of valitidy
            if not url: return
            if not netcache.is_cache_valid(url,validity=validity):
                if strin != "":
                    endline = '\r'
                else:
                    endline = None
                #Did we already had a cache (even an old one) ?
                isnew = not netcache.is_cache_valid(url)
                toprint = "%s [%s/%s] Fetch "%(strin,count[0],count[1]) + url
                width = term_width() - 1
                toprint = toprint[:width]
                toprint += " "*(width-len(toprint))
                print(toprint,end=endline)
                #If not saving to tour, then we should limit download size
                limit = not savetotour
                self._go_to_url(url,update_hist=False,limit_size=limit)
                if savetotour and isnew and netcache.is_cache_valid(url):
                    #we add to the next tour only if we managed to cache
                    #the ressource
                    add_to_tour(url)
            #Now, recursive call, even if we didn’t refresh the cache
            # This recursive call is impacting performances a lot but is needed
            # For the case when you add a address to a list to read later
            # You then expect the links to be loaded during next refresh, even
            # if the link itself is fresh enough
            # see fetch_list()
            if depth > 0:
                #we should only savetotour at the first level of recursion
                # The code for this was removed so, currently, we savetotour
                # at every level of recursion.
                r = self.get_renderer(url)
                url,oldmode = unmode_url(url)
                if oldmode == "full":
                    mode = "full_links_only"
                else:
                    mode = "links_only"
                if r:
                    links = r.get_links(mode=mode)
                    subcount = [0,len(links)]
                    d = depth - 1
                    for k in links:
                        #recursive call (validity is always 0 in recursion)
                        substri = strin + " -->"
                        subcount[0] += 1
                        fetch_url(k,depth=d,validity=0,savetotour=savetotour,\
                                            count=subcount,strin=substri)
        def fetch_list(list,validity=0,depth=1,tourandremove=False,tourchildren=False):
            links = self.list_get_links(list)
            end = len(links)
            counter = 0
            print(" * * * %s to fetch in %s * * *" %(end,list))
            for l in links:
                counter += 1
                # If cache for a link is newer than the list
                fetch_url(l,depth=depth,validity=validity,savetotour=tourchildren,count=[counter,end])
                if tourandremove:
                    if add_to_tour(l):
                        self.list_rm_url(l,list)

        self.sync_only = True
        if not lists:
            lists = self.list_lists()
        # We will fetch all the lists except "archives" and "history"
        # We keep tour for the last round
        subscriptions = []
        normal_lists = []
        fridge = []
        for l in lists:
            #only try existing lists
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
            fetch_list(l,validity=refresh_time,depth=depth,tourchildren=True)
        #Then the fetch list (item are removed from the list after fetch)
        # We fetch regarless of the refresh_time
        if "to_fetch" in lists:
            nowtime = int(time.time())
            short_valid = nowtime - starttime
            fetch_list("to_fetch",validity=short_valid,depth=depth,tourandremove=True)
        #then we fetch all the rest (including bookmarks and tour)
        for l in normal_lists:
            fetch_list(l,validity=refresh_time,depth=depth)
        for l in fridge:
            fetch_list(l,validity=0,depth=depth)
        #tour should be the last one as item my be added to it by others
        fetch_list("tour",validity=refresh_time,depth=depth)
        print("End of sync")
        self.sync_only = False

    ### The end!
    def do_quit(self, *args):
        """Exit Offpunk."""
        self.opencache.cleanup() 
        print("You can close your screen!")
        sys.exit()

    do_exit = do_quit



# Main function
def main():

    # Parse args
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bookmarks', action='store_true',
                        help='start with your list of bookmarks')
    parser.add_argument('--config-file',metavar='FILE',
                        help='use this particular config file instead of default')
    parser.add_argument('--sync', action='store_true',
                        help='run non-interactively to build cache by exploring lists passed \
                                as argument. Without argument, all lists are fetched.')
    parser.add_argument('--assume-yes', action='store_true',
                        help='assume-yes when asked questions about certificates/redirections during sync (lower security)')
    parser.add_argument('--disable-http',action='store_true',
                        help='do not try to get http(s) links (but already cached will be displayed)')
    parser.add_argument('--fetch-later', action='store_true',
                        help='run non-interactively with an URL as argument to fetch it later')
    parser.add_argument('--depth',
                        help='depth of the cache to build. Default is 1. More is crazy. Use at your own risks!')
    parser.add_argument('--images-mode',
                        help='the mode to use to choose which images to download in a HTML page.\
                             one of (None, readable, full). Warning: full will slowdown your sync.')
    parser.add_argument('--cache-validity',
                        help='duration for which a cache is valid before sync (seconds)')
    parser.add_argument('--version', action='store_true',
                        help='display version information and quit')
    parser.add_argument('--features', action='store_true',
                        help='display available features and dependancies then quit')
    parser.add_argument('url', metavar='URL', nargs='*',
                        help='Arguments should be URL to be fetched or, if --sync is used, lists')
    args = parser.parse_args()

    # Handle --version
    if args.version:
        print("Offpunk " + __version__)
        sys.exit()
    elif args.features:
        GeminiClient.do_version(None,None)
        sys.exit()
    else:
        for f in [xdg("config"), xdg("data")]:
            if not os.path.exists(f):
                print("Creating config directory {}".format(f))
                os.makedirs(f)

    # Instantiate client
    gc = GeminiClient(synconly=args.sync)
    torun_queue = []

    # Interactive if offpunk started normally
    # False if started with --sync
    # Queue is a list of command (potentially empty)
    def read_config(queue,rcfile=None,interactive=True):
        if not rcfile:
            rcfile = os.path.join(xdg("config"), "offpunkrc")
        if os.path.exists(rcfile):
            print("Using config %s" % rcfile)
            with open(rcfile, "r") as fp:
                for line in fp:
                    line = line.strip()
                    if ((args.bookmarks or args.url) and
                        any((line.startswith(x) for x in ("go", "g", "tour", "t")))
                        ):
                        if args.bookmarks:
                            print("Skipping rc command \"%s\" due to --bookmarks option." % line)
                        else:
                            print("Skipping rc command \"%s\" due to provided URLs." % line)
                        continue
                    # We always consider redirect
                    # for the rest, we need to be interactive
                    if line.startswith("redirect") or interactive:
                        queue.append(line)
        return queue
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
                        gc.list_add_line("tour",u)
                    else:
                        gc.list_add_line("to_fetch",u)
                else:
                    print("%s is not a valid URL to fetch"%u)
        else:
            print("--fetch-later requires an URL (or a list of URLS) as argument")
    elif args.sync:
        if args.assume_yes:
            gc.automatic_choice = "y"
            gc.onecmd("set accept_bad_ssl_certificates True")
        if args.cache_validity:
            refresh_time = int(args.cache_validity)
        else:
            # if no refresh time, a default of 0 is used (which means "infinite")
            refresh_time = 0
        if args.images_mode and args.images_mode in ["none","readable","normal","full"]:
            gc.options["images_mode"] = args.images_mode
        if args.depth:
            depth = int(args.depth)
        else:
            depth = 1
        read_config(torun_queue,rcfile=args.config_file,interactive=False)
        for line in torun_queue:
            gc.onecmd(line)
        lists = None
        gc.call_sync(refresh_time=refresh_time,depth=depth,lists=args.url)
    else:
        # We are in the normal mode. First process config file
        torun_queue = read_config(torun_queue,rcfile=args.config_file,interactive=True)
        print("Welcome to Offpunk!")
        print("Type `help` to get the list of available command.")
        for line in torun_queue:
            gc.onecmd(line)

        while True:
            try:
                gc.cmdloop()
            except KeyboardInterrupt:
                print("")

if __name__ == '__main__':
    main()
