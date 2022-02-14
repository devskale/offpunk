#!/usr/bin/env python3
# Offpunk Offline Gemini client
# Derived from AV-98 by Solderpunk,
# (C) 2021, 2022 Ploum <offpunk@ploum.eu>
# (C) 2019, 2020 Solderpunk <solderpunk@sdf.org>
# With contributions from:
#  - danceka <hannu.hartikainen@gmail.com>
#  - <jprjr@tilde.club>
#  - <vee@vnsf.xyz>
#  - Klaus Alexander Seistrup <klaus@seistrup.dk>
#  - govynnus <govynnus@sdf.org>
#  - Björn Wärmedal <bjorn.warmedal@gmail.com>
#  - <jake@rmgr.dev>

_VERSION = "0.3"

import argparse
import cmd
import cgi
import codecs
import collections
import datetime
import fnmatch
import getpass
import glob
import hashlib
import io
import mimetypes
import os
import os.path
import filecmp
import random
import shlex
import shutil
import socket
import sqlite3
import ssl
from ssl import CertificateError
import subprocess
import sys
import tempfile
import time
import urllib.parse
import uuid
import webbrowser

try:
    import editor
    _HAS_EDITOR = True
except ModuleNotFoundError:
    _HAS_EDITOR = False

try:
    import ansiwrap as textwrap
    _HAS_ANSIWRAP = True
except ModuleNotFoundError:
    print("Try installing python-ansiwrap for better rendering")
    import textwrap
    _HAS_ANSIWRAP = False

_HAS_CHAFA = shutil.which('chafa')
_HAS_XSEL = shutil.which('xsel')
try:
    from PIL import Image
    _HAS_PIL = True
    if _HAS_ANSIWRAP and _HAS_CHAFA:
        _RENDER_IMAGE = True
    else:
        print("chafa and ansiwrap are required to render images in terminal")
        _RENDER_IMAGE = False
except ModuleNotFoundError:
    print("python-pil, chafa and ansiwrap are required to render images")
    _RENDER_IMAGE = False
    _HAS_PIL = False


try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    _HAS_CRYPTOGRAPHY = True
    _BACKEND = default_backend()
except ModuleNotFoundError:
    _HAS_CRYPTOGRAPHY = False

try:
    import magic
    _HAS_MAGIC = True
except ModuleNotFoundError:
    print("Python-magic is recommended for better detection of mimetypes")
    _HAS_MAGIC = False

try:
    import requests
    _DO_HTTP = True
except ModuleNotFoundError:
    _DO_HTTP = False

try:
    from readability import Document
    _HAS_READABILITY = True
except ModuleNotFoundError:
    _HAS_READABILITY = False

try:
    from bs4 import BeautifulSoup
    _HAS_SOUP = True
except ModuleNotFoundError:
    _HAS_SOUP = False

_DO_HTML = _HAS_SOUP and _HAS_READABILITY

try:
    import feedparser
    _DO_FEED = True
except ModuleNotFoundError:
    _DO_FEED = False

## Config directories
# There are two conflicting xdg modules, we try to work with both
try:
    from xdg import BaseDirectory
    _HAS_XDG = True
    _CACHE_PATH = BaseDirectory.save_cache_path("offpunk/")
    _CONFIG_DIR = BaseDirectory.save_config_path("offpunk/")
    _DATA_DIR = BaseDirectory.save_data_path("offpunk/")
except ModuleNotFoundError:
    _HAS_XDG = False
    _CACHE_PATH = os.path.expanduser("~/.cache/offpunk/")
    _CONFIG_DIR = None
    ## Look for pre-existing config directory, if any
    for confdir in ("~/.offpunk/", "~/.config/offpunk/"):
        confdir = os.path.expanduser(confdir)
        if os.path.exists(confdir):
            _CONFIG_DIR = confdir
            break
    ## Otherwise, make one in .config if it exists
    if not _CONFIG_DIR and os.path.exists("~/.config/"):
        _CONFIG_DIR = os.path.expanduser("~/.config/offpunk/")
    elif not _CONFIG_DIR:
        _CONFIG_DIR = os.path.expanduser("~/.offpunk/")
    _DATA_DIR = _CONFIG_DIR
for f in [_CONFIG_DIR, _CACHE_PATH, _DATA_DIR]:
    if not os.path.exists(f):
        print("Creating config directory {}".format(f))
        os.makedirs(f)

_MAX_REDIRECTS = 5
_MAX_CACHE_SIZE = 10
_MAX_CACHE_AGE_SECS = 180
#_DEFAULT_LESS = "less -EXFRfM -PMurl\ lines\ \%lt-\%lb/\%L\ \%Pb\%$ %s"
# -E : quit when reaching end of file (to behave like "cat")
# -F : quit if content fits the screen (behave like "cat")
# -X : does not clear the screen
# -R : interpret ANSI colors correctly
# -f : suppress warning for some contents
# -M : long prompt (to have info about where you are in the file)
# -w : hilite the new first line after a page skip (space)
# -i : ignore case in search
_DEFAULT_CAT = "less -EXFRfMwi %s"
_DEFAULT_LESS = "less -XRfMwi %s"
#_DEFAULT_LESS = "batcat -p %s"

# Command abbreviations
_ABBREVS = {
    "a":    "add",
    "b":    "back",
    "bb":   "blackbox",
    "bm":   "bookmarks",
    "book": "bookmarks",
    "cp":   "copy",
    "f":    "fold",
    "fo":   "forward",
    "g":    "go",
    "h":    "history",
    "hist": "history",
    "l":    "less",
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
    "/":    "search",
    "t":    "tour",
    "u":    "up",
}

_MIME_HANDLERS = {
    "application/pdf":      "zathura %s",
    "audio/mpeg":           "mpg123 %s",
    "audio/ogg":            "ogg123 %s",
    "image/*":              "feh -. %s",
    #"text/html":            "lynx -dump -force_html %s",
}

# monkey-patch Gemini support in urllib.parse
# see https://github.com/python/cpython/blob/master/Lib/urllib/parse.py
urllib.parse.uses_relative.append("gemini")
urllib.parse.uses_netloc.append("gemini")

global TERM_WIDTH
TERM_WIDTH = 80

def fix_ipv6_url(url):
    if not url:
        return
    if not url.count(":") > 2: # Best way to detect them?
        return url
    if url.startswith("mailto"):
        return url
    # If there's a pair of []s in there, it's probably fine as is.
    if "[" in url and "]" in url:
        return url
    # Easiest case is a raw address, no schema, no path.
    # Just wrap it in square brackets and whack a slash on the end
    if "/" not in url:
        return "[" + url + "]/"
    # Now the trickier cases...
    if "://" in url:
        schema, schemaless = url.split("://",maxsplit=1)
    else:
        schema, schemaless = None, url
    if "/" in schemaless:
        netloc, rest = schemaless.split("/",1)
        schemaless = "[" + netloc + "]" + "/" + rest
    if schema:
        return schema + "://" + schemaless
    return schemaless

# This list is also used as a list of supported protocols
standard_ports = {
        "gemini": 1965,
        "gopher": 70,
        "http"  : 80,
        "https" : 443,
}

# First, we define the different content->text renderers, outside of the rest
# (They could later be factorized in other files or replaced)
class AbstractRenderer():
    def __init__(self,content,url):
        self.url = url
        self.body = content
        self.rendered_text = None
        self.links = None
        self.title = None
        self.validity = True
    
    def is_valid(self):
        return self.validity
    def get_links(self):
        if self.links == None :
            rendered_text, self.links = self.render(self.body,mode="links_only")
        return self.links
    def get_title(self):
        return "Abstract title"
    
    #This function will give gemtext to the gemtext renderer
    def prepare(self,body,mode=None):
        return body
    
    def get_body(self,readable=True,width=None):
        if not width:
            width = TERM_WIDTH
        if self.rendered_text == None or not readable:
            if readable : 
                mode = "readable" 
            else :
                mode = "full"
            prepared_body = self.prepare(self.body,mode=mode)
            self.rendered_text, self.links = self.render(prepared_body,width=width,mode=mode)
        return self.rendered_text
    # An instance of AbstractRenderer should have a self.render(body,width,mode) method.
    # 3 modes are used : readable (by default), full and links_only (the fastest, when
    # rendered content is not used, only the links are needed)
    # The prepare() function is called before the rendering. It is useful if
    # your renderer output in a format suitable for another existing renderer (such as gemtext)

