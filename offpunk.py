#TODO: migrate go_to_gi to netcache
#!/usr/bin/env python3
# Offpunk Offline Gemini client
# Derived from AV-98 by Solderpunk,
# (C) 2021, 2022 Ploum <offpunk110 at ploum.eu>
# (C) 2019, 2020 Solderpunk <solderpunk at sdf.org>
# With contributions from:
#  - danceka <hannu.hartikainen at gmail.com>
#  - <jprjr at tilde.club>
#  - <vee at vnsf.xyz>
#  - Klaus Alexander Seistrup <klaus at seistrup.dk>
#  - govynnus <govynnus at sdf.org>
#  - Björn Wärmedal <bjorn.warmedal at gmail.com>
#  - <jake at rmgr.dev>
#  - Maeve Sproule <code at sprock.dev>

"""
Offline-First Gemini/Web/Gopher/RSS reader and browser
"""

__version__ = "1.10"

import argparse
import cmd
import datetime
import fnmatch
import glob
import hashlib
import io
import os
import os.path
import filecmp
import random
import shlex
import shutil
import socket
import sqlite3
import sys
import time
import urllib.parse
import uuid
import webbrowser
import base64
import subprocess
import ansirenderer
import netcache
from offutils import run,term_width
try:
    import setproctitle
    setproctitle.setproctitle("offpunk")
    _HAS_SETPROCTITLE = True
except ModuleNotFoundError:
    _HAS_SETPROCTITLE = False


_HAS_XSEL = shutil.which('xsel')
_HAS_XDGOPEN = shutil.which('xdg-open')
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    _HAS_CRYPTOGRAPHY = True
    _BACKEND = default_backend()
except ModuleNotFoundError:
    _HAS_CRYPTOGRAPHY = False

try:
    import requests
    _DO_HTTP = True
except ModuleNotFoundError:
    _DO_HTTP = False



## Config directories
## We implement our own python-xdg to avoid conflict with existing libraries.
_home = os.path.expanduser('~')
data_home = os.environ.get('XDG_DATA_HOME') or \
            os.path.join(_home,'.local','share')
config_home = os.environ.get('XDG_CONFIG_HOME') or \
                os.path.join(_home,'.config')
_CONFIG_DIR = os.path.join(config_home,"offpunk/")
_DATA_DIR = os.path.join(data_home,"offpunk/")
_old_config = os.path.expanduser("~/.offpunk/")
## Look for pre-existing config directory, if any
if os.path.exists(_old_config):
    _CONFIG_DIR = _old_config
#if no XDG .local/share and not XDG .config, we use the old config
if not os.path.exists(data_home) and os.path.exists(_old_config):
    _DATA_DIR = _CONFIG_DIR
_MAX_CACHE_SIZE = 10
_MAX_CACHE_AGE_SECS = 180

_GREP = "grep --color=auto"
less_version = 0
if not shutil.which("less"):
    print("Please install the pager \"less\" to run Offpunk.")
    print("If you wish to use another pager, send me an email.")
    print("(I’m really curious to hear about people not having \"less\" on their system.)")
    sys.exit()
output = run("less --version")
# We get less Version (which is the only integer on the first line)
words = output.split("\n")[0].split()
less_version = 0
for w in words:
    if w.isdigit():
        less_version = int(w)
# restoring position only works for version of less > 572
if less_version >= 572:
    _LESS_RESTORE_POSITION = True
else:
    _LESS_RESTORE_POSITION = False
#_DEFAULT_LESS = "less -EXFRfM -PMurl\ lines\ \%lt-\%lb/\%L\ \%Pb\%$ %s"
# -E : quit when reaching end of file (to behave like "cat")
# -F : quit if content fits the screen (behave like "cat")
# -X : does not clear the screen
# -R : interpret ANSI colors correctly
# -f : suppress warning for some contents
# -M : long prompt (to have info about where you are in the file)
# -W : hilite the new first line after a page skip (space)
# -i : ignore case in search
# -S : do not wrap long lines. Wrapping is done by offpunk, longlines
# are there on purpose (surch in asciiart)
#--incsearch : incremental search starting rev581
if less_version >= 581:
    less_base = "less --incsearch --save-marks -~ -XRfMWiS"
elif less_version >= 572:
    less_base = "less --save-marks -XRfMWiS"
else:
    less_base = "less -XRfMWiS"
_DEFAULT_LESS = less_base + " \"+''\" %s"
_DEFAULT_CAT = less_base + " -EF %s"
def less_cmd(file, histfile=None,cat=False,grep=None):
    if histfile:
        env = {"LESSHISTFILE": histfile}
    else:
        env = {}
    if cat:
        cmd_str = _DEFAULT_CAT
    elif grep:
        grep_cmd = _GREP
        #case insensitive for lowercase search
        if grep.islower():
            grep_cmd += " -i"
        cmd_str = _DEFAULT_CAT + "|" + grep_cmd + " %s"%grep
    else:
        cmd_str = _DEFAULT_LESS
    run(cmd_str, parameter=file, direct_output=True, env=env)

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

#An IPV6 URL should be put between []
#We try to detect them has location with more than 2 ":"
def fix_ipv6_url(url):
    if not url or url.startswith("mailto"):
        return url
    if "://" in url:
        schema, schemaless = url.split("://",maxsplit=1)
    else:
        schema, schemaless = None, url
    if "/" in schemaless:
        netloc, rest = schemaless.split("/",1)
        if netloc.count(":") > 2 and "[" not in netloc and "]" not in netloc:
            schemaless = "[" + netloc + "]" + "/" + rest
    elif schemaless.count(":") > 2:
        schemaless = "[" + schemaless + "]/"
    if schema:
        return schema + "://" + schemaless
    return schemaless

# Offpunk is organized as follow:
# - a GeminiClient instance which handles the browsing of GeminiItems (= pages).
# - There’s only one GeminiClient. Each page is a GeminiItem (name is historical, as
# it could be non-gemini content)
# - A GeminiItem is created with an URL from which it will derives content.
# - Content include : a title, a body (raw source) and a renderer. The renderer will provide
#                     ANSI rendered version of the content and a list of links
# - Each GeminiItem generates a "cache_path" in which it maintains a cached version of its content.