# Gemtext Rendering Engine
class GemtextRenderer(AbstractRenderer):
    def get_title(self):
        if self.title:
            return self.title
        else:
            lines = self.body.splitlines()
            for line in lines:
                if line.startswith("#"):
                    self.title = line.strip("#").strip()
                    return self.title
            if len(lines) > 0:
                # If not title found, we take the first 50 char 
                # of the first line
                title_line = lines[0].strip()
                if len(title_line) > 50:
                    title_line = title_line[:49] + "…"
                self.title = title_line
                return self.title
            else:
                self.title = "Empty Page"
                return self.title
    
    #render_gemtext
    def render(self,gemtext, width=None,mode=None):
        if not width:
            width = TERM_WIDTH
        links = []
        preformatted = False
        rendered_text = ""
        #This local method takes a line and apply the ansi code given as "color"
        #The whole line is then wrapped and ansi code are ended.
        def wrap_line(line,color=None,i_indent="",s_indent=""):
            wrapped = textwrap.wrap(line,width,initial_indent=i_indent,\
                                    subsequent_indent=s_indent)
            final = ""
            for l in wrapped:
                if color:
                    l = color + l + "\x1b[0m"
                if l.strip() != "":
                    final += l + "\n"
            return final
        def format_link(url,index,name=None):
            if "://" in url:
                protocol,adress = url.split("://",maxsplit=1)
                protocol = " %s" %protocol
            else:
                adress = url
                protocol = ""
            if "gemini" in protocol:
                protocol = ""
            if not name:
                name = adress
            line = "[%d%s] %s" % (index, protocol, name)
            return line
        for line in gemtext.splitlines():
            if line.startswith("```"):
                preformatted = not preformatted
            elif preformatted:
                rendered_text += line + "\n"
            elif line.startswith("=>"):
                strippedline = line[2:].strip()
                if strippedline:
                    links.append(strippedline)        
                    splitted = strippedline.split(maxsplit=1)
                    url = splitted[0]
                    name = None
                    if len(splitted) > 1:
                        name = splitted[1]
                    link = format_link(url,len(links),name=name)
                    startpos = link.find("] ") + 2
                    wrapped = wrap_line(link,s_indent=startpos*" ")
                    rendered_text += wrapped
            elif line.startswith("* "):
                line = line[1:].lstrip("\t ")
                rendered_text += textwrap.fill(line, width, initial_indent = "• ", 
                                                subsequent_indent="  ") + "\n"
            elif line.startswith(">"):
                line = line[1:].lstrip("\t ")
                rendered_text += textwrap.fill(line,width, initial_indent = "> ", 
                                                subsequent_indent="> ") + "\n"
            elif line.startswith("###"):
                line = line[3:].lstrip("\t ")
                rendered_text += wrap_line(line, color="\x1b[34m\x1b[2m")
            elif line.startswith("##"):
                line = line[2:].lstrip("\t ")
                rendered_text += wrap_line(line, color="\x1b[34m")
            elif line.startswith("#"):
                line = line[1:].lstrip("\t ")
                if not self.title:
                    self.title = line
                rendered_text += wrap_line(line,color="\x1b[1;34m\x1b[4m")
            else:
                rendered_text += wrap_line(line).rstrip() + "\n"
        return rendered_text, links

class GopherRenderer(AbstractRenderer):
    def get_title(self):
        return "Gopher - No Title"

    #menu_or_text
    def render(self,body,width=None,mode=None):
        if not width:
            width = TERM_WIDTH
        try:
            render,links = self._render_goph(width=width,mode=mode)
        except Exception as err:
            print("Error ",err)
            lines = body.split("\n")
            render = ""
            for line in lines:
                render += textwrap.fill(line,width) + "\n"
            links = []
        return render,links

    def _render_goph(self,width=None,mode=None):
        if not width:
            width = TERM_WIDTH
        # This is copied straight from Agena (and thus from VF1)
        rendered_text = ""
        links = []
        for line in self.body.split("\n"):
            #if line.strip() == ".":
            #    continue
            if line.startswith("i"):
                towrap = line[1:].split("\t")[0] + "\r\n"
                rendered_text += textwrap.fill(towrap,width) + "\n"
            elif not line.strip() in [".",""]:
                parts = line.split("\t")
                parts[-1] = parts[-1].strip()
                if parts[-1] == "+":
                    parts = parts[:-1]
                if len(parts) == 4:
                    name,path,host,port = parts
                    itemtype = name[0]
                    name = name[1:]
                    if port == "70":
                        port = ""
                    else:
                        port = ":%s"%port
                    if itemtype == "h" and path.startswith("URL:"):
                        url = path[4:]
                    else:
                        url = "gopher://%s%s/%s%s" %(host,port,itemtype,path)
                    linkline = url + " " + name
                    links.append(linkline)
                    towrap = "[%s] "%len(links)+ name + "\n"
                    rendered_text += textwrap.fill(towrap,width) + "\n"
                else:
                    towrap = line +"\n"
                    rendered_text += textwrap.fill(towrap,width) + "\n"
        return rendered_text,links


class FolderRenderer(GemtextRenderer):
    def prepare(self,body,mode=None):
        def write_list(l):
            path = os.path.join(listdir,l+".gmi")
            gi = GeminiItem("file://" + path)
            size = len(gi.get_links())
            line = "=> %s %s (%s items)\n" %(str(path),l,size)
            return line
        listdir = os.path.join(_DATA_DIR,"lists")
        if self.url != listdir:
            return "This is folder %s" %self.url
        else:
            self.title = "My lists"
            lists = []
            if os.path.exists(listdir):
                listfiles = os.listdir(listdir)
                if len(listfiles) > 0:
                    for l in listfiles:
                        #removing the .gmi at the end of the name
                        lists.append(l[:-4])
            if len(lists) > 0:
                body = ""
                my_lists = []
                system_lists = []
                subscriptions = []
                lists.sort()
                for l in lists:
                    if l in ["history","to_fetch","archives","tour"]:
                        system_lists.append(l)
                    elif l in ["subscribed"]:
                        subscriptions.append(l)
                    else:
                        my_lists.append(l)
                if len(my_lists) > 0:
                    body+= "\n## Bookmarks Lists (updated during sync)\n"
                    for l in my_lists:
                        body += write_list(l)
                if len(subscriptions) > 0:
                    body +="\n## Subscriptions (new links in those are added to tour)\n"
                    for l in subscriptions:
                        body += write_list(l)
                if len(system_lists) > 0:
                    body +="\n## System Lists\n"
                    for l in system_lists:
                        body += write_list(l)
                return body

class FeedRenderer(GemtextRenderer):
    def is_valid(self):
        if _DO_FEED:
            parsed = feedparser.parse(self.body)
        else:
            return False
        if parsed.bozo:
            return False
        else:
            return True

    def get_title(self):
        if not self.title:
            self.render(self.body)
        return self.title

    def prepare(self,content,mode="readable",width=None):
        if not width:
            width = TERM_WIDTH
        self.links = []
        self.title = "RSS/Atom feed"
        page = ""
        if _DO_FEED:
            parsed = feedparser.parse(content)
        else:
            page += "Please install python-feedparser to handle RSS/Atom feeds\n"
            self.validity = False
            return page
        if parsed.bozo:
            page += "Invalid RSS feed\n\n"
            page += str(parsed.bozo_exception)
            self.validity = False
        else:
            if "title" in parsed.feed:
                t = parsed.feed.title
            else:
                t = "Unknown"
            self.title = "%s (XML feed)" %t
            title = "# %s"%self.title
            page += title + "\n"
            if "updated" in parsed.feed:
                page += "Last updated on %s\n\n" %parsed.feed.updated
            if "subtitle" in parsed.feed:
                page += parsed.feed.subtitle + "\n"
            if "link" in parsed.feed:
                page += "=> %s\n" %parsed.feed.link
            page += "\n## Entries\n"
            if len(parsed.entries) < 1:
                self.validity = False
            for i in parsed.entries:
                line = "=> %s " %i.link
                if "published" in i:
                    pub_date = time.strftime("%Y-%m-%d",i.published_parsed)
                    line += pub_date + " : "
                line += "%s" %(i.title)
                if "author" in i:
                    line += " (by %s)"%i.author
                page += line + "\n"
                if mode == "full":
                    if "summary" in i:
                        rendered, links = HtmlRenderer.render(self,i.summary,\
                                            width=width,mode="full",add_title=False)
                        page += rendered
                        page += "\n"
        return page

class ImageRenderer(AbstractRenderer):
    def is_valid(self):
        if _RENDER_IMAGE:
            return True
        else:
            return False
    def get_links(self):
        return []
    def get_title(self):
        return "Picture file"
    def render(self,img,width=None,mode=None):
        if mode == "links_only":
            return "", []
        if not width:
            width = TERM_WIDTH
        try:
            img_obj = Image.open(img)
            if hasattr(img_obj,"n_frames") and img_obj.n_frames > 1:
                # we remove all frames but the first one
                img_obj.save(img,save_all=False)
            cmd = "chafa --bg white -s %s -w 1 \"%s\"" %(width,img)
            return_code = subprocess.run(cmd,shell=True, capture_output=True)
            ansi_img = return_code.stdout.decode()
        except Exception as err:
            ansi_img = "***image failed : %s***\n" %err
        return ansi_img, []

class HtmlRenderer(AbstractRenderer):
    def get_title(self):
        if self.title:
            return self.title
        else:
            readable = Document(self.body)
            self.title = readable.short_title()
            return self.title

    # Our own HTML engine (crazy, isn’t it?)
    # Return [rendered_body, list_of_links]
    # mode is either links_only, readable or full
    def render(self,body,mode="readable",width=None,add_title=True):
        if not width:
            width = TERM_WIDTH
        if not _DO_HTML:
            print("HTML document detected. Please install python-bs4 and python-readability.")
            return
        # This method recursively parse the HTML
        r_body = ""
        links = []
        # You know how bad html is when you realize that space sometimes meaningful, somtimes not.
        # CR are not meaniningful. Except that, somethimes, they should be interpreted as spaces.
        # HTML is real crap. At least the one people are generating.
        def sanitize_string(string):
            endspace = string.endswith(" ")
            startspace = string.startswith(" ")
            toreturn = string.replace("\n", " ").replace("\t"," ").strip()
            while "  " in toreturn:
                toreturn = toreturn.replace("  "," ")
            toreturn = toreturn.strip("\n").strip("\t")
            toreturn = toreturn.replace("&nbsp"," ")
            if endspace and not toreturn.endswith(" "):
                toreturn += " "
            if startspace and not toreturn.startswith(" "):
                toreturn = " " + toreturn
            return toreturn
        def recursive_render(element,indent=""):
            rendered_body = ""
            if element.name == "blockquote":
                for child in element.children:
                    rendered_body += "\x1b[3m"
                    rendered_body +=  recursive_render(child,indent="\t").rstrip("\t")
                    rendered_body += "\x1b[23m"
            elif element.name in ["div","p"]:
                rendered_body += "\n"
                for child in element.children:
                    rendered_body += recursive_render(child,indent=indent)
                rendered_body += "\n\n"
            elif element.name in ["h1","h2","h3","h4","h5","h6"]:
                line = sanitize_string(element.get_text())
                if element.name in ["h1","h2"]:
                    rendered_body += "\n"+"\x1b[1;34m\x1b[4m" + line + "\x1b[0m"+"\n"
                elif element.name in ["h3","h4"]:
                    rendered_body += "\n" + "\x1b[34m" + line + "\x1b[0m" + "\n"
                else:
                    rendered_body += "\n" + "\x1b[34m\x1b[2m" + line + "\x1b[0m" + "\n"
            elif element.name == "pre":
                rendered_body += "\n"
                for child in element.children:
                   rendered_body += recursive_render(child,indent=indent)
                rendered_body += "\n\n"
            elif element.name in ["li","tr"]:
                line = ""
                for child in element.children:
                    line += recursive_render(child,indent=indent).strip("\n")
                rendered_body += " * " + line.strip() + "\n"
            elif element.name in ["td"]:
                line = "| "
                for child in element.children:
                    line += recursive_render(child)
                line += " |"
                rendered_body += line
            # italics
            elif element.name in ["code","em","i"]:
                rendered_body += "\x1b[3m"
                for child in element.children:
                    rendered_body += recursive_render(child,indent=indent)
                rendered_body += "\x1b[23m"
            #bold
            elif element.name in ["code","b","strong"]:
                rendered_body += "\x1b[1m"
                for child in element.children:
                    rendered_body += recursive_render(child,indent=indent)
                rendered_body += "\x1b[22m"
            elif element.name == "a":
                text = sanitize_string(element.get_text())
                # support for images nested in links
                for child in element.children:
                    if child.name == "img":
                        img = recursive_render(child)
                        rendered_body += img
                link = element.get('href')
                if link:
                    links.append(link+" "+text)
                    link_id = " [%s]"%(len(links))
                    rendered_body += "\x1b[2;34m" + text + link_id + "\x1b[0m"
                else:
                    #No real link found
                    rendered_body = text
            elif element.name == "img":
                src = element.get("src")
                text = ""
                ansi_img = ""
                if _RENDER_IMAGE and mode != "links_only" and src:
                    abs_url = urllib.parse.urljoin(self.url, src)
                    try:
                        g = GeminiItem(abs_url)
                        if g.is_cache_valid():
                            img = g.get_cache_path()
                            renderer = ImageRenderer(img,abs_url)
                            # Image are 40px wide except if terminal is smaller
                            if width > 40:
                                size = 40
                            else:
                                size = width
                            ansi_img = "\n" + renderer.get_body(width=size)
                    except Exception as err:
                        #we sometimes encounter really bad formatted files or URL
                        ansi_img += "[BAD IMG] %s"%src
                alt = element.get("alt")
                if alt:
                    alt = sanitize_string(alt)
                    text += "[IMG] %s"%alt
                else:
                    text += "[IMG]"
                if src:
                    links.append(src+" "+text)
                    link_id = " [%s]"%(len(links))
                    rendered_body = ansi_img + "\x1b[2;33m" + text + link_id + "\x1b[0m\n\n"
            elif element.name == "br":
                rendered_body = "\n"
            elif element.string:
                rendered_body = sanitize_string(element.string)
            else:
                for child in element.children:
                    rendered_body += recursive_render(child,indent=indent)
            return indent + rendered_body
        # the real render_html hearth
        if mode == "full":
            summary = body
        else:
            readable = Document(body)
            summary = readable.summary()
        soup = BeautifulSoup(summary, 'html.parser')
        rendered_body = ""
        if soup :
            if soup.body :
                contents = soup.body.contents
            else:
                contents = soup.contents
            for el in contents:
                rendered_body += recursive_render(el)
            paragraphs = rendered_body.split("\n\n")
            for par in paragraphs:
                lines = par.splitlines()
                for line in lines:
                    if line.startswith("\t"):
                        i_indent = "   "
                        s_indent = i_indent
                        line = line.strip("\t")
                    elif line.startswith(" * "):
                        i_indent = ""  # we keep the initial bullet)
                        s_indent = "   "
                    else:
                        i_indent = ""
                        s_indent = i_indent
                    if line.strip() != "":
                        try:
                            wrapped = textwrap.fill(line,width,initial_indent=i_indent,
                                                subsequent_indent=s_indent)
                        except Exception as err:
                            wrapped = line
                        wrapped += "\n"
                    else:
                        wrapped = ""
                    r_body += wrapped
                r_body += "\n"
        #check if we need to add the title or if already in content
        lines = r_body.splitlines()
        first_line = ""
        while first_line == "" and len(lines) > 0:
            first_line = lines.pop(0)
        if add_title and self.get_title()[:(width-1)] not in first_line:
            title = "\x1b[1;34m\x1b[4m" + self.get_title() + "\x1b[0m""\n" 
            title = textwrap.fill(title,width)
            r_body = title + "\n" + r_body
        #We try to avoid huge empty gaps in the page
        r_body = r_body.replace("\n\n\n\n","\n\n").replace("\n\n\n","\n\n")
        return r_body,links

# Mapping mimetypes with renderers
# (any content with a mimetype text/* not listed here will be rendered with as GemText)
_FORMAT_RENDERERS = {
    "text/gemini":  GemtextRenderer,
    "text/html" :   HtmlRenderer,
    "text/xml" : FeedRenderer,
    "application/xml" : FeedRenderer,
    "application/rss+xml" : FeedRenderer,
    "application/atom+xml" : FeedRenderer,
    "text/gopher": GopherRenderer,
    "image/*": ImageRenderer
}
# Offpunk is organized as follow:
# - a GeminiClient instance which handles the browsing of GeminiItems (= pages).
# - There’s only one GeminiClient. Each page is a GeminiItem (name is historical, as
# it could be non-gemini content)
# - A GeminiItem is created with an URL from which it will derives content.
# - Content include : a title, a body, an ansi-rendered-body and a list of links.
# - Each GeminiItem generates a "cache_path" in which it maintains a cached version of its content.