class GeminiItem():

    def __init__(self, url, name=""):
        self.last_mode = None
        findmode = url.split("##offpunk_mode=")
        if len(findmode) > 1:
            self.url = findmode[0]
            if findmode[1] in ["full"] or findmode[1].isnumeric():
                self.last_mode = findmode[1]
        else:
            self.url = url
        self.url = fix_ipv6_url(self.url).strip()
        self._cache_path = self.get_cache_path()
        self.name = name
        self.mime = None
        self.renderer = ansirenderer.renderer_from_file(self._cache_path,self.url)
        #TODO : stuff have been migrated to netcache. What are we missing here ?
        self.scheme = "https"
        self.local = False

    def get_cache_path(self):
        # if we already have a _cache_path, we returns it.
        # Except if it became a folder! (which happens for index.html/index.gmi)
        # In that case, we need to reconstruct it
        # TODO: ensure that the following two lines are not needed in netcache
        #if self._cache_path and not os.path.isdir(self._cache_path):
        #    return self._cache_path
        return netcache.get_cache_path(self.url)

    def get_page_title(self):
        title = ""
        if self.renderer:
            title = self.renderer.get_title()
        if not title or len(title) == 0:
            title = self.renderer.get_url_title()
        else:
            title += " (%s)" %self.renderer.get_url_title()
        return title

    def is_cache_valid(self,validity=0):
        return netcache.is_cache_valid(self.url,validity=validity)

    def cache_last_modified(self):
        return netcache.cache_last_modified(self.url)

    def get_body(self,as_file=False):
        if self.is_cache_valid():
            path = self.get_cache_path()
        else:
            path = None
        if path:
            # There’s on OS limit on path length
            if len(path) > 259:
                toreturn = "Path is too long. This is an OS limitation.\n\n"
                toreturn += self.url
                return toreturn
            elif as_file:
                return path
            else:
                with open(path) as f:
                    body = f.read()
                    f.close()
                return body
        else:
            #print("ERROR: NO CACHE for %s" %self._cache_path)
            return None

    def get_images(self,mode=None):
        if self.renderer:
            return self.renderer.get_images(mode=mode)
        else:
            return []

    # This method is used to load once the list of links in a gi
    # Links can be followed, after a space, by a description/title
    def get_links(self,mode=None):
        links = []
        toreturn = []
        if self.renderer:
            if not mode:
                mode = self.last_mode
            links = self.renderer.get_links(mode=mode)
        for l in links:
            #split between link and potential name
            # check that l is non-empty
            url = None
            if l:
                splitted = l.split(maxsplit=1)
                url = self.absolutise_url(splitted[0])
            if url and looks_like_url(url):
                if len(splitted) > 1:
                    #We add a name only for Gopher items
                    if url.startswith("gopher://"):
                        newgi = GeminiItem(url,name=splitted[1])
                    else:
                        newgi = GeminiItem(url)
                else:
                    newgi = GeminiItem(url)
                toreturn.append(newgi)
            elif url and mode != "links_only" and url.startswith("data:image/"):
                imgurl,imgdata = ansirenderer.looks_like_base64(url,self.url)
                if imgurl:
                    toreturn.append(GeminiItem(imgurl))
                else:
                    toreturn.append(None)
            else:
                # We must include a None item to keep the link count valid
                toreturn.append(None)
        return toreturn

    def get_link(self,nb):
        # == None allows to return False, even if the list is empty
        links = self.get_links()
        if len(links) < nb:
            print("Index too high! No link %s for %s" %(nb,self.url))
            return None
        else:
            return links[nb-1]

    def get_subscribe_links(self):
        if self.renderer:
            subs = self.renderer.get_subscribe_links()
            abssubs = []
            # some rss links are relatives
            for s in subs:
                s[0] = self.absolutise_url(s[0])
                abssubs.append(s)
            return abssubs
        else:
            return []


    def display(self,mode=None,grep=None):
        if self.renderer and self.renderer.is_valid():
            if not mode:
                mode = self.last_mode
            else:
                self.last_mode = mode
            title = self.renderer.get_url_title()
            if self.is_cache_valid(): #and self.offline_only and not self.local:
                nbr = len(self.get_links(mode=mode))
                if self.local:
                    title += " (%s items)"%nbr
                    str_last = "local file"
                else:
                    str_last = "last accessed on %s" %time.ctime(self.cache_last_modified())
                    title += " (%s links)"%nbr
                return self.renderer.display(mode=mode,window_title=title,window_info=str_last,grep=grep)
            else:
                return False
        else:
            return False

    def get_filename(self):
        filename = os.path.basename(self.get_cache_path())
        return filename

    def get_temp_filename(self):
        tmpf = None
        if self.renderer and self.renderer.is_valid():
            tmpf = self.renderer.get_temp_file()
        cache_path = self.get_cache_path()
        if not tmpf and cache_path:
            tmpf = cache_path
        return tmpf



    def set_error(self,err):
    # If we get an error, we want to keep an existing cache
    # but we need to touch it or to create an empty one
    # to avoid hitting the error at each refresh
        cache = self.get_cache_path()
        if self.is_cache_valid():
            os.utime(cache)
        else:
            cache_dir = os.path.dirname(cache)
            root_dir = cache_dir
            while not os.path.exists(root_dir):
                root_dir = os.path.dirname(root_dir)
            if os.path.isfile(root_dir):
                os.remove(root_dir)
            os.makedirs(cache_dir,exist_ok=True)
            if os.path.isdir(cache_dir):
                with open(cache, "w") as cache:
                    cache.write(str(datetime.datetime.now())+"\n")
                    cache.write("ERROR while caching %s\n\n" %self.url)
                    cache.write("*****\n\n")
                    cache.write(str(type(err)) + " = " + str(err))
                    #cache.write("\n" + str(err.with_traceback(None)))
                    cache.write("\n*****\n\n")
                    cache.write("If you believe this error was temporary, type ""reload"".\n")
                    cache.write("The ressource will be tentatively fetched during next sync.\n")
                    cache.close()


    def root(self):
        return GeminiItem(self._derive_url("/"))

    def up(self,level=1):
        path = self.path.rstrip('/')
        count = 0
        while count < level:
            pathbits = list(os.path.split(path))
            # Don't try to go higher than root or in config
            if self.local or len(pathbits) == 1 :
                return self
            # Get rid of bottom component
            if len(pathbits) > 1:
                pathbits.pop()
            path = os.path.join(*pathbits)
            count += 1
        if self.scheme == "gopher":
            path = "/1" + path
        return GeminiItem(self._derive_url(path))

    def query(self, query):
        query = urllib.parse.quote(query)
        return GeminiItem(self._derive_url(query=query))

    def _derive_url(self, path="", query=""):
        """
        A thin wrapper around urlunparse which avoids inserting standard ports
        into URLs just to keep things clean.
        """
        if not self.port or self.port == netcache.standard_ports[self.scheme] :
            host = self.host
        else:
            host = self.host + ":" + str(self.port)
        return urllib.parse.urlunparse((self.scheme,host,path or self.path, "", query, ""))

    def absolutise_url(self, relative_url):
        """
        Convert a relative URL to an absolute URL by using the URL of this
        GeminiItem as a base.
        """
        try:
            abs_url = urllib.parse.urljoin(self.url, relative_url)
        except ValueError as e:
            abs_url = None
        return abs_url

    def url_mode(self):
        url = self.url
        if self.last_mode and self.last_mode != "readable":
            url += "##offpunk_mode=" + self.last_mode
        return url

    #what is the line to add to a list for this url ?
    def to_map_line(self):
        return "=> {} {}\n".format(self.url_mode(), self.get_page_title())


# Cheap and cheerful URL detector
def looks_like_url(word):
    try:
        if not word.strip():
            return False
        url = fix_ipv6_url(word).strip()
        parsed = urllib.parse.urlparse(url)
        #sometimes, urllib crashed only when requesting the port
        port = parsed.port
        mailto = word.startswith("mailto:")
        scheme = word.split("://")[0]
        start = scheme in netcache.standard_ports
        local = scheme in ["file","list"]
        if not start and not local and not mailto:
            return looks_like_url("gemini://"+word)
        elif mailto:
            return "@" in word
        elif not local:
            return "." in word or "localhost" in word
        else:
            return "/" in word
    except ValueError:
        return False


class UserAbortException(Exception):
    pass