class GeminiItem():

    def __init__(self, url, name=""):
        if "://" not in url and ("./" not in url and url[0] != "/"):
            if not url.startswith("mailto:"):
                url = "gemini://" + url
        self.url = fix_ipv6_url(url).strip()
        self.name = name
        self.mime = None
        self.renderer = None
        self.links = None
        self.body = None
        parsed = urllib.parse.urlparse(self.url)
        if "./" in url or url[0] == "/":
            self.scheme = "file"
        else:
            self.scheme = parsed.scheme
        if self.scheme in ["file","mailto"]:
            self.local = True
            self.host = ""
            self.port = None
            self._cache_path = None
            # file:// is 7 char
            if self.url.startswith("file://"):
                self.path = self.url[7:]
            elif self.scheme == "mailto":
                self.path = parsed.path
            else:
                self.path = self.url
        else:
            self.local = False
            if self.scheme == "gopher":
                if parsed.path and parsed.path[0] == "/" and len(parsed.path) > 1:
                    splitted = parsed.path.split("/")
                    # We check if we have well a gopher type
                    if len(splitted[1]) == 1:
                        itemtype = parsed.path[1]
                        selector = parsed.path[2:]
                    else:
                        itemtype = "1"
                        selector = parsed.path
                    itemtype = parsed.path[1]
                    self.path = parsed.path[2:]
                else:
                    itemtype = "1"
                    self.path = parsed.path
                if itemtype == "0":
                    self.mime = "text/gemini"
                elif itemtype == "1":
                    self.mime = "text/gopher"
                elif itemtype == "h":
                    self.mime = "text/html"
                elif itemtype in ("9","g","I","s"):
                    self.mime = None
                else:
                    self.mime = "text/gopher"
            else:
                self.path = parsed.path
            if parsed.query:
                # we don’t add the query if path is too long because path above 260 char
                # are not supported and crash python.
                # Also, very long query are usually useless stuff
                if len(self.path+parsed.query) < 258:
                    self.path += "/" + parsed.query
            self.host = parsed.hostname
            #if not local, we create a local cache path.
            self._cache_path = os.path.expanduser(_CACHE_PATH + self.scheme +\
                                                    "/" + self.host + self.path)
            #There’s an OS limitation of 260 characters per path. 
            #We will thus cut the path enough to add the index afterward
            self._cache_path = self._cache_path[:249]
            # FIXME : this is a gross hack to give a name to
            # index files. This will break if the index is not
            # index.gmi. I don’t know how to know the real name
            # of the file. But first, we need to ensure that the domain name
            # finish by "/". Else, the cache will create a file, not a folder.
            if self.scheme.startswith("http"):
                index = "index.html"
            elif self.scheme == "gopher":
                index = "index.txt"
            else:
                index = "index.gmi"
            if self.path == "" or os.path.isdir(self._cache_path):
                if not self._cache_path.endswith("/"):
                    self._cache_path += "/"
                if not self.url.endswith("/"):
                    self.url += "/"
            if self._cache_path.endswith("/"):
                self._cache_path += index
            self.port = parsed.port or standard_ports.get(self.scheme, 0)
            
    def get_capsule_title(self):
            #small intelligence to try to find a good name for a capsule
            #we try to find eithe ~username or /users/username
            #else we fallback to hostname
            if self.scheme == "file":
                if self.name != "":
                    red_title = self.name
                else:
                    red_title = self.path
            else:
                red_title = self.host
                if "user" in self.path:
                    i = 0
                    splitted = self.path.split("/")
                    while i < (len(splitted)-1):
                        if splitted[i].startswith("user"):
                            red_title = splitted[i+1]
                        i += 1
                if "~" in self.path:
                    for pp in self.path.split("/"):
                        if pp.startswith("~"):
                            red_title = pp[1:]
            return red_title
    
    def is_cache_valid(self,validity=0):
        # Validity is the acceptable time for 
        # a cache to be valid  (in seconds)
        # If 0, then any cache is considered as valid
        # (use validity = 1 if you want to refresh everything)
        if self.local:
            return True
        elif self._cache_path :
            # If path is too long, we always return True to avoid
            # fetching it.
            if len(self._cache_path) > 259:
                self.links = []
                print("We return False because path is too long")
                return False
            if os.path.exists(self._cache_path):
                if validity > 0 :
                    last_modification = self.cache_last_modified()
                    now = time.time()
                    age = now - last_modification
                    return age < validity
                else:
                    return True
            else:
                #Cache has not been build
                return False
        else:
            #There’s not even a cache!
            return False

    def cache_last_modified(self):
        if self._cache_path:
            return os.path.getmtime(self._cache_path)
        elif self.local:
            return 0
        else:
            print("ERROR : NO CACHE in cache_last_modified")
            return None
    
    def get_body(self,as_file=False):
        if self.body and not as_file:
            return self.body
        if self.local:
            path = self.path
        elif self.is_cache_valid():
            path = self._cache_path
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
            print("ERROR: NO CACHE for %s" %self._cache_path)
            return error
    
    # This method is used to load once the list of links in a gi
    # Links can be followed, after a space, by a description/title
    def __make_links(self,links):
        self.links = []
        for l in links:
            #split between link and potential name
            splitted = l.split(maxsplit=1)
            url = self.absolutise_url(splitted[0])
            if looks_like_url(url):
                if len(splitted) > 1:
                    newgi = GeminiItem(url,splitted[1])
                else:
                    newgi = GeminiItem(url)
                self.links.append(newgi)

    def get_links(self):
        if self.links == None:
            if not self.renderer:
                self._set_renderer()
            if self.renderer:
                self.__make_links(self.renderer.get_links())
            else:
                self.links = []
        return self.links

    def get_link(self,nb):
        # == None allows to return False, even if the list is empty
        if self.links == None:
            r_body = self.get_rendered_body()
        if len(self.links) < nb:
            print("Index too high! No link %s for %s" %(nb,self.url))
            return None
        else:
            return self.links[nb-1]

    # Red title above rendered content
    def _make_terminal_title(self):
        title = self.get_capsule_title()
        #FIXME : how do I know that I’m offline_only ?
        if self.is_cache_valid(): #and self.offline_only and not self.local:
            last_modification = self.cache_last_modified()
            str_last = time.ctime(last_modification)
            nbr = len(self.get_links())
            if self.local:
                title += " (%s items)    \x1b[0;31m(local file)"%nbr
            else:
                title += " (%s links)    \x1b[0;31m(last accessed on %s)"%(nbr,str_last)
        rendered_title = "\x1b[31m\x1b[1m"+ title + "\x1b[0m"
        #FIXME: width to replace self.options["width"]
        wrapped = textwrap.fill(rendered_title,TERM_WIDTH)
        return wrapped + "\n"

    def _set_renderer(self,mime=None):
        if self.local and os.path.isdir(self.path):
            self.renderer = FolderRenderer("",self.path)
            return
        if not mime:
            mime = self.get_mime()
        mime_to_use = []
        for m in _FORMAT_RENDERERS:
            if fnmatch.fnmatch(mime, m):
                mime_to_use.append(m)
        if len(mime_to_use) > 0:
            current_mime = mime_to_use[0]
            func = _FORMAT_RENDERERS[current_mime]
            if current_mime.startswith("text"):
                self.renderer = func(self.get_body(),self.url)
                # We double check if the renderer is correct.
                # If not, we fallback to html
                # (this is currently only for XHTML, often being
                # mislabelled as xml thus RSS feeds)
                if not self.renderer.is_valid():
                    func = _FORMAT_RENDERERS["text/html"]
                    #print("Set (fallback)RENDERER to html instead of %s"%mime)
                    self.renderer = func(self.get_body(),self.url)
            else:
                #we don’t parse text, we give the file to the renderer
                self.renderer = func(self._cache_path,self.url)
                if not self.renderer.is_valid():
                    self.renderer = None

    
    def get_rendered_body(self,readable=True):
        if not self.renderer:
            self._set_renderer()
        if self.renderer:
            body = self.renderer.get_body(readable=readable)
            self.__make_links(self.renderer.get_links())
            to_return = self._make_terminal_title() + body
            return to_return
        else:
            self.links = []
            return None
        
    def get_cache_path(self,url=None):
        if url:
            g = GeminiItem(url)
            path = g.get_cache_path()
        elif self.local:
            path = self.path
        else:
            path = self._cache_path
        return path

    def get_filename(self):
        filename = os.path.basename(self.get_cache_path())
        return filename

    def write_body(self,body,mime=None):
        ## body is a copy of the raw gemtext
        ## Write_body() also create the cache !
        # DEFAULT GEMINI MIME
        self.body = body
        if mime:
            self.mime, mime_options = cgi.parse_header(mime)
        if not self.local:
            if self.mime and self.mime.startswith("text/"):
                mode = "w"
            else:
                mode = "wb"
            cache_dir = os.path.dirname(self._cache_path)
            # If the subdirectory already exists as a file (not a folder)
            # We remove it (happens when accessing URL/subfolder before
            # URL/subfolder/file.gmi.
            # This causes loss of data in the cache
            # proper solution would be to save "sufolder" as "sufolder/index.gmi"
            # If the subdirectory doesn’t exist, we recursively try to find one
            # until it exists to avoid a file blocking the creation of folders
            root_dir = cache_dir
            while not os.path.exists(root_dir):
                root_dir = os.path.dirname(root_dir)
            if os.path.isfile(root_dir):
                os.remove(root_dir)
            os.makedirs(cache_dir,exist_ok=True)
            with open(self._cache_path, mode=mode) as f:
                f.write(body)
                f.close()
         
    def get_mime(self):
        if self.mime:
            return self.mime
        elif self.is_cache_valid():
            if self.local:
                path = self.path
            else:
                path = self._cache_path
            if path.endswith(".gmi"):
                mime = "text/gemini"
            elif _HAS_MAGIC :
                mime = magic.from_file(path,mime=True)
                mime2,encoding = mimetypes.guess_type(path,strict=False)
                #If we hesitate between html and xml, takes the xml one
                #because the FeedRendered fallback to HtmlRenderer
                if mime2 and mime != mime2 and "html" in mime and "xml" in mime2:
                    mime = "text/xml"
                #Some xml/html document are considered as octet-stream
                if mime == "application/octet-stream":
                    mime = "text/xml"
            else:
                mime,encoding = mimetypes.guess_type(path,strict=False)
            #gmi Mimetype is not recognized yet
            if not mime and not _HAS_MAGIC :
                print("Cannot guess the mime type of the file. Install Python-magic")
            if mime.startswith("text") and mime not in _FORMAT_RENDERERS:
                #by default, we consider it’s gemini except for html
                mime = "text/gemini"
            self.mime = mime
        return self.mime
    
    def set_error(self,err):
    # If we get an error, we want to keep an existing cache
    # but we need to touch it or to create an empty one
    # to avoid hitting the error at each refresh
        if self.is_cache_valid():
            os.utime(self._cache_path)
        else:
            cache_dir = os.path.dirname(self._cache_path)
            root_dir = cache_dir
            while not os.path.exists(root_dir):
                root_dir = os.path.dirname(root_dir)
            if os.path.isfile(root_dir):
                os.remove(root_dir)
            os.makedirs(cache_dir,exist_ok=True)
            if os.path.isdir(cache_dir):
                with open(self._cache_path, "w") as cache:
                    cache.write(str(datetime.datetime.now())+"\n")
                    cache.write("ERROR while caching %s\n\n" %self.url)
                    cache.write("*****\n\n")
                    cache.write(str(type(err)) + " = " + str(err))
                    cache.write("\n" + str(err.with_traceback(None)))
                    cache.write("\n*****\n\n")
                    cache.write("If you believe this error was temporary, type ""reload"".\n")
                    cache.write("The ressource will be tentatively fetched during next sync.\n")
                    cache.close()
    
               
    def root(self):
        return GeminiItem(self._derive_url("/"))

    def up(self):
        pathbits = list(os.path.split(self.path.rstrip('/')))
        # Don't try to go higher than root or in config
        if self.local or len(pathbits) == 1 :
            return self
        # Get rid of bottom component
        pathbits.pop()
        new_path = os.path.join(*pathbits)
        return GeminiItem(self._derive_url(new_path))

    def query(self, query):
        query = urllib.parse.quote(query)
        return GeminiItem(self._derive_url(query=query))

    def _derive_url(self, path="", query=""):
        """
        A thin wrapper around urlunparse which avoids inserting standard ports
        into URLs just to keep things clean.
        """
        if not self.port or self.port == standard_ports[self.scheme] :
            host = self.host
        else:
            host = self.host + ":" + str(self.port)
        return urllib.parse.urlunparse((self.scheme,host,path or self.path, "", query, ""))

    def absolutise_url(self, relative_url):
        """
        Convert a relative URL to an absolute URL by using the URL of this
        GeminiItem as a base.
        """
        abs_url = urllib.parse.urljoin(self.url, relative_url)
        return abs_url

    def full_title(self):
        if self.renderer:
            title = self.renderer.get_title()
        else:
            # we take the last component of url as title
            if self.local:
                title = self.url.split("/")[-1]
            else:
                parsed = urllib.parse.urlparse(self.url)
                if parsed.path:
                    title = parsed.path.strip("/").split("/")[-1]
                else:
                    title = parsed.netloc
        title += " (%s)"%self.get_capsule_title()
        return title
        
    def to_map_line(self):
        return "=> {} {}\n".format(self.url, self.full_title())

CRLF = '\r\n'

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
        start = word.startswith("gemini://") or word.startswith("http://")\
                or word.startswith("https://")
        if not start and not mailto:
            return looks_like_url("gemini://"+word)
        elif mailto:
            return "@" in word
        else:
            return "." in word
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

def restricted(inner):
    def outer(self, *args, **kwargs):
        if self.restricted:
            print("Sorry, this command is not available in restricted mode!")
            return None
        else:
            return inner(self, *args, **kwargs)
    outer.__doc__ = inner.__doc__
    return outer

class GeminiClient(cmd.Cmd):

    def __init__(self, restricted=False, synconly=False):
        cmd.Cmd.__init__(self)

        # Set umask so that nothing we create can be read by anybody else.
        # The certificate cache and TOFU database contain "browser history"
        # type sensitivie information.
        os.umask(0o077)


        self.no_cert_prompt = "\x1b[38;5;76m" + "ON" + "\x1b[38;5;255m" + "> " + "\x1b[0m"
        self.cert_prompt = "\x1b[38;5;202m" + "ON" + "\x1b[38;5;255m"
        self.offline_prompt = "\x1b[38;5;76m" + "OFF" + "\x1b[38;5;255m" + "> " + "\x1b[0m"
        self.prompt = self.no_cert_prompt
        self.gi = None
        self.hist_index = 0
        self.idx_filename = ""
        self.index = []
        self.index_index = -1
        self.lookup = self.index
        self.marks = {}
        self.page_index = 0
        self.permanent_redirects = {}
        self.previous_redirectors = set()
        # Sync-only mode is restriced by design
        self.restricted = restricted or synconly
        self.tmp_filename = ""
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
            "ipv6" : True,
            "timeout" : 600,
            "short_timeout" : 5,
            "width" : 80,
            "auto_follow_redirects" : True,
            "gopher_proxy" : None,
            "tls_mode" : "tofu",
            "http_proxy": None,
            "https_everywhere": False,
            "archives_size" : 100,
            "history_size" : 100
        }
        global TERM_WIDTH
        TERM_WIDTH = self.options["width"]
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

    def _connect_to_tofu_db(self):

        db_path = os.path.join(_CONFIG_DIR, "tofu.db")
        self.db_conn = sqlite3.connect(db_path)
        self.db_cur = self.db_conn.cursor()

        self.db_cur.execute("""CREATE TABLE IF NOT EXISTS cert_cache
            (hostname text, address text, fingerprint text,
            first_seen date, last_seen date, count integer)""")

    def _go_to_gi(self, gi, update_hist=True, check_cache=True, handle=True,readable=True):
        """This method might be considered "the heart of Offpunk".
        Everything involved in fetching a gemini resource happens here:
        sending the request over the network, parsing the response, 
        storing the response in a temporary file, choosing
        and calling a handler program, and updating the history.
        Nothing is returned."""
        if not gi:
            return
        # Don't try to speak to servers running other protocols
        elif gi.scheme == "mailto":
            if handle and not self.sync_only:
                resp = input("Send an email to %s Y/N? " %gi.path)
                self.gi = gi
                if resp.strip().lower() in ("y", "yes"):
                    cmd = "xdg-open mailto:%s" %gi.path
                    subprocess.call(shlex.split(cmd))
            return
        elif gi.scheme not in ("file","gemini", "gopher", "http", "https") and not self.sync_only:
            print("Sorry, no support for {} links.".format(gi.scheme))
            return

        # Obey permanent redirects
        if gi.url in self.permanent_redirects:
            new_gi = GeminiItem(self.permanent_redirects[gi.url], name=gi.name)
            self._go_to_gi(new_gi)
            return
        
        if gi.scheme == "http" and self.options["https_everywhere"] :
            newurl = "https" + gi.url[4:]
            new_gi = GeminiItem(newurl,name=gi.name)
            self._go_to_gi(new_gi)
            return

        # Use cache or mark as to_fetch if resource is not cached
        # Why is this code useful ? It set the mimetype !
        if self.offline_only:
            if not gi.is_cache_valid():
                self.get_list("to_fetch")
                self.list_add_line("to_fetch",gi=gi,verbose=False)
                print("%s not available, marked for syncing"%gi.url)
                self.gi = gi
                return
        # check if local file exists.
        if gi.local and not os.path.exists(gi.path):
            print("Local file %s does not exist!" %gi.path)
            return

        elif not self.offline_only and not gi.local:
            try:
                if gi.scheme in ("http", "https"):
                    if self.support_http:
                        gi = self._fetch_http(gi)
                    elif handle and not self.sync_only:
                        if not _DO_HTTP:
                            print("Install python3-requests to handle http requests natively")
                        webbrowser.open_new_tab(gi.url)
                        return
                    else:
                        return
                elif gi.scheme in ("gopher"):
                    gi = self._fetch_gopher(gi,timeout=self.options["short_timeout"])
                else:
                    gi = self._fetch_over_network(gi)
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
                else:
                    if print_error:
                        print("ERROR4: " + str(type(err)) + " : " + str(err))
                        print("\n" + str(err.with_traceback(None)))
                return

        # Pass file to handler, unless we were asked not to
        if gi :
            rendered_body = gi.get_rendered_body(readable=readable)
            display = handle and not self.sync_only
            if rendered_body:
                self.index = gi.get_links()
                self.lookup = self.index
                self.page_index = 0
                self.index_index = -1
                if display:
                    self._temp_file(rendered_body)
                    cmd_str = _DEFAULT_CAT
                    subprocess.run(shlex.split(cmd_str % self.idx_filename))
            elif display :
                cmd_str = self._get_handler_cmd(gi.get_mime())
                try:
                    # get tmpfile from gi !
                    tmpfile = gi.get_body(as_file=True)
                    subprocess.call(shlex.split(cmd_str % tmpfile))
                except FileNotFoundError:
                    print("Handler program %s not found!" % shlex.split(cmd_str)[0])
                    print("You can use the ! command to specify another handler program or pipeline.")
        # Update state
        self.gi = gi
        if update_hist and not self.sync_only:
            self._update_history(gi)


    def _temp_file(self,content):
        # We actually put the body in a tmpfile before giving it to less
        if self.idx_filename:
            os.unlink(self.idx_filename)
        tmpf = tempfile.NamedTemporaryFile("w", encoding="UTF-8", delete=False)
        tmpf.write(content)
        tmpf.close()
        self.idx_filename = tmpf.name
        return self.idx_filename


    def _fetch_http(self,gi):
        header = {}
        header["User-Agent"] = "Offpunk browser v%s"%_VERSION
        response = requests.get(gi.url,headers=header)
        mime = response.headers['content-type']
        body = response.content
        if "text/" in mime:
            #body = response.text
            body = response.content.decode("UTF-8","replace")
        else:
            body = response.content
        gi.write_body(body,mime)
        return gi

    def _fetch_gopher(self,gi,timeout=10):
        if not looks_like_url(gi.url):
            print("%s is not a valide url" %gi.url)
        parsed =urllib.parse.urlparse(gi.url)
        host = parsed.hostname
        port = parsed.port or 70
        if parsed.path and parsed.path[0] == "/" and len(parsed.path) > 1:
            splitted = parsed.path.split("/")
            # We check if we have well a gopher type
            if len(splitted[1]) == 1:
                itemtype = parsed.path[1]
                selector = parsed.path[2:]
            else:
                itemtype = "1"
                selector = parsed.path
        else:
            itemtype = "1"
            selector = parsed.path
        addresses = socket.getaddrinfo(host, port, family=0,type=socket.SOCK_STREAM)
        s = socket.create_connection((host,port))
        for address in addresses:
            self._debug("Connecting to: " + str(address[4]))
            s = socket.socket(address[0], address[1])
            s.settimeout(timeout)
            try:
                s.connect(address[4])
                break
            except OSError as e:
                err = e
        else:
            # If we couldn't connect to *any* of the addresses, just
            # bubble up the exception from the last attempt and deny
            # knowledge of earlier failures.
            raise err
        if parsed.query:
            request = selector + "\t" + parsed.query
        else:
            request = selector
        request += "\r\n"
        s.sendall(request.encode("UTF-8"))
        response = s.makefile("rb").read()
        # Transcode response into UTF-8
        #if itemtype in ("0","1","h"):
        if not itemtype in ("9","g","I","s"):
            # Try most common encodings
            for encoding in ("UTF-8", "ISO-8859-1"):
                try:
                    response = response.decode("UTF-8")
                    break
                except UnicodeDecodeError:
                    pass
            else:
                # try to find encoding
                #if _HAS_CHARDET:
                detected = chardet.detect(response)
                response = response.decode(detected["encoding"])
                #else:
                    #raise UnicodeDecodeError
        if itemtype == "0":
            mime = "text/gemini"
        elif itemtype == "1":
            mime = "text/gopher"
        elif itemtype == "h":
            mime = "text/html"
        elif itemtype in ("9","g","I","s"):
            mime = None
        else:
            # by default, we should consider Gopher
            mime = "text/gopher"
        gi.write_body(response,mime)
        return gi

    # fetch_over_network will modify with gi.write_body(body,mime)
    # before returning the gi
    def _fetch_over_network(self, gi):
        
        # Be careful with client certificates!
        # Are we crossing a domain boundary?
        if self.active_cert_domains and gi.host not in self.active_cert_domains:
            if self.active_is_transient:
                print("Permanently delete currently active transient certificate?")
                resp = input("Y/N? ")
                if resp.strip().lower() in ("y", "yes"):
                    print("Destroying certificate.")
                    self._deactivate_client_cert()
                else:
                    print("Staying here.")
                    raise UserAbortException()
            else:
                print("PRIVACY ALERT: Deactivate client cert before connecting to a new domain?")
                resp = input("Y/N? ")
                if resp.strip().lower() in ("n", "no"):
                    print("Keeping certificate active for {}".format(gi.host))
                else:
                    print("Deactivating certificate.")
                    self._deactivate_client_cert()

        # Suggest reactivating previous certs
        if not self.client_certs["active"] and gi.host in self.client_certs:
            print("PRIVACY ALERT: Reactivate previously used client cert for {}?".format(gi.host))
            resp = input("Y/N? ")
            if resp.strip().lower() in ("y", "yes"):
                self._activate_client_cert(*self.client_certs[gi.host])
            else:
                print("Remaining unidentified.")
                self.client_certs.pop(gi.host)

        # Is this a local file?
        if gi.local:
            address, f = None, open(gi.path, "rb")
        else:
            address, f = self._send_request(gi)

        # Spec dictates <META> should not exceed 1024 bytes,
        # so maximum valid header length is 1027 bytes.
        header = f.readline(1027)
        header = header.decode("UTF-8")
        if not header or header[-1] != '\n':
            raise RuntimeError("Received invalid header from server!")
        header = header.strip()
        self._debug("Response header: %s." % header)
        # Validate header
        status, meta = header.split(maxsplit=1)
        if len(meta) > 1024 or len(status) != 2 or not status.isnumeric():
            f.close()
            raise RuntimeError("Received invalid header from server!")

        # Update redirect loop/maze escaping state
        if not status.startswith("3"):
            self.previous_redirectors = set()

        # Handle non-SUCCESS headers, which don't have a response body
        # Inputs
        if status.startswith("1"):
            if self.sync_only:
                return None
            else:
                print(meta)
                if status == "11":
                    user_input = getpass.getpass("> ")
                else:
                    user_input = input("> ")
                return self._fetch_over_network(gi.query(user_input))

        # Redirects
        elif status.startswith("3"):
            new_gi = GeminiItem(gi.absolutise_url(meta))
            if new_gi.url == gi.url:
                raise RuntimeError("URL redirects to itself!")
            elif new_gi.url in self.previous_redirectors:
                raise RuntimeError("Caught in redirect loop!")
            elif len(self.previous_redirectors) == _MAX_REDIRECTS:
                raise RuntimeError("Refusing to follow more than %d consecutive redirects!" % _MAX_REDIRECTS)
            elif self.sync_only:
                follow = self.automatic_choice
            # Never follow cross-domain redirects without asking
            elif new_gi.host != gi.host:
                follow = input("Follow cross-domain redirect to %s? (y/n) " % new_gi.url)
            # Never follow cross-protocol redirects without asking
            elif new_gi.scheme != gi.scheme:
                follow = input("Follow cross-protocol redirect to %s? (y/n) " % new_gi.url)
            # Don't follow *any* redirect without asking if auto-follow is off
            elif not self.options["auto_follow_redirects"]:
                follow = input("Follow redirect to %s? (y/n) " % new_gi.url)
            # Otherwise, follow away
            else:
                follow = "yes"
            if follow.strip().lower() not in ("y", "yes"):
                raise UserAbortException()
            self._debug("Following redirect to %s." % new_gi.url)
            self._debug("This is consecutive redirect number %d." % len(self.previous_redirectors))
            self.previous_redirectors.add(gi.url)
            if status == "31":
                # Permanent redirect
                self.permanent_redirects[gi.url] = new_gi.url
            return self._fetch_over_network(new_gi)

        # Errors
        elif status.startswith("4") or status.startswith("5"):
            raise RuntimeError(meta)

        # Client cert
        elif status.startswith("6"):
            self._handle_cert_request(meta)
            return self._fetch_over_network(gi)

        # Invalid status
        elif not status.startswith("2"):
            raise RuntimeError("Server returned undefined status code %s!" % status)

        # If we're here, this must be a success and there's a response body
        assert status.startswith("2")
        
        mime = meta
        # Read the response body over the network
        fbody = f.read()
        # DEFAULT GEMINI MIME
        if mime == "":
            mime = "text/gemini; charset=utf-8"
        shortmime, mime_options = cgi.parse_header(mime)
        if "charset" in mime_options:
            try:
                codecs.lookup(mime_options["charset"])
            except LookupError:
                raise RuntimeError("Header declared unknown encoding %s" % value)
        if shortmime.startswith("text/"):
            #Get the charset and default to UTF-8 in none
            encoding = mime_options.get("charset", "UTF-8")
            try:
                body = fbody.decode(encoding)
            except UnicodeError:
                raise RuntimeError("Could not decode response body using %s\
                                    encoding declared in header!" % encoding)
        else:
            body = fbody
        gi.write_body(body,mime)    
        return gi

    def _send_request(self, gi):
        """Send a selector to a given host and port.
        Returns the resolved address and binary file with the reply."""
        if gi.scheme == "gemini":
            # For Gemini requests, connect to the host and port specified in the URL
            host, port = gi.host, gi.port
        elif gi.scheme == "gopher":
            # For Gopher requests, use the configured proxy
            host, port = self.options["gopher_proxy"].rsplit(":", 1)
            self._debug("Using gopher proxy: " + self.options["gopher_proxy"])
        elif gi.scheme in ("http", "https"):
            host, port = self.options["http_proxy"].rsplit(":",1)
            self._debug("Using http proxy: " + self.options["http_proxy"])
        # Do DNS resolution
        addresses = self._get_addresses(host, port)

        # Prepare TLS context
        protocol = ssl.PROTOCOL_TLS if sys.version_info.minor >=6 else ssl.PROTOCOL_TLSv1_2
        context = ssl.SSLContext(protocol)
        # Use CAs or TOFU
        if self.options["tls_mode"] == "ca":
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
            context.load_default_certs()
        else:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        # Impose minimum TLS version
        ## In 3.7 and above, this is easy...
        if sys.version_info.minor >= 7:
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        ## Otherwise, it seems very hard...
        ## The below is less strict than it ought to be, but trying to disable
        ## TLS v1.1 here using ssl.OP_NO_TLSv1_1 produces unexpected failures
        ## with recent versions of OpenSSL.  What a mess...
        else:
            context.options |= ssl.OP_NO_SSLv3
            context.options |= ssl.OP_NO_SSLv2
        # Try to enforce sensible ciphers
        try:
            context.set_ciphers("AESGCM+ECDHE:AESGCM+DHE:CHACHA20+ECDHE:CHACHA20+DHE:!DSS:!SHA1:!MD5:@STRENGTH")
        except ssl.SSLError:
            # Rely on the server to only support sensible things, I guess...
            pass
        # Load client certificate if needed
        if self.client_certs["active"]:
            certfile, keyfile = self.client_certs["active"]
            context.load_cert_chain(certfile, keyfile)
        
        # Connect to remote host by any address possible
        err = None
        for address in addresses:
            self._debug("Connecting to: " + str(address[4]))
            s = socket.socket(address[0], address[1])
            if self.sync_only:
                timeout = self.options["short_timeout"]
            else:
                timeout = self.options["timeout"]
            s.settimeout(timeout)
            s = context.wrap_socket(s, server_hostname = gi.host)
            try:
                s.connect(address[4])
                break
            except OSError as e:
                err = e
        else:
            # If we couldn't connect to *any* of the addresses, just
            # bubble up the exception from the last attempt and deny
            # knowledge of earlier failures.
            raise err

        if sys.version_info.minor >=5:
            self._debug("Established {} connection.".format(s.version()))
        self._debug("Cipher is: {}.".format(s.cipher()))

        # Do TOFU
        if self.options["tls_mode"] != "ca":
            cert = s.getpeercert(binary_form=True)
            self._validate_cert(address[4][0], host, cert)

        # Remember that we showed the current cert to this domain...
        if self.client_certs["active"]:
            self.active_cert_domains.append(gi.host)
            self.client_certs[gi.host] = self.client_certs["active"]

        # Send request and wrap response in a file descriptor
        self._debug("Sending %s<CRLF>" % gi.url)
        s.sendall((gi.url + CRLF).encode("UTF-8"))
        mf= s.makefile(mode = "rb")
        return address, mf

    def _get_addresses(self, host, port):
        # DNS lookup - will get IPv4 and IPv6 records if IPv6 is enabled
        if ":" in host:
            # This is likely a literal IPv6 address, so we can *only* ask for
            # IPv6 addresses or getaddrinfo will complain
            family_mask = socket.AF_INET6
        elif socket.has_ipv6 and self.options["ipv6"]:
            # Accept either IPv4 or IPv6 addresses
            family_mask = 0
        else:
            # IPv4 only
            family_mask = socket.AF_INET
        addresses = socket.getaddrinfo(host, port, family=family_mask,
                type=socket.SOCK_STREAM)
        # Sort addresses so IPv6 ones come first
        addresses.sort(key=lambda add: add[0] == socket.AF_INET6, reverse=True)

        return addresses


    def _handle_cert_request(self, meta):

        # Don't do client cert stuff in restricted mode, as in principle
        # it could be used to fill up the disk by creating a whole lot of
        # certificates
        if self.restricted:
            print("The server is requesting a client certificate.")
            print("These are not supported in restricted mode, sorry.")
            raise UserAbortException()

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
                if _HAS_CRYPTOGRAPHY:
                    # Load the most frequently seen certificate to see if it has
                    # expired
                    certdir = os.path.join(_CONFIG_DIR, "cert_cache")
                    with open(os.path.join(certdir, most_frequent_cert+".crt"), "rb") as fp:
                        previous_cert = fp.read()
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
            cmd_str = "xdg-open %s"
        self._debug("Using handler: %s" % cmd_str)
        return cmd_str

    #TODO: remove format_geminiitem
    def _format_geminiitem(self, index, gi, url=False):
        protocol = "" if gi.scheme == "gemini" else " %s" % gi.scheme
        line = "[%d%s] %s" % (index, protocol, gi.name or gi.url)
        if gi.name and url:
            line += " (%s)" % gi.url
        return line

    def _show_lookup(self, offset=0, end=None, url=False):
        for n, gi in enumerate(self.lookup[offset:end]):
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

    def _get_active_tmpfile(self):
        if self.gi.get_mime() in _FORMAT_RENDERERS:
            return self.idx_filename
        else:
            return self.tmp_filename

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
        self.prompt = self.cert_prompt + "+" + os.path.basename(certfile).replace('.crt','') + "> " + "\x1b[0m"
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
        elif line.strip() == "..":
            return self.do_up()
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
        try:
            gi = self.lookup[n-1]
        except IndexError:
            print ("Index too high!")
            return

        self.index_index = n
        self._go_to_gi(gi)

    ### Settings
    @restricted
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
                print("Unrecognised option %s" % option)
        else:
            # Set value of one specific setting
            option, value = line.split(" ", 1)
            if option not in self.options:
                print("Unrecognised option %s" % option)
                return
            # Validate / convert values
            if option == "gopher_proxy":
                if ":" not in value:
                    value += ":1965"
                else:
                    host, port = value.rsplit(":",1)
                    if not port.isnumeric():
                        print("Invalid proxy port %s" % port)
                        return
            elif option == "tls_mode":
                if value.lower() not in ("ca", "tofu"):
                    print("TLS mode must be `ca` or `tofu`!")
                    return
            elif option == "width":
                if value.isnumeric():
                    value = int(value)
                    print("changing width to ",value)
                    global TERM_WIDTH
                    TERM_WIDTH = value
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

    @restricted
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

    @restricted
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

    def do_copy(self, *args):
        """Copy the content of the last visited page as gemtext in the clipboard.
Use with "url" as argument to only copy the adress.
Use with "raw" to copy the content as seen in your terminal (not gemtext)"""
        if self.gi:
            if _HAS_XSEL:
                if args and args[0] == "url":
                    subprocess.call(("echo %s |xsel -b -i" % self.gi.url), shell=True)
                elif args and args[0] == "raw":
                    subprocess.call(("cat %s |xsel -b -i" % self._get_active_tmpfile()), shell=True)
                else:
                    subprocess.call(("cat %s |xsel -b -i" % self.gi.get_body(as_file=True)), shell=True)
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
                clipboards.append(subprocess.check_output(['xsel','-p'],text=True))
                clipboards.append(subprocess.check_output(['xsel','-s'],text=True))
                clipboards.append(subprocess.check_output(['xsel','-b'],text=True))
                for u in clipboards:
                    if looks_like_url(u) :
                        urls.append(u)
                if len(urls) > 1:
                    self.lookup = []
                    for u in urls:
                        self.lookup.append(GeminiItem(u))
                    print("Where do you want to go today?")
                    self._show_lookup()
                elif len(urls) == 1:
                    self.do_go(urls[0])
                else:
                    print("Go where? (hint: simply copy an URL)")
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

    @needs_gi
    def do_reload(self, *args):
        """Reload the current URL."""
        if self.offline_only:
            self.get_list("to_fetch")
            self.list_add_line("to_fetch",gi=self.gi,verbose=False)
            print("%s marked for syncing" %self.gi.url)
        else:
            self._go_to_gi(self.gi, check_cache=False)

    @needs_gi
    def do_up(self, *args):
        """Go up one directory in the path."""
        self._go_to_gi(self.gi.up())

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

    def do_next(self, *args):
        """Go to next item after current in index."""
        return self.onecmd(str(self.index_index+1))

    def do_previous(self, *args):
        """Go to previous item before current in index."""
        self.lookup = self.index
        return self.onecmd(str(self.index_index-1))

    @needs_gi
    def do_root(self, *args):
        """Go to root selector of the server hosting current item."""
        self._go_to_gi(self.gi.root())

    def do_tour(self, line):
        """Add index items as waypoints on a tour, which is basically a FIFO
queue of gemini items.

Items can be added with `tour 1 2 3 4` or ranges like `tour 1-4`.
All items in current menu can be added with `tour *`.
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
                self.list_go_to_line("1","tour")
                self.list_rm_url(self.gi.url,"tour")
        elif line == "ls":
            self.list_show("tour")
        elif line == "clear":
            for l in self.list_get_links("tour"):
                self.list_rm_url(l.url,"tour")
        elif line == "*":
            for l in self.lookup:
                self.list_add_line("tour",gi=l,verbose=False)
        elif line == ".":
            self.list_add_line("tour",verbose=False)
        elif looks_like_url(line):
            self.list_add_line("tour",gi=GeminiItem(line))
        else:
            for index in line.split():
                try:
                    pair = index.split('-')
                    if len(pair) == 1:
                        # Just a single index
                        n = int(index)
                        gi = self.lookup[n-1]
                        self.list_add_line("tour",gi=gi,verbose=False)
                    elif len(pair) == 2:
                        # Two endpoints for a range of indices
                        if int(pair[0]) < int(pair[1]):
                            for n in range(int(pair[0]), int(pair[1]) + 1):
                                gi = self.lookup[n-1]
                                self.list_add_line("tour",gi=gi,verbose=False)
                        else:
                            for n in range(int(pair[0]), int(pair[1]) - 1, -1):
                                gi = self.lookup[n-1]
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
Think of it like marks in vi: 'mark a'='ma' and 'go a'=''a'."""
        line = line.strip()
        if not line:
            for mark, gi in self.marks.items():
                print("[%s] %s (%s)" % (mark, gi.name, gi.url))
        elif line.isalpha() and len(line) == 1:
            self.marks[line] = self.gi
        else:
            print("Invalid mark, must be one letter")

    def do_version(self, line):
        """Display version and system information."""
        def has(value):
            if value:
                return "\t\x1b[1;32mInstalled\x1b[0m\n"
            else:
                return "\t\x1b[1;31mNot Installed\x1b[0m\n"
        output = "Offpunk " + _VERSION + "\n"
        output += "===========\n"
        output += " - python-editor       : " + has(_HAS_EDITOR)
        output += " - python-ansiwrap     : " + has(_HAS_ANSIWRAP)
        output += " - python-pil          : " + has(_HAS_PIL)
        output += " - python-cryptography : " + has(_HAS_CRYPTOGRAPHY)
        output += " - python-magic        : " + has(_HAS_MAGIC)
        output += " - python-requests     : " + has(_DO_HTTP)
        output += " - python-feedparser   : " + has(_DO_FEED)
        output += " - python-bs4          : " + has(_HAS_SOUP)
        output += " - python-readability  : " + has(_HAS_READABILITY)
        output += " - python-xdg          : " + has(_HAS_XDG)
        output += " - chafa               : " + has(_HAS_CHAFA)
        output += " - xsel                : " + has(_HAS_XSEL)

        output += "\nFeatures :\n"
        output += " - Render images (ansiwrap,pil,chafa) : " + has(_RENDER_IMAGE)
        output += " - Render HTML (bs4, readability)     : " + has(_DO_HTML)
        output += " - Render Atom/RSS feeds (feedparser) : " + has(_DO_FEED)
        output += " - Connect to http/https (requests)   : " + has(_DO_HTTP)
        output += " - copy to/from clipboard (xsel)      : " + has(_HAS_XSEL)
        output += "\n"
        output += "Config directory    : " +  _CONFIG_DIR + "\n"
        output += "User Data directory : " +  _DATA_DIR + "\n"
        output += "CACHE               : " +  _CACHE_PATH

        print(output)

    ### Stuff that modifies the lookup table
    def do_ls(self, line):
        """List contents of current index.
Use 'ls -l' to see URLs."""
        self.lookup = self.index
        self._show_lookup(url = "-l" in line)
        self.page_index = 0

    def do_gus(self, line):
        """Submit a search query to the geminispace.info search engine."""
        gus = GeminiItem("gemini://geminispace.info/search")
        self._go_to_gi(gus.query(line))

    def do_history(self, *args):
        """Display history."""
        self.list_show("history")

    def do_find(self, searchterm):
        """Find in the list of links (case insensitive)."""
        results = [
            gi for gi in self.lookup if searchterm.lower() in gi.name.lower()]
        if results:
            self.lookup = results
            self._show_lookup()
            self.page_index = 0
        else:
            print("No results found.")

    def emptyline(self):
        """Page through index ten lines at a time."""
        i = self.page_index
        if i > len(self.lookup):
            return
        self._show_lookup(offset=i, end=i+10)
        self.page_index += 10

    ### Stuff that does something to most recently viewed item
    @needs_gi
    def do_cat(self, *args):
        """Run most recently visited item through "cat" command."""
        subprocess.call(shlex.split("cat %s" % self._get_active_tmpfile()))

    @needs_gi
    def do_less(self, *args):
        """Run most recently visited item through "less" command.
Use "less full" to see a complete html page instead of the article view.
(the "full" argument has no effect on Gemtext content)."""
        if self.gi and args and args[0] == "full":
            self._go_to_gi(self.gi,readable=False)
        elif self.gi.is_cache_valid():
            cmd_str = _DEFAULT_LESS % self._get_active_tmpfile()
            subprocess.call(cmd_str, shell=True)
        else:
            self.do_go(self.gi.url)

    @needs_gi
    def do_open(self, *args):
        """Open current item with the configured handler or xdg-open.
see "handler" command to set your own."""
        cmd_str = self._get_handler_cmd(self.gi.get_mime())
        file_path = "\"%s\"" %self.gi.get_body(as_file=True)
        cmd_str = cmd_str % file_path 
        subprocess.call(cmd_str,shell=True)


    @needs_gi
    def do_fold(self, *args):
        """Run most recently visited item through "fold" command."""
        cmd_str = _DEFAULT_LESS % self._get_active_tmpfile()
        subprocess.call("%s | fold -w 70 -s" % cmd_str, shell=True)

    @restricted
    @needs_gi
    def do_shell(self, line):
        """'cat' most recently visited item through a shell pipeline."""
        subprocess.call(("cat %s |" % self._get_active_tmpfile()) + line, shell=True)

    @restricted
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
                gi = self.lookup[index-1]
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
            print("Saved to %s" % filename)
            shutil.copyfile(gi.get_body(as_file=True), filename)

        # Restore gi if necessary
        if index != None:
            self._go_to_gi(last_gi, handle=False)

    @needs_gi
    def do_url(self, *args):
        """Print URL of most recently visited item."""
        print(self.gi.url)

    ### Bookmarking stuff
    @restricted
    @needs_gi
    def do_add(self, line):
        """Add the current URL to the list specied as argument.
If no argument given, URL is added to Bookmarks."""
        args = line.split()
        if len(args) < 1 :
            self.list_add_line("bookmarks")
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
                    title = "Subscriptions (new links in those pages will be added to tour)"
                elif list == "to_fetch":
                    title = "Links requested and to be fetched during the next --sync"
                else:
                    title = None
                self.list_create(list, title=title)
                list_path = self.list_path(list)
        return list_path
    
    def do_subscribe(self,line):
        """Subscribe to current page by saving it in the "subscribed" list.
If a new link is found in the page during a --sync, the new link is automatically
fetched and added to your next tour.
To unsubscribe, remove the page from the "subscribed" list."""
        list_path = self.get_list("subscribed")
        added = self.list_add_line("subscribed",verbose=False)
        if added :
            print("Subscribed to %s" %self.gi.url)
        else:
            print("You are already subscribed to %s"%self.gi.url)

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
    
    def do_archive(self,args):
        """Archive current page by removing it from every list and adding it to
archives, which is a special historical list limited in size. It is similar to `move archives`."""
        for li in self.list_lists():
            if li not in ["archives", "history"]:
                deleted = self.list_rm_url(self.gi.url,li)
                if deleted:
                    print("Removed from %s"%li)
        self.list_add_top("archives",limit=self.options["archives_size"])
        print("Archiving: %s"%self.gi.full_title())
        print("\x1b[2;34mCurrent maximum size of archives : %s\x1b[0m" %self.options["archives_size"])

    def list_add_line(self,list,gi=None,verbose=True):
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
                    if gi.url in sp:
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
            l_file.write(stri)
            counter = 0
            to_truncate = truncate_lines
            for l in lines:
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
        list_path = self.list_path(list)
        if list_path:
            to_return = False
            with open(list_path,"r") as lf:
                lines = lf.readlines()
                lf.close()
            with open(list_path,"w") as lf:
                for l in lines:
                    # we separate components of the line
                    # to ensure we identify a complete URL, not a part of it
                    splitted = l.split()
                    if url not in splitted:
                        #sometimes, we must remove the ending "/"
                        if url.endswith("/") and url[:-1] in splitted:
                            to_return = True
                        else:
                            lf.write(l)
                    else:
                        to_return = True
                lf.close()
            return to_return
        else:
            return False

    def list_get_links(self,list):
        list_path = self.list_path(list)
        if list_path:
            gi = GeminiItem("file://" + list_path)
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
            gi = GeminiItem("file://" + list_path,list)
            gi = gi.get_link(int(line))
            display = not self.sync_only 
            self._go_to_gi(gi,handle=display)

    def list_show(self,list):
        list_path = self.list_path(list)
        if not list_path:
            print("List %s does not exist. Create it with ""list create %s"""%(list,list))
        else:
            gi = GeminiItem("file://" + list_path,list)
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

    def list_create(self,list,title=None):
        list_path = self.list_path(list)
        if list in ["create","edit","delete"]:
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
                        isremoved = self.list_rm_url(self.gi.url,l)
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
    
    def do_list(self,arg):
        """Manage list of bookmarked pages.
- list : display available lists
- list $LIST : display pages in $LIST
- list create $NEWLIST : create a new list
- list edit $LIST : edit the list
- list delete $LIST : delete a list permanently (a confirmation is required)
See also :
- add $LIST (to add current page to $LIST or, by default, to bookmarks)
- move $LIST (to add current page to list while removing from all others)
- archive (to remove current page from all lists while adding to archives)"""
        listdir = os.path.join(_DATA_DIR,"lists")
        os.makedirs(listdir,exist_ok=True)
        if not arg:
            lists = self.list_lists()
            if len(lists) > 0:
                lgi = GeminiItem(listdir, "My lists")
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
                if not _HAS_EDITOR:
                    print("Please install python-editor to edit you lists")
                elif len(args) > 1:
                    if args[1] in self.list_lists():
                        path = os.path.join(listdir,args[1]+".gmi")
                        editor.edit(path)
                    else:
                        print("A valid list name is required to edit a list")
                else:
                    print("A valid list name is required to edit a list")
            elif args[0] == "delete":
                if len(args) > 1:
                    if args[1] in ["tour","to_fetch","bookmarks","history","archives"]:
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
            print("%s is aan alias for '%s'" %(arg,full_cmd))
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

    ### The end!
    def do_quit(self, *args):
        """Exit Offpunk."""
        # Close TOFU DB
        self.db_conn.commit()
        self.db_conn.close()
        # Clean up after ourself
        if self.tmp_filename and os.path.exists(self.tmp_filename):
            os.unlink(self.tmp_filename)
        if self.idx_filename and os.path.exists(self.idx_filename):
            os.unlink(self.idx_filename)

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
    parser = argparse.ArgumentParser(description='A command line gemini client.')
    parser.add_argument('--bookmarks', action='store_true',
                        help='start with your list of bookmarks')
    parser.add_argument('--tls-cert', metavar='FILE', help='TLS client certificate file')
    parser.add_argument('--tls-key', metavar='FILE', help='TLS client certificate private key file')
    parser.add_argument('--restricted', action="store_true", help='Disallow shell, add, and save commands')
    parser.add_argument('--sync', action='store_true', 
                        help='run non-interactively to build cache by exploring bookmarks')
    parser.add_argument('--assume-yes', action='store_true', 
                        help='assume-yes when asked questions about certificates/redirections during sync')
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
    parser.add_argument('url', metavar='URL', nargs='*',
                        help='start with this URL')
    args = parser.parse_args()

    # Handle --version
    if args.version:
        print("Offpunk " + _VERSION)
        sys.exit()

    # Instantiate client
    gc = GeminiClient(restricted=args.restricted,synconly=args.sync)

    if not args.sync and not args.fetch_later:
        # Process config file
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
                    gc.cmdqueue.append(line)
        print("Welcome to Offpunk!")
        if args.restricted:
            print("Restricted mode engaged!")
        print("Type `help` to get the list of available command.")

    # Act on args
    if args.tls_cert:
        # If tls_key is None, python will attempt to load the key from tls_cert.
        gc._activate_client_cert(args.tls_cert, args.tls_key)
    if args.bookmarks:
        gc.cmdqueue.append("bookmarks")
    elif args.url:
        if len(args.url) == 1:
            gc.cmdqueue.append("go %s" % args.url[0])
        else:
            for url in args.url:
                if not url.startswith("gemini://"):
                    url = "gemini://" + url
                gc.cmdqueue.append("tour %s" % url)
            gc.cmdqueue.append("tour")

    if args.disable_http:
        gc.support_http = False

    # Endless interpret loop
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
        # fetch_gitem is the core of the sync algorithm.
        # It takes as input :
        # - a GeminiItem to be fetched
        # - depth : the degree of recursion to build the cache (0 means no recursion)
        # - validity : the age, in seconds, existing caches need to have before
        #               being refreshed (0 = never refreshed if it already exists)
        # - savetotour : if True, newly cached items are added to tour
        if args.assume_yes:
            gc.automatic_choice = "y"
        def add_to_tour(gitem):
            if gitem.is_cache_valid():
                print("  -> adding to tour: %s" %gitem.url)
                gc.list_add_line("tour",gi=gitem,verbose=False)
                return True
            else:
                return False

        def fetch_gitem(gitem,depth=0,validity=0,savetotour=False,count=[0,0],strin=""):
            #savetotour = True will save to tour newly cached content
            # else, do not save to tour
            #regardless of valitidy
            if not gitem.is_cache_valid(validity=validity):
                if strin != "":
                    endline = '\r'
                else:
                    endline = None
                #Did we already had a cache (even an old one) ?
                isnew = not gitem.is_cache_valid()
                print("%s [%s/%s] Fetch "%(strin,count[0],count[1]),gitem.url,end=endline)
                gc._go_to_gi(gitem,update_hist=False)
                if savetotour and isnew and gitem.is_cache_valid():
                    #we add to the next tour only if we managed to cache 
                    #the ressource
                    add_to_tour(gitem)
            #Now, recursive call, even if we didn’t refresh the cache
            if depth > 0:
                #we only savetotour at the first level of recursion
                if depth > 1:
                    savetotour=False
                links = gitem.get_links()
                subcount = [0,len(links)]
                d = depth - 1
                for k in links:
                    #recursive call (validity is always 0 in recursion)
                    substri = strin + " -->"
                    subcount[0] += 1
                    fetch_gitem(k,depth=d,validity=0,savetotour=savetotour,\
                                        count=subcount,strin=substri)
        
        def fetch_list(list,validity=0,depth=1,tourandremove=False,tourchildren=False):
            links = gc.list_get_links(list)
            end = len(links)
            counter = 0
            print(" * * * %s to fetch in %s * * *" %(end,list))
            for l in links:
                counter += 1
                fetch_gitem(l,depth=depth,validity=validity,savetotour=tourchildren,count=[counter,end])
                if tourandremove:
                    if add_to_tour(l):
                        gc.list_rm_url(l.url,list)
            
        if args.cache_validity:
            refresh_time = int(args.cache_validity)
        else:
            # if no refresh time, a default of 0 is used (which means "infinite")
            refresh_time = 0
        if args.depth:
            depth = int(args.depth)
        else:
            depth = 1
        gc.sync_only = True
        lists = gc.list_lists()
        # We will fetch all the lists except "archives" and "history"
        # We keep tour for the last round
        if "tour" in lists:
            lists.remove("tour")
        if "archives" in lists:
            lists.remove("archives")
        if "history" in lists:
            lists.remove("history")
        # We start with the "subscribed" as we need to find new items
        if "subscribed" in lists:
            lists.remove("subscribed")
            fetch_list("subscribed",validity=refresh_time,depth=depth,tourchildren=True)
        #Then the fetch list (item are removed from the list after fetch)
        if "to_fetch" in lists:
            lists.remove("to_fetch")
            fetch_list("to_fetch",validity=refresh_time,depth=depth,tourandremove=True)
        #then we fetch all the rest (including bookmarks and tour)
        for l in lists:
            fetch_list(l,validity=refresh_time,depth=depth)
        #tour should be the last one as item my be added to it by others
        fetch_list("tour",validity=refresh_time,depth=depth)


        gc.onecmd("blackbox")
    else:
        while True:
            try:
                gc.cmdloop()
            except KeyboardInterrupt:
                print("")

if __name__ == '__main__':
    main()