# GeminiClient Decorators
def needs_gi(inner):
    def outer(self, *args, **kwargs):
        if not self.gi:
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


        self.no_cert_prompt = "\001\x1b[38;5;76m\002" + "ON" + "\001\x1b[38;5;255m\002" + "> " + "\001\x1b[0m\002"
        self.cert_prompt = "\001\x1b[38;5;202m\002" + "ON" + "\001\x1b[38;5;255m\002"
        self.offline_prompt = "\001\x1b[38;5;76m\002" + "OFF" + "\001\x1b[38;5;255m\002" + "> " + "\001\x1b[0m\001"
        self.prompt = self.no_cert_prompt
        self.gi = None
        self.hist_index = 0
        self.index = []
        self.index_index = -1
        self.marks = {}
        self.page_index = 0
        self.permanent_redirects = {}
        # Sync-only mode is restriced by design
        self.visited_hosts = set()
        self.offline_only = False
        self.sync_only = False
        self.support_http = _DO_HTTP
        self.automatic_choice = "n"

        self.client_certs = {
            "active": None
        }
        self.active_cert_domains = []
        self.active_is_transient = False
        self.transient_certs_created = []

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
            "redirects" : True,
            # the wikipedia entry needs two %s, one for lang, other for search
            "wikipedia" : "gemini://vault.transjovian.org:1965/search/%s/%s",
            "search"    : "gemini://kennedy.gemi.dev/search?%s",
            "accept_bad_ssl_certificates" : False,
        }

        self.redirects = {
            "twitter.com" : "nitter.42l.fr",
            "facebook.com" : "blocked",
            "doubleclick.net": "blocked",
            "google-analytics.com" : "blocked",
            "youtube.com" : "yewtu.be",
            "reddit.com"  : "teddit.net",
            "old.reddit.com": "teddit.net",
            "medium.com"  : "scribe.rip",

        }
        term_width(new_width=self.options["width"])
        self.log = {
            "start_time": time.time(),
            "requests": 0,
            "ipv4_requests": 0,
            "ipv6_requests": 0,
            "bytes_recvd": 0,
            "ipv4_bytes_recvd": 0,
            "ipv6_bytes_recvd": 0,
            "dns_failures": 0,
            "refused_connections": 0,
            "reset_connections": 0,
            "timeouts": 0,
            "cache_hits": 0,
        }

        self._connect_to_tofu_db()

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

    def _connect_to_tofu_db(self):

        db_path = os.path.join(_CONFIG_DIR, "tofu.db")
        self.db_conn = sqlite3.connect(db_path)
        self.db_cur = self.db_conn.cursor()

        self.db_cur.execute("""CREATE TABLE IF NOT EXISTS cert_cache
            (hostname text, address text, fingerprint text,
            first_seen date, last_seen date, count integer)""")

    def _go_to_gi(self, gi, update_hist=True, check_cache=True, handle=True,\
                                                mode=None,limit_size=False):
        """This method might be considered "the heart of Offpunk".
        Everything involved in fetching a gemini resource happens here:
        sending the request over the network, parsing the response,
        storing the response in a temporary file, choosing
        and calling a handler program, and updating the history.
        Nothing is returned."""
        if not gi:
            return
        # Don't try to speak to servers running other protocols
        #TODO: support for mailto and unsupported protocols
       # elif gi.scheme == "mailto":
       #     if handle and not self.sync_only:
       #         resp = input("Send an email to %s Y/N? " %gi.path)
       #         self.gi = gi
       #         if resp.strip().lower() in ("y", "yes"):
       #             if _HAS_XDGOPEN :
       #                 run("xdg-open mailto:%s", parameter=gi.path ,direct_output=True)
       #             else:
       #                 print("Cannot find a mail client to send mail to %s" %gi.path)
       #                 print("Please install xdg-open (usually from xdg-util package)")
       #     return
       # elif gi.scheme not in ["file","list"] and gi.scheme not in netcache.standard_ports \
       #                                                         and not self.sync_only:
       #     print("Sorry, no support for {} links.".format(gi.scheme))
       #     return

        if not mode:
            mode = gi.last_mode
        # Obey permanent redirects
        if gi.url in self.permanent_redirects:
            new_gi = GeminiItem(self.permanent_redirects[gi.url], name=gi.name)
            self._go_to_gi(new_gi,mode=mode)
            return

        # Use cache or mark as to_fetch if resource is not cached
        # Why is this code useful ? It set the mimetype !
        if self.offline_only:
            if not gi.is_cache_valid():
                self.get_list("to_fetch")
                r = self.list_add_line("to_fetch",gi=gi,verbose=False)
                if r:
                    print("%s not available, marked for syncing"%gi.url)
                else:
                    print("%s already marked for syncing"%gi.url)
                return
        # check if local file exists.
        if gi.local and not os.path.exists(gi.path):
            print("Local file %s does not exist!" %gi.path)
            return

        elif not self.offline_only and not gi.local:
            try:
                params = {}
                params["timeout"] = self.options["short_timeout"]
                params["max_size"] = int(self.options["max_size_download"])*1000000
                cachepath = netcache.fetch(gi.url,**params)
            except UserAbortException:
                return
            except Exception as err:
                gi.set_error(err)
                # Print an error message
                # we fail silently when sync_only
                print_error = not self.sync_only
                if isinstance(err, socket.gaierror):
                    self.log["dns_failures"] += 1
                    if print_error:
                        print("ERROR: DNS error!")
                elif isinstance(err, ConnectionRefusedError):
                    self.log["refused_connections"] += 1
                    if print_error:
                        print("ERROR1: Connection refused!")
                elif isinstance(err, ConnectionResetError):
                    self.log["reset_connections"] += 1
                    if print_error:
                        print("ERROR2: Connection reset!")
                elif isinstance(err, (TimeoutError, socket.timeout)):
                    self.log["timeouts"] += 1
                    if print_error:
                        print("""ERROR3: Connection timed out!
        Slow internet connection?  Use 'set timeout' to be more patient.""")
                elif isinstance(err, FileExistsError):
                    print("""ERROR5: Trying to create a directory which already exists
                            in the cache : """)
                    print(err)
                elif _DO_HTTP and isinstance(err,requests.exceptions.SSLError):
                    print("""ERROR6: Bad SSL certificate:\n""")
                    print(err)
                    print("""\n If you know what you are doing, you can try to accept bad certificates with the following command:\n""")
                    print("""set accept_bad_ssl_certificates True""")
                else:
                    if print_error:
                        import traceback
                        print("ERROR4: " + str(type(err)) + " : " + str(err))
                        print("\n" + str(err.with_traceback(None)))
                        print(traceback.format_exc())
                return

        # Pass file to handler, unless we were asked not to
        if netcache.is_cache_valid(gi.url) :
            display = handle and not self.sync_only
            #TODO: take into account _RENDER_IMAGE
            if display and self.options["download_images_first"] \
                                                        and not self.offline_only:
                # We download images first
                for image in gi.get_images(mode=mode):
                    if image and image.startswith("http"):
                        img_gi = GeminiItem(image)
                        if not img_gi.is_cache_valid():
                            width = term_width() - 1
                            toprint = "Downloading %s" %image
                            toprint = toprint[:width]
                            toprint += " "*(width-len(toprint))
                            print(toprint,end="\r")
                            self._go_to_gi(img_gi, update_hist=False, check_cache=True, \
                                                handle=False,limit_size=True)
            if display and gi.display(mode=mode):
                self.index = gi.get_links()
                self.page_index = 0
                self.index_index = -1
                # Update state (external files are not added to history)
                self.gi = gi
                if update_hist and not self.sync_only:
                    self._update_history(gi)
            elif display :
                cmd_str = self._get_handler_cmd(gi.get_mime())
                try:
                    # get body (tmpfile) from gi !
                    run(cmd_str, parameter=gi.get_body(as_file=True), direct_output=True)
                except FileNotFoundError:
                    print("Handler program %s not found!" % shlex.split(cmd_str)[0])
                    print("You can use the ! command to specify another handler program or pipeline.")





    def _handle_cert_request(self, meta):
        print("SERVER SAYS: ", meta)
        # Present different messages for different 6x statuses, but
        # handle them the same.
        if status in ("64", "65"):
            print("The server rejected your certificate because it is either expired or not yet valid.")
        elif status == "63":
            print("The server did not accept your certificate.")
            print("You may need to e.g. coordinate with the admin to get your certificate fingerprint whitelisted.")
        else:
            print("The site {} is requesting a client certificate.".format(gi.host))
            print("This will allow the site to recognise you across requests.")

        # Give the user choices
        print("What do you want to do?")
        print("1. Give up.")
        print("2. Generate a new transient certificate.")
        print("3. Generate a new persistent certificate.")
        print("4. Load a previously generated persistent.")
        print("5. Load certificate from an external file.")
        if self.sync_only:
            choice = 1
        else:
            choice = input("> ").strip()
        if choice == "2":
            self._generate_transient_cert_cert()
        elif choice == "3":
            self._generate_persistent_client_cert()
        elif choice == "4":
            self._choose_client_cert()
        elif choice == "5":
            self._load_client_cert()
        else:
            print("Giving up.")
            raise UserAbortException()

    def _validate_cert(self, address, host, cert):
        """
        Validate a TLS certificate in TOFU mode.

        If the cryptography module is installed:
         - Check the certificate Common Name or SAN matches `host`
         - Check the certificate's not valid before date is in the past
         - Check the certificate's not valid after date is in the future

        Whether the cryptography module is installed or not, check the
        certificate's fingerprint against the TOFU database to see if we've
        previously encountered a different certificate for this IP address and
        hostname.
        """
        now = datetime.datetime.utcnow()
        if _HAS_CRYPTOGRAPHY:
            # Using the cryptography module we can get detailed access
            # to the properties of even self-signed certs, unlike in
            # the standard ssl library...
            c = x509.load_der_x509_certificate(cert, _BACKEND)
            # Check certificate validity dates
            if not self.options["accept_bad_ssl_certificates"]:
                if c.not_valid_before >= now:
                    raise CertificateError("Certificate not valid until: {}!".format(c.not_valid_before))
                elif c.not_valid_after <= now:
                    raise CertificateError("Certificate expired as of: {})!".format(c.not_valid_after))

            # Check certificate hostnames
            names = []
            common_name = c.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            if common_name:
                names.append(common_name[0].value)
            try:
                names.extend([alt.value for alt in c.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value])
            except x509.ExtensionNotFound:
                pass
            names = set(names)
            for name in names:
                try:
                    ssl._dnsname_match(str(name), host)
                    break
                except CertificateError:
                    continue
            else:
                # If we didn't break out, none of the names were valid
                raise CertificateError("Hostname does not match certificate common name or any alternative names.")

        sha = hashlib.sha256()
        sha.update(cert)
        fingerprint = sha.hexdigest()

        # Have we been here before?
        self.db_cur.execute("""SELECT fingerprint, first_seen, last_seen, count
            FROM cert_cache
            WHERE hostname=? AND address=?""", (host, address))
        cached_certs = self.db_cur.fetchall()

        # If so, check for a match
        if cached_certs:
            max_count = 0
            most_frequent_cert = None
            for cached_fingerprint, first, last, count in cached_certs:
                if count > max_count:
                    max_count = count
                    most_frequent_cert = cached_fingerprint
                if fingerprint == cached_fingerprint:
                    # Matched!
                    self._debug("TOFU: Accepting previously seen ({} times) certificate {}".format(count, fingerprint))
                    self.db_cur.execute("""UPDATE cert_cache
                        SET last_seen=?, count=?
                        WHERE hostname=? AND address=? AND fingerprint=?""",
                        (now, count+1, host, address, fingerprint))
                    self.db_conn.commit()
                    break
            else:
                certdir = os.path.join(_CONFIG_DIR, "cert_cache")
                with open(os.path.join(certdir, most_frequent_cert+".crt"), "rb") as fp:
                    previous_cert = fp.read()
                if _HAS_CRYPTOGRAPHY:
                    # Load the most frequently seen certificate to see if it has
                    # expired
                    previous_cert = x509.load_der_x509_certificate(previous_cert, _BACKEND)
                    previous_ttl = previous_cert.not_valid_after - now
                    print(previous_ttl)

                self._debug("TOFU: Unrecognised certificate {}!  Raising the alarm...".format(fingerprint))
                print("****************************************")
                print("[SECURITY WARNING] Unrecognised certificate!")
                print("The certificate presented for {} ({}) has never been seen before.".format(host, address))
                print("This MIGHT be a Man-in-the-Middle attack.")
                print("A different certificate has previously been seen {} times.".format(max_count))
                if _HAS_CRYPTOGRAPHY:
                    if previous_ttl < datetime.timedelta():
                        print("That certificate has expired, which reduces suspicion somewhat.")
                    else:
                        print("That certificate is still valid for: {}".format(previous_ttl))
                print("****************************************")
                print("Attempt to verify the new certificate fingerprint out-of-band:")
                print(fingerprint)
                if self.sync_only:
                    choice = self.automatic_choice
                else:
                    choice = input("Accept this new certificate? Y/N ").strip().lower()
                if choice in ("y", "yes"):
                    self.db_cur.execute("""INSERT INTO cert_cache
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (host, address, fingerprint, now, now, 1))
                    self.db_conn.commit()
                    with open(os.path.join(certdir, fingerprint+".crt"), "wb") as fp:
                        fp.write(cert)
                else:
                    raise Exception("TOFU Failure!")

        # If not, cache this cert
        else:
            self._debug("TOFU: Blindly trusting first ever certificate for this host!")
            self.db_cur.execute("""INSERT INTO cert_cache
                VALUES (?, ?, ?, ?, ?, ?)""",
                (host, address, fingerprint, now, now, 1))
            self.db_conn.commit()
            certdir = os.path.join(_CONFIG_DIR, "cert_cache")
            if not os.path.exists(certdir):
                os.makedirs(certdir)
            with open(os.path.join(certdir, fingerprint+".crt"), "wb") as fp:
                fp.write(cert)
    
    def _get_handler_cmd(self, mimetype):
        # Now look for a handler for this mimetype
        # Consider exact matches before wildcard matches
        exact_matches = []
        wildcard_matches = []
        for handled_mime, cmd_str in _MIME_HANDLERS.items():
            if "*" in handled_mime:
                wildcard_matches.append((handled_mime, cmd_str))
            else:
                exact_matches.append((handled_mime, cmd_str))
        for handled_mime, cmd_str in exact_matches + wildcard_matches:
            if fnmatch.fnmatch(mimetype, handled_mime):
                break
        else:
            # Use "xdg-open" as a last resort.
            if _HAS_XDGOPEN:
                cmd_str = "xdg-open %s"
            else:
                cmd_str = "echo \"Can’t find how to open \"%s"
                print("Please install xdg-open (usually from xdg-util package)")
        return cmd_str

    #TODO: remove format_geminiitem
    def _format_geminiitem(self, index, gi, url=False):
        if not gi:
            line = "[%s] - No valid URL"%index
        else:
            protocol = "" if gi.scheme == "gemini" else " %s" % gi.scheme
            line = "[%d%s] %s" % (index, protocol, gi.name or gi.url)
            if gi.name and url:
                line += " (%s)" % gi.url
        return line

    @needs_gi
    def _show_lookup(self, offset=0, end=None, url=False):
        for n, gi in enumerate(self.gi.get_links()[offset:end]):
            print(self._format_geminiitem(n+offset+1, gi, url))

    def _update_history(self, gi):
        # We never update while in sync_only
        if self.sync_only:
            return
        # We don’t add lists to history
        #if not gi or os.path.join(_DATA_DIR,"lists") in gi.url:
        #    return
        histlist = self.get_list("history")
        links = self.list_get_links("history")
        # avoid duplicate
        length = len(links)
        if length > self.options["history_size"]:
            length = self.options["history_size"]
        if length > 0 and links[self.hist_index] == gi:
            return
        self.list_add_top("history",limit=self.options["history_size"],truncate_lines=self.hist_index)
        self.hist_index = 0


    def _log_visit(self, gi, address, size):
        if not address:
            return
        self.log["requests"] += 1
        self.log["bytes_recvd"] += size
        self.visited_hosts.add(address)
        if address[0] == socket.AF_INET:
            self.log["ipv4_requests"] += 1
            self.log["ipv4_bytes_recvd"] += size
        elif address[0] == socket.AF_INET6:
            self.log["ipv6_requests"] += 1
            self.log["ipv6_bytes_recvd"] += size

    def _debug(self, debug_text):
        if not self.options["debug"]:
            return
        debug_text = "\x1b[0;32m[DEBUG] " + debug_text + "\x1b[0m"
        print(debug_text)

    def _load_client_cert(self):
        """
        Interactively load a TLS client certificate from the filesystem in PEM
        format.
        """
        print("Loading client certificate file, in PEM format (blank line to cancel)")
        certfile = input("Certfile path: ").strip()
        if not certfile:
            print("Aborting.")
            return
        certfile = os.path.expanduser(certfile)
        if not os.path.isfile(certfile):
            print("Certificate file {} does not exist.".format(certfile))
            return
        print("Loading private key file, in PEM format (blank line to cancel)")
        keyfile = input("Keyfile path: ").strip()
        if not keyfile:
            print("Aborting.")
            return
        keyfile = os.path.expanduser(keyfile)
        if not os.path.isfile(keyfile):
            print("Private key file {} does not exist.".format(keyfile))
            return
        self._activate_client_cert(certfile, keyfile)

    def _generate_transient_cert_cert(self):
        """
        Use `openssl` command to generate a new transient client certificate
        with 24 hours of validity.
        """
        certdir = os.path.join(_CONFIG_DIR, "transient_certs")
        name = str(uuid.uuid4())
        self._generate_client_cert(certdir, name, transient=True)
        self.active_is_transient = True
        self.transient_certs_created.append(name)

    def _generate_persistent_client_cert(self):
        """
        Interactively use `openssl` command to generate a new persistent client
        certificate with one year of validity.
        """
        certdir = os.path.join(_CONFIG_DIR, "client_certs")
        print("What do you want to name this new certificate?")
        print("Answering `mycert` will create `{0}/mycert.crt` and `{0}/mycert.key`".format(certdir))
        name = input("> ")
        if not name.strip():
            print("Aborting.")
            return
        self._generate_client_cert(certdir, name)

    def _generate_client_cert(self, certdir, basename, transient=False):
        """
        Use `openssl` binary to generate a client certificate (which may be
        transient or persistent) and save the certificate and private key to the
        specified directory with the specified basename.
        """
        if not os.path.exists(certdir):
            os.makedirs(certdir)
        certfile = os.path.join(certdir, basename+".crt")
        keyfile = os.path.join(certdir, basename+".key")
        cmd = "openssl req -x509 -newkey rsa:2048 -days {} -nodes -keyout {} -out {}".format(1 if transient else 365, keyfile, certfile)
        if transient:
            cmd += " -subj '/CN={}'".format(basename)
        os.system(cmd)
        self._activate_client_cert(certfile, keyfile)

    def _choose_client_cert(self):
        """
        Interactively select a previously generated client certificate and
        activate it.
        """
        certdir = os.path.join(_CONFIG_DIR, "client_certs")
        certs = glob.glob(os.path.join(certdir, "*.crt"))
        if len(certs) == 0:
            print("There are no previously generated certificates.")
            return
        certdir = {}
        for n, cert in enumerate(certs):
            certdir[str(n+1)] = (cert, os.path.splitext(cert)[0] + ".key")
            print("{}. {}".format(n+1, os.path.splitext(os.path.basename(cert))[0]))
        choice = input("> ").strip()
        if choice in certdir:
            certfile, keyfile = certdir[choice]
            self._activate_client_cert(certfile, keyfile)
        else:
            print("What?")

    def _activate_client_cert(self, certfile, keyfile):
        self.client_certs["active"] = (certfile, keyfile)
        self.active_cert_domains = []
        self.prompt = self.cert_prompt + "+" + os.path.basename(certfile).replace('.crt','') + "> " + "\001\x1b[0m\002"
        self._debug("Using ID {} / {}.".format(*self.client_certs["active"]))

    def _deactivate_client_cert(self):
        if self.active_is_transient:
            for filename in self.client_certs["active"]:
                os.remove(filename)
            for domain in self.active_cert_domains:
                self.client_certs.pop(domain)
        self.client_certs["active"] = None
        self.active_cert_domains = []
        self.prompt = self.no_cert_prompt
        self.active_is_transient = False

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
        # if we have no GeminiItem, there's nothing to do
        if self.gi is None:
            print("No links to index")
            return
        try:
            gi = self.gi.get_link(n)
        except IndexError:
            print ("Index too high!")
            return

        self.index_index = n
        self._go_to_gi(gi)

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
                    requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = 'ALL:@SECLEVEL=2'
                elif value.lower() == "true":
                    print("Low security SSL certificates are now accepted")
                    requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = 'ALL:@SECLEVEL=1'
                else:
                    print("accept_bad_ssl_certificates should be True or False")
                    return
            elif option == "width":
                if value.isnumeric():
                    value = int(value)
                    print("changing width to ",value)
                    term_width(new_width=value)
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

    def do_cert(self, line):
        """Manage client certificates"""
        print("Managing client certificates")
        if self.client_certs["active"]:
            print("Active certificate: {}".format(self.client_certs["active"][0]))
        print("1. Deactivate client certificate.")
        print("2. Generate new certificate.")
        print("3. Load previously generated certificate.")
        print("4. Load externally created client certificate from file.")
        print("Enter blank line to exit certificate manager.")
        choice = input("> ").strip()
        if choice == "1":
            print("Deactivating client certificate.")
            self._deactivate_client_cert()
        elif choice == "2":
            self._generate_persistent_client_cert()
        elif choice == "3":
            self._choose_client_cert()
        elif choice == "4":
            self._load_client_cert()
        else:
            print("Aborting.")

    def do_handler(self, line):
        """View or set handler commands for different MIME types."""
        if not line.strip():
            # Show all current handlers
            for mime in sorted(_MIME_HANDLERS.keys()):
                print("%s   %s" % (mime, _MIME_HANDLERS[mime]))
        elif len(line.split()) == 1:
            mime = line.strip()
            if mime in _MIME_HANDLERS:
                print("%s   %s" % (mime, _MIME_HANDLERS[mime]))
            else:
                print("No handler set for MIME type %s" % mime)
        else:
            mime, handler = line.split(" ", 1)
            _MIME_HANDLERS[mime] = handler
            if "%s" not in handler:
                print("Are you sure you don't want to pass the filename to the handler?")

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
            self.prompt = self.offline_prompt
            print("Offpunk is now offline and will only access cached content")

    def do_online(self, *args):
        """Use Offpunk online with a direct connection"""
        if self.offline_only:
            self.offline_only = False
            self.prompt = self.no_cert_prompt
            print("Offpunk is online and will access the network")
        else:
            print("Already online. Try offline.")

    def do_copy(self, arg):
        """Copy the content of the last visited page as gemtext in the clipboard.
Use with "url" as argument to only copy the adress.
Use with "raw" to copy ANSI content as seen in your terminal (not gemtext).
Use with "cache" to copy the path of the cached content."""
        if self.gi:
            if _HAS_XSEL:
                args = arg.split()
                if args and args[0] == "url":
                    if len(args) > 1 and args[1].isdecimal():
                        gi = self.index[int(args[1])-1]
                        url = gi.url
                    else:
                        url = self.gi.url
                    run("xsel -b -i", input=url, direct_output=True)
                elif args and args[0] == "raw":
                    run("xsel -b -i", input=open(self.gi.get_temp_filename(), "rb"), direct_output=True)
                elif args and args[0] == "cache":
                    run("xsel -b -i", input=self.gi.get_cache_path(), direct_output=True)
                else:
                    run("xsel -b -i", input=open(self.gi.get_body(as_file=True), "rb"), direct_output=True)
            else:
                print("Please install xsel to use copy")
        else:
            print("No content to copy, visit a page first")

    ### Stuff for getting around
    def do_go(self, line):
        """Go to a gemini URL or marked item."""
        line = line.strip()
        if not line:
            if shutil.which('xsel'):
                clipboards = []
                urls = []
                for selec in ["-p","-s","-b"]:
                    try:
                        clipboards.append(run("xsel "+selec))
                    except Exception as err:
                        #print("Skippink clipboard %s because %s"%(selec,err))
                        pass
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
            else:
                print("Go where? (hint: install xsel to go to copied URLs)")

        # First, check for possible marks
        elif line in self.marks:
            gi = self.marks[line]
            self._go_to_gi(gi)
        # or a local file
        elif os.path.exists(os.path.expanduser(line)):
            self._go_to_gi(GeminiItem(line))
        # If this isn't a mark, treat it as a URL
        elif looks_like_url(line):
            self._go_to_gi(GeminiItem(line))
        else:
            print("%s is not a valid URL to go"%line)

    @needs_gi
    def do_reload(self, *args):
        """Reload the current URL."""
        if self.offline_only:
            self.get_list("to_fetch")
            r = self.list_add_line("to_fetch",gi=self.gi,verbose=False)
            if r:
                print("%s marked for syncing" %self.gi.url)
            else:
                print("%s already marked for syncing" %self.gi.url)
        else:
            self._go_to_gi(self.gi, check_cache=False)

    @needs_gi
    def do_up(self, *args):
        """Go up one directory in the path.
Take an integer as argument to go up multiple times."""
        level = 1
        if args[0].isnumeric():
            level = int(args[0])
        elif args[0] != "":
            print("Up only take integer as arguments")
        self._go_to_gi(self.gi.up(level=level))

    def do_back(self, *args):
        """Go back to the previous gemini item."""
        histfile = self.get_list("history")
        links = self.list_get_links("history")
        if self.hist_index >= len(links) -1:
            return
        self.hist_index += 1
        gi = links[self.hist_index]
        self._go_to_gi(gi, update_hist=False)

    def do_forward(self, *args):
        """Go forward to the next gemini item."""
        histfile = self.get_list("history")
        links = self.list_get_links("history")
        if self.hist_index <= 0:
            return
        self.hist_index -= 1
        gi = links[self.hist_index]
        self._go_to_gi(gi, update_hist=False)

    @needs_gi
    def do_root(self, *args):
        """Go to root selector of the server hosting current item."""
        self._go_to_gi(self.gi.root())

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
                self.list_rm_url(l.url_mode(),"tour")
        elif line == "*":
            for l in self.gi.get_links():
                self.list_add_line("tour",gi=l,verbose=False)
        elif line == ".":
            self.list_add_line("tour",verbose=False)
        elif looks_like_url(line):
            self.list_add_line("tour",gi=GeminiItem(line))
        elif line in self.list_lists():
            list_path = self.list_path(line)
            if not list_path:
                print("List %s does not exist. Cannot add it to tour"%(list))
            else:
                gi = GeminiItem("list:///%s"%line)
                display = not self.sync_only
                if gi:
                    for l in gi.get_links():
                        self.list_add_line("tour",gi=l,verbose=False)
        else:
            for index in line.split():
                try:
                    pair = index.split('-')
                    if len(pair) == 1:
                        # Just a single index
                        n = int(index)
                        gi = self.gi.get_link(n)
                        self.list_add_line("tour",gi=gi,verbose=False)
                    elif len(pair) == 2:
                        # Two endpoints for a range of indices
                        if int(pair[0]) < int(pair[1]):
                            for n in range(int(pair[0]), int(pair[1]) + 1):
                                gi = self.gi.get_link(n)
                                self.list_add_line("tour",gi=gi,verbose=False)
                        else:
                            for n in range(int(pair[0]), int(pair[1]) - 1, -1):
                                gi = self.gi.get_link(n)
                                self.list_add_line("tour",gi=gi,verbose=False)

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
            self.marks[line] = self.gi
        else:
            print("Invalid mark, must be one letter")

    @needs_gi
    def do_info(self,line):
        """Display information about current page."""
        out = self.gi.get_page_title() + "\n\n"
        out += "URL      :   " + self.gi.url + "\n"
        out += "Path     :   " + self.gi.path + "\n"
        out += "Mime     :   " + self.gi.get_mime() + "\n"
        out += "Cache    :   " + self.gi.get_cache_path() + "\n"
        tmp = self.gi.get_temp_filename()
        if tmp != self.gi.get_cache_path():
            out += "Tempfile :   " + self.gi.get_temp_filename() + "\n"
        if self.gi.renderer :
            rend = str(self.gi.renderer.__class__)
            rend = rend.lstrip("<class '__main__.").rstrip("'>")
        else:
            rend = "None"
        out += "Renderer :   " + rend + "\n\n"
        lists = []
        for l in self.list_lists():
            if self.list_has_url(self.gi.url,l):
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
        output += " - python-cryptography : " + has(_HAS_CRYPTOGRAPHY)
        output += " - xdg-open            : " + has(_HAS_XDGOPEN)
        output += "\nWeb browsing:\n"
        output += " - python-requests     : " + has(_DO_HTTP)
        output += " - python-feedparser   : " + has(_DO_FEED)
        output += " - python-bs4          : " + has(_HAS_SOUP)
        output += " - python-readability  : " + has(_HAS_READABILITY)
        output += " - timg 1.3.2+         : " + has(_NEW_TIMG)
        if _NEW_CHAFA:
            output += " - chafa 1.10+         : " + has(_HAS_CHAFA)
        else:
            output += " - chafa               : " + has(_HAS_CHAFA)
            output += " - python-pil          : " + has(_HAS_PIL)
        output += "\nNice to have:\n"
        output += " - python-setproctitle : " + has(_HAS_SETPROCTITLE)
        output += " - xsel                : " + has(_HAS_XSEL)

        output += "\nFeatures :\n"
        if _NEW_CHAFA:
            output += " - Render images (chafa or timg)              : " + has(_RENDER_IMAGE)
        else:
            output += " - Render images (python-pil, chafa or timg)  : " + has(_RENDER_IMAGE)
        output += " - Render HTML (bs4, readability)             : " + has(_DO_HTML)
        output += " - Render Atom/RSS feeds (feedparser)         : " + has(_DO_FEED)
        output += " - Connect to http/https (requests)           : " + has(_DO_HTTP)
        output += " - Detect text encoding (python-chardet)      : " + has(_HAS_CHARDET)
        output += " - copy to/from clipboard (xsel)              : " + has(_HAS_XSEL)
        output += " - restore last position (less 572+)          : " + has(_LESS_RESTORE_POSITION)
        output += "\n"
        output += "Config directory    : " +  _CONFIG_DIR + "\n"
        output += "User Data directory : " +  _DATA_DIR + "\n"
        output += "Cache directoy      : " +  _CACHE_PATH

        print(output)

    ### Stuff that modifies the lookup table
    def do_ls(self, line):
        """List contents of current index.
Use 'ls -l' to see URLs."""
        self._show_lookup(url = "-l" in line)
        self.page_index = 0

    def do_search(self,line):
        """Search on Gemini using the engine configured (by default kennedy.gemi.dev)
        You can configure it using "set search URL".
        URL should contains one "%s" that will be replaced by the search term."""
        search = urllib.parse.quote(line)
        url = self.options["search"]%search
        gi = GeminiItem(url)
        self._go_to_gi(gi)

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
        gi = GeminiItem(url)
        self._go_to_gi(gi)

    def do_gus(self, line):
        """Submit a search query to the geminispace.info search engine."""
        gus = GeminiItem("gemini://geminispace.info/search")
        self._go_to_gi(gus.query(line))

    def do_history(self, *args):
        """Display history."""
        self.list_show("history")

    @needs_gi
    def do_find(self, searchterm):
        """Find in current page by displaying only relevant lines (grep)."""
        self.gi.display(grep=searchterm)

    def emptyline(self):
        """Page through index ten lines at a time."""
        i = self.page_index
        if not self.gi or i > len(self.gi.get_links()):
            return
        self._show_lookup(offset=i, end=i+10)
        self.page_index += 10

    ### Stuff that does something to most recently viewed item
    @needs_gi
    def do_cat(self, *args):
        """Run most recently visited item through "cat" command."""
        run("cat", input=open(self.gi.get_temp_filename(), "rb"), direct_output=True)

    @needs_gi
    def do_view(self, *args):
        """Run most recently visited item through "less" command, restoring \
previous position.
Use "view normal" to see the default article view on html page.
Use "view full" to see a complete html page instead of the article view.
Use "view feed" to see the the linked feed of the page (in any).
Use "view feeds" to see available feeds on this page.
(full, feed, feeds have no effect on non-html content)."""
        if self.gi and args and args[0] != "":
            if args[0] in ["full","debug"]:
                self._go_to_gi(self.gi,mode=args[0])
            elif args[0] in ["normal","readable"]:
                self._go_to_gi(self.gi,mode="readable")
            elif args[0] == "feed":
                subs = self.gi.get_subscribe_links()
                if len(subs) > 1:
                    self.do_go(subs[1][0])
                elif "rss" in subs[0][1] or "atom" in subs[0][1]:
                    print("%s is already a feed" %self.gi.url)
                else:
                    print("No other feed found on %s"%self.gi.url)
            elif args[0] == "feeds":
                subs = self.gi.get_subscribe_links()
                stri = "Available views :\n"
                counter = 0
                for s in subs:
                    counter += 1
                    stri += "[%s] %s [%s]\n"%(counter,s[0],s[1])
                stri += "Which view do you want to see ? >"
                ans = input(stri)
                if ans.isdigit() and 0 < int(ans) <= len(subs):
                    self.do_go(subs[int(ans)-1][0])
            else:
                print("Valid argument for view are : normal, full, feed, feeds")
        else:
            self._go_to_gi(self.gi)

    @needs_gi
    def do_open(self, *args):
        """Open current item with the configured handler or xdg-open.
Uses "open url" to open current URL in a browser.
see "handler" command to set your handler."""
        if args[0] == "url":
            run("xdg-open %s", parameter=self.gi.url, direct_output=True)
        else:
            cmd_str = self._get_handler_cmd(self.gi.get_mime())
            run(cmd_str, parameter=self.gi.get_body(as_file=True), direct_output=True)

    @needs_gi
    def do_shell(self, line):
        """'cat' most recently visited item through a shell pipeline.
'!' is an useful shortcut."""
        run(line, input=open(self.gi.get_temp_filename(), "rb"), direct_output=True)

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
            if not self.gi.is_cache_valid():
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
            last_gi = self.gi
            try:
                gi = self.gi.get_link(index)
                self._go_to_gi(gi, update_hist = False, handle = False)
            except IndexError:
                print ("Index too high!")
                self.gi = last_gi
                return
        else:
            gi = self.gi

        # Derive filename from current GI's path, if one hasn't been set
        if not filename:
            filename = gi.get_filename()
        # Check for filename collisions and actually do the save if safe
        if os.path.exists(filename):
            print("File %s already exists!" % filename)
        else:
            # Don't use _get_active_tmpfile() here, because we want to save the
            # "source code" of menus, not the rendered view - this way Offpunk
            # can navigate to it later.
            path = gi.get_body(as_file=True)
            if os.path.isdir(path):
                print("Can’t save %s because it’s a folder, not a file"%path)
            else:
                print("Saved to %s" % filename)
                shutil.copyfile(path, filename)

        # Restore gi if necessary
        if index != None:
            self._go_to_gi(last_gi, handle=False)

    @needs_gi
    def do_url(self, *args):
        """Print URL of most recently visited item."""
        print(self.gi.url)

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
            old_file_gmi = os.path.join(_CONFIG_DIR,list + ".gmi")
            old_file_nogmi = os.path.join(_CONFIG_DIR,list)
            target = os.path.join(_DATA_DIR,"lists")
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
        subs = self.gi.get_subscribe_links()
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
            sublink = self.gi.absolutise_url(sublink)
            gi = GeminiItem(sublink,name=title)
            list_path = self.get_list("subscribed")
            added = self.list_add_line("subscribed",gi=gi,verbose=False)
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
                deleted = self.list_rm_url(self.gi.url_mode(),li)
                if deleted:
                    print("Removed from %s"%li)
        self.list_add_top("archives",limit=self.options["archives_size"])
        print("Archiving: %s"%self.gi.get_page_title())
        print("\x1b[2;34mCurrent maximum size of archives : %s\x1b[0m" %self.options["archives_size"])

    def list_add_line(self,list,gi=None,verbose=True):
        list_path = self.list_path(list)
        if not list_path and self.list_is_system(list):
            self.list_create(list,quite=True)
            list_path = self.list_path(list)
        if not list_path:
            print("List %s does not exist. Create it with ""list create %s"""%(list,list))
            return False
        else:
            if not gi:
                gi = self.gi
            # first we check if url already exists in the file
            with open(list_path,"r") as l_file:
                lines = l_file.readlines()
                l_file.close()
                for l in lines:
                    sp = l.split()
                    if gi.url_mode() in sp:
                        if verbose:
                            print("%s already in %s."%(gi.url,list))
                        return False
            with open(list_path,"a") as l_file:
                l_file.write(gi.to_map_line())
                l_file.close()
            if verbose:
                print("%s added to %s" %(gi.url,list))
            return True

    def list_add_top(self,list,limit=0,truncate_lines=0):
        if not self.gi:
            return
        stri = self.gi.to_map_line().strip("\n")
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

    # deletion and has_url are so similar, I made them the same method
    def list_has_url(self,url,list,deletion=False):
        list_path = self.list_path(list)
        if list_path:
            to_return = False
            with open(list_path,"r") as lf:
                lines = lf.readlines()
                lf.close()
            to_write = []
            # let’s remove the mode
            url = url.split("##offpunk_mode=")[0]
            for l in lines:
                # we separate components of the line
                # to ensure we identify a complete URL, not a part of it
                splitted = l.split()
                if url not in splitted and len(splitted) > 1:
                    current = splitted[1].split("##offpunk_mode=")[0]
                    #sometimes, we must remove the ending "/"
                    if url == current:
                        to_return = True
                    elif url.endswith("/") and url[:-1] == current:
                        to_return = True
                    else:
                        to_write.append(l)
                else:
                    to_return = True
            if deletion :
                with open(list_path,"w") as lf:
                    for l in to_write:
                        lf.write(l)
                    lf.close()
            return to_return
        else:
            return False

    def list_get_links(self,list):
        list_path = self.list_path(list)
        if list_path:
            gi = GeminiItem("list:///%s"%list)
            return gi.get_links()
        else:
            return []

    def list_go_to_line(self,line,list):
        list_path = self.list_path(list)
        if not list_path:
            print("List %s does not exist. Create it with ""list create %s"""%(list,list))
        elif not line.isnumeric():
            print("go_to_line requires a number as parameter")
        else:
            gi = GeminiItem("list:///%s"%list)
            gi = gi.get_link(int(line))
            display = not self.sync_only
            if gi:
                self._go_to_gi(gi,handle=display)
                return gi.url_mode()

    def list_show(self,list):
        list_path = self.list_path(list)
        if not list_path:
            print("List %s does not exist. Create it with ""list create %s"""%(list,list))
        else:
            gi = GeminiItem("list:///%s"%list)
            display = not self.sync_only
            self._go_to_gi(gi,handle=display)

    #return the path of the list file if list exists.
    #return None if the list doesn’t exist.
    def list_path(self,list):
        listdir = os.path.join(_DATA_DIR,"lists")
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
            listdir = os.path.join(_DATA_DIR,"lists")
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
                        isremoved = self.list_rm_url(self.gi.url_mode(),l)
                        if isremoved:
                            print("Removed from %s"%l)
                self.list_add_line(args[0])

    def list_lists(self):
        listdir = os.path.join(_DATA_DIR,"lists")
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
        listdir = os.path.join(_DATA_DIR,"lists")
        os.makedirs(listdir,exist_ok=True)
        if not arg:
            lists = self.list_lists()
            if len(lists) > 0:
                lgi = GeminiItem("list:///")
                self._go_to_gi(lgi)
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

    ### Flight recorder
    def do_blackbox(self, *args):
        """Display contents of flight recorder, showing statistics for the
current gemini browsing session."""
        lines = []
        # Compute flight time
        now = time.time()
        delta = now - self.log["start_time"]
        hours, remainder = divmod(delta, 3600)
        minutes, seconds = divmod(remainder, 60)
        # Count hosts
        ipv4_hosts = len([host for host in self.visited_hosts if host[0] == socket.AF_INET])
        ipv6_hosts = len([host for host in self.visited_hosts if host[0] == socket.AF_INET6])
        # Assemble lines
        lines.append(("Patrol duration", "%02d:%02d:%02d" % (hours, minutes, seconds)))
        lines.append(("Requests sent:", self.log["requests"]))
        lines.append(("   IPv4 requests:", self.log["ipv4_requests"]))
        lines.append(("   IPv6 requests:", self.log["ipv6_requests"]))
        lines.append(("Bytes received:", self.log["bytes_recvd"]))
        lines.append(("   IPv4 bytes:", self.log["ipv4_bytes_recvd"]))
        lines.append(("   IPv6 bytes:", self.log["ipv6_bytes_recvd"]))
        lines.append(("Unique hosts visited:", len(self.visited_hosts)))
        lines.append(("   IPv4 hosts:", ipv4_hosts))
        lines.append(("   IPv6 hosts:", ipv6_hosts))
        lines.append(("DNS failures:", self.log["dns_failures"]))
        lines.append(("Timeouts:", self.log["timeouts"]))
        lines.append(("Refused connections:", self.log["refused_connections"]))
        lines.append(("Reset connections:", self.log["reset_connections"]))
        lines.append(("Cache hits:", self.log["cache_hits"]))
        # Print
        for key, value in lines:
            print(key.ljust(24) + str(value).rjust(8))


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

    def call_sync(self,refresh_time=0,depth=1):
        # fetch_gitem is the core of the sync algorithm.
        # It takes as input :
        # - a GeminiItem to be fetched
        # - depth : the degree of recursion to build the cache (0 means no recursion)
        # - validity : the age, in seconds, existing caches need to have before
        #               being refreshed (0 = never refreshed if it already exists)
        # - savetotour : if True, newly cached items are added to tour
        def add_to_tour(gitem):
            if gitem and gitem.is_cache_valid():
                toprint = "  -> adding to tour: %s" %gitem.url
                width = term_width() - 1
                toprint = toprint[:width]
                toprint += " "*(width-len(toprint))
                print(toprint)
                self.list_add_line("tour",gi=gitem,verbose=False)
                return True
            else:
                return False
        def fetch_gitem(gitem,depth=0,validity=0,savetotour=False,count=[0,0],strin=""):
            #savetotour = True will save to tour newly cached content
            # else, do not save to tour
            #regardless of valitidy
            if not gitem: return
            if not gitem.is_cache_valid(validity=validity):
                if strin != "":
                    endline = '\r'
                else:
                    endline = None
                #Did we already had a cache (even an old one) ?
                isnew = not gitem.is_cache_valid()
                toprint = "%s [%s/%s] Fetch "%(strin,count[0],count[1]) + gitem.url
                width = term_width() - 1
                toprint = toprint[:width]
                toprint += " "*(width-len(toprint))
                print(toprint,end=endline)
                #If not saving to tour, then we should limit download size
                limit = not savetotour
                self._go_to_gi(gitem,update_hist=False,limit_size=limit)
                if savetotour and isnew and gitem.is_cache_valid():
                    #we add to the next tour only if we managed to cache
                    #the ressource
                    add_to_tour(gitem)
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
                links = gitem.get_links(mode="links_only")
                subcount = [0,len(links)]
                d = depth - 1
                for k in links:
                    #recursive call (validity is always 0 in recursion)
                    substri = strin + " -->"
                    subcount[0] += 1
                    fetch_gitem(k,depth=d,validity=0,savetotour=savetotour,\
                                        count=subcount,strin=substri)
        def fetch_list(list,validity=0,depth=1,tourandremove=False,tourchildren=False):
            links = self.list_get_links(list)
            end = len(links)
            counter = 0
            print(" * * * %s to fetch in %s * * *" %(end,list))
            for l in links:
                counter += 1
                # If cache for a link is newer than the list
                fetch_gitem(l,depth=depth,validity=validity,savetotour=tourchildren,count=[counter,end])
                if tourandremove:
                    if add_to_tour(l):
                        self.list_rm_url(l.url_mode(),list)

        self.sync_only = True
        lists = self.list_lists()
        # We will fetch all the lists except "archives" and "history"
        # We keep tour for the last round
        subscriptions = []
        normal_lists = []
        fridge = []
        for l in lists:
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
        def unlink(filename):
            if filename and os.path.exists(filename):
                os.unlink(filename)
        # Close TOFU DB
        self.db_conn.commit()
        self.db_conn.close()
        # Clean up after ourself

        for cert in self.transient_certs_created:
            for ext in (".crt", ".key"):
                certfile = os.path.join(_CONFIG_DIR, "transient_certs", cert+ext)
                if os.path.exists(certfile):
                    os.remove(certfile)
        print("You can close your screen!")
        sys.exit()

    do_exit = do_quit



# Main function
def main():

    # Parse args
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bookmarks', action='store_true',
                        help='start with your list of bookmarks')
    parser.add_argument('--tls-cert', metavar='FILE', help='TLS client certificate file')
    parser.add_argument('--tls-key', metavar='FILE', help='TLS client certificate private key file')
    parser.add_argument('--sync', action='store_true',
                        help='run non-interactively to build cache by exploring bookmarks')
    parser.add_argument('--assume-yes', action='store_true',
                        help='assume-yes when asked questions about certificates/redirections during sync (lower security)')
    parser.add_argument('--disable-http',action='store_true',
                        help='do not try to get http(s) links (but already cached will be displayed)')
    parser.add_argument('--fetch-later', action='store_true',
                        help='run non-interactively with an URL as argument to fetch it later')
    parser.add_argument('--depth',
                        help='depth of the cache to build. Default is 1. More is crazy. Use at your own risks!')
    parser.add_argument('--cache-validity',
                        help='duration for which a cache is valid before sync (seconds)')
    parser.add_argument('--version', action='store_true',
                        help='display version information and quit')
    parser.add_argument('--features', action='store_true',
                        help='display available features and dependancies then quit')
    parser.add_argument('url', metavar='URL', nargs='*',
                        help='start with this URL')
    args = parser.parse_args()

    # Handle --version
    if args.version:
        print("Offpunk " + __version__)
        sys.exit()
    elif args.features:
        GeminiClient.do_version(None,None)
        sys.exit()
    else:
        for f in [_CONFIG_DIR, _DATA_DIR]:
            if not os.path.exists(f):
                print("Creating config directory {}".format(f))
                os.makedirs(f)

    # Instantiate client
    gc = GeminiClient(synconly=args.sync)
    torun_queue = []

    # Interactive if offpunk started normally
    # False if started with --sync
    # Queue is a list of command (potentially empty)
    def read_config(queue,interactive=True):
        rcfile = os.path.join(_CONFIG_DIR, "offpunkrc")
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
    if args.tls_cert:
        # If tls_key is None, python will attempt to load the key from tls_cert.
        gc._activate_client_cert(args.tls_cert, args.tls_key)
    if args.bookmarks:
        torun_queue.append("bookmarks")
    elif args.url:
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
                gi = GeminiItem(u)
                if gi and gi.is_cache_valid():
                    gc.list_add_line("tour",gi)
                else:
                    gc.list_add_line("to_fetch",gi)
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
        if args.depth:
            depth = int(args.depth)
        else:
            depth = 1
        read_config(torun_queue, interactive=False)
        for line in torun_queue:
            gc.onecmd(line)
        gc.call_sync(refresh_time=refresh_time,depth=depth)
        gc.onecmd("blackbox")
    else:
        # We are in the normal mode. First process config file
        torun_queue = read_config(torun_queue,interactive=True)
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
