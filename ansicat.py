#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import textwrap
import time
import html
import urllib
import argparse
import mimetypes
import fnmatch
import netcache
import offthemes
from offutils import run,term_width,is_local,looks_like_base64, looks_like_url
import base64
from offutils import xdg 
try:
    from readability import Document
    _HAS_READABILITY = True
except ModuleNotFoundError:
    _HAS_READABILITY = False

try:
    from bs4 import BeautifulSoup
    from bs4 import Comment
    #if bs4 version >= 4.11, we need to silent some xml warnings
    import bs4
    version = bs4.__version__.split(".")
    recent = False
    if int(version[0]) > 4:
        recent = True
    elif int(version[0]) == 4:
        recent = int(version[1]) >= 11
    if recent:
        # As this is only for silencing some warnings, we fail
        # silently. We don’t really care
        try:
            from bs4 import XMLParsedAsHTMLWarning
            import warnings
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        except:
            pass
    _HAS_SOUP = True
except ModuleNotFoundError:
    _HAS_SOUP = False

_DO_HTML = _HAS_SOUP #and _HAS_READABILITY
if _DO_HTML and not _HAS_READABILITY:
    print("To improve your web experience (less cruft in webpages),")
    print("please install python3-readability or readability-lxml")

try:
    import feedparser
    _DO_FEED = True
except ModuleNotFoundError:
    _DO_FEED = False

_HAS_TIMG = shutil.which('timg')
_HAS_CHAFA = shutil.which('chafa')
_NEW_CHAFA = False
_NEW_TIMG = False
_RENDER_IMAGE = False
_HAS_PIL = False

# All this code to know if we render image inline or not
if _HAS_CHAFA:
    # starting with 1.10, chafa can return only one frame
    # which allows us to drop dependancy for PIL
    output = run("chafa --version")
    # output is "Chafa version M.m.p"
    # check for m < 1.10
    try:
        chafa_major, chafa_minor, _ = output.split("\n")[0].split(" ")[-1].split(".")
        if int(chafa_major) >= 1 and int(chafa_minor) >= 10:
            _NEW_CHAFA = True
    except:
        pass
if _NEW_CHAFA :
    _RENDER_IMAGE = True
if _HAS_TIMG :
    try:
        output = run("timg --version")
    except subprocess.CalledProcessError:
        output = False
    # We don’t deal with timg before 1.3.2 (looping options)
    if output and output[5:10] > "1.3.2":
        _NEW_TIMG = True
        _RENDER_IMAGE = True
elif _HAS_CHAFA and not _NEW_CHAFA:
    try:
        from PIL import Image
        _HAS_PIL = True
        _RENDER_IMAGE = True
    except ModuleNotFoundError:
        _HAS_PIL = False
if not _RENDER_IMAGE:
    print("To render images inline, you need either chafa or timg.")
    if not _NEW_CHAFA and not _NEW_TIMG:
        print("Before Chafa 1.10, you also need python-pil")



#return ANSI text that can be show by less
def inline_image(img_file,width):
    #We don’t even try displaying pictures that are not there
    if not os.path.exists(img_file):
        return ""
    #Chafa is faster than timg inline. Let use that one by default
    #But we keep a list of "inlines" in case chafa fails
    inlines = []
    ansi_img = ""
    #We avoid errors by not trying to render non-image files
    if shutil.which("file"):
        mime = run("file -b --mime-type %s", parameter=img_file).strip()
        if not "image" in mime:
            return ansi_img
    if _HAS_CHAFA:
        if _HAS_PIL and not _NEW_CHAFA:
            # this code is a hack to remove frames from animated gif
            img_obj = Image.open(img_file)
            if hasattr(img_obj,"n_frames") and img_obj.n_frames > 1:
                # we remove all frames but the first one
                img_obj.save(img_file,format="gif",save_all=False)
            inlines.append("chafa --bg white -s %s -f symbols")
        elif _NEW_CHAFA:
            inlines.append("chafa --bg white -t 1 -s %s -f symbols --animate=off")
    if _NEW_TIMG:
        inlines.append("timg --frames=1 -p q -g %sx1000")
    image_success = False
    while not image_success and len(inlines)>0:
        cmd = inlines.pop(0)%width + " %s"
        try:
            ansi_img = run(cmd, parameter=img_file)
            image_success = True
        except Exception as err:
            ansi_img = "***IMAGE ERROR***\n%s…\n…%s" %(str(err)[:50],str(err)[-50:])
    return ansi_img

def terminal_image(img_file):
    #Render by timg is better than old chafa.
    # it is also centered
    cmds = []
    if _NEW_CHAFA:
        cmds.append("chafa -C on -d 0 --bg white -w 1")
    elif _HAS_CHAFA:
        cmds.append("chafa -d 0 --bg white -w 1")
    if _NEW_TIMG:
        cmds.append("timg --loops=1 -C")
    image_success = False
    while not image_success and len(cmds) > 0:
        cmd = cmds.pop(0) + " %s"
        try:
            run(cmd, parameter=img_file, direct_output=True)
            image_success = True
        except Exception as err:
            print(err)


# First, we define the different content->text renderers, outside of the rest
# (They could later be factorized in other files or replaced)
class AbstractRenderer():
    def __init__(self,content,url,center=True):
        self.url = url
        self.body = str(content)
        #there’s one rendered text and one links table per mode
        self.rendered_text = {}
        self.links = {}
        self.images = {}
        self.title = None
        self.validity = True
        self.temp_files = {}
        self.center = center
        self.last_mode = "readable"
        self.theme = offthemes.default

    def display(self,mode=None,directdisplay=False):
        wtitle = self.get_formatted_title()
        if mode == "source":
            body = self.body
        else:
            body = wtitle + "\n" + self.get_body(mode=mode)
        if directdisplay:
            print(body)
            return True
        else:
            return body

    def has_direct_display(self):
        return False

    def set_theme(self,theme):
        if theme:
            self.theme.update(theme)

    def get_theme(self):
        return self.theme

    #This class hold an internal representation of the HTML text
    class representation:
        def __init__(self,width,title=None,center=True,theme={}):
            self.title=title
            self.center = center
            self.final_text = ""
            self.opened = []
            self.width = width
            self.last_line = ""
            self.last_line_colors = {}
            self.last_line_center = False
            self.new_paragraph = True
            self.i_indent = ""
            self.s_indent = ""
            self.r_indent = ""
            self.current_indent = ""
            self.disabled_indents = None
            # each color is an [open,close] pair code
            self.theme = theme
            self.colors = offthemes.colors

        def _insert(self,color,open=True):
            if open: o = 0
            else: o = 1
            pos = len(self.last_line)
            #we remember the position where to insert color codes
            if not pos in self.last_line_colors:
                self.last_line_colors[pos] = []
            #Two inverse code cancel each other
            if [color,int(not o)] in self.last_line_colors[pos]:
                self.last_line_colors[pos].remove([color,int(not o)])
            else:
                self.last_line_colors[pos].append([color,o])#+color+str(o))

        # Take self.last line and add ANSI codes to it before adding it to
        # self.final_text.
        def _endline(self):
            if len(self.last_line.strip()) > 0:
                for c in self.opened:
                    self._insert(c,open=False)
                nextline = ""
                added_char = 0
                #we insert the color code at the saved positions
                while len (self.last_line_colors) > 0:
                    pos,colors = self.last_line_colors.popitem()
                    #popitem itterates LIFO.
                    #So we go, backward, to the pos (starting at the end of last_line)
                    nextline = self.last_line[pos:] + nextline
                    ansicol = "\x1b["
                    for c,o in colors:
                        ansicol += self.colors[c][o] + ";"
                    ansicol = ansicol[:-1]+"m"
                    nextline = ansicol + nextline
                    added_char += len(ansicol)
                    self.last_line = self.last_line[:pos]
                nextline = self.last_line + nextline
                if self.last_line_center:
                    #we have to care about the ansi char while centering
                    width = term_width() + added_char
                    nextline = nextline.strip().center(width)
                    self.last_line_center = False
                else:
                    #should we lstrip the nextline in the addition ?
                    nextline = self.current_indent + nextline.lstrip() + self.r_indent
                    self.current_indent = self.s_indent
                self.final_text += nextline
                self.last_line = ""
                self.final_text += "\n"
                for c in self.opened:
                    self._insert(c,open=True)
            else:
                self.last_line = ""


        def center_line(self):
            self.last_line_center = True

        def open_theme(self,element):
            if element in self.theme:
                colors = self.theme[element]
                for c in colors:
                    self.open_color(c)
                return True
            else:
                return False
        def close_theme(self,element):
            if element in self.theme:
                colors = self.theme[element]
                for c in colors:
                    self.close_color(c)
        def open_color(self,color):
            if color in self.colors and color not in self.opened:
                self._insert(color,open=True)
                self.opened.append(color)
        def close_color(self,color):
            if color in self.colors and color in self.opened:
                self._insert(color,open=False)
                self.opened.remove(color)
        def close_all(self):
            if len(self.colors) > 0:
                self.last_line += "\x1b[0m"
                self.opened.clear()

        def startindent(self,indent,sub=None,reverse=None):
            self._endline()
            self.i_indent = indent
            self.current_indent = indent
            if sub:
                self.s_indent = sub
            else:
                self.s_indent = indent
            if reverse:
                self.r_indent = reverse
            else:
                self.r_indent = ""


        def endindent(self):
            self._endline()
            self.i_indent = ""
            self.s_indent = ""
            self.r_indent = ""
            self.current_indent = ""

        def _disable_indents(self):
            self.disabled_indents = []
            self.disabled_indents.append(self.current_indent)
            self.disabled_indents.append(self.i_indent)
            self.disabled_indents.append(self.s_indent)
            self.disabled_indents.append(self.r_indent)
            self.endindent()

        def _enable_indents(self):
            if self.disabled_indents:
                self.current_indent = self.disabled_indents[0]
                self.i_indent = self.disabled_indents[1]
                self.s_indent = self.disabled_indents[2]
                self.r_indent = self.disabled_indents[3]
            self.disabled_indents = None

        def newline(self):
            self._endline()

        #A new paragraph implies 2 newlines (1 blank line between paragraphs)
        #But it is only used if didn’t already started one to avoid plenty
        #of blank lines. force=True allows to bypass that limit.
        #new_paragraph becomes false as soon as text is entered into it
        def newparagraph(self,force=False):
            if force or not self.new_paragraph:
                self._endline()
                self.final_text += "\n"
                self.new_paragraph = True

        def add_space(self):
            if len(self.last_line) > 0 and self.last_line[-1] != " ":
                self.last_line += " "

        def _title_first(self,intext=None):
            if self.title:
                if not self.title == intext:
                    self._disable_indents()
                    self.open_theme("title")
                    self.add_text(self.title)
                    self.close_all()
                    self.newparagraph()
                    self._enable_indents()
                self.title = None

        # Beware, blocks are not wrapped nor indented and left untouched!
        # They are mostly useful for pictures and preformatted text.
        def add_block(self,intext,theme=None):
            # If necessary, we add the title before a block
            self._title_first()
            # we don’t want to indent blocks
            self._endline()
            self._disable_indents()
            #we have to apply the theme for every line in the intext
            #applying theme to preformatted is controversial as it could change it
            if theme:
                block = ""
                lines = intext.split("\n")
                for l in lines:
                    self.open_theme(theme)
                    self.last_line += self.current_indent + l
                    self.close_theme(theme)
                    self._endline()
                self.last_line += "\n"
            #one thing is sure : we need to keep unthemed blocks for images!
            else:
                self.final_text += self.current_indent + intext
                self.new_paragraph = False
                self._endline()
            self._enable_indents()

        def add_text(self,intext):
            self._title_first(intext=intext)
            lines = []
            last = (self.last_line + intext)
            self.last_line = ""
            # With the following, we basically cancel adding only spaces
            # on an empty line
            if len(last.strip()) > 0:
                self.new_paragraph = False
            else:
                last = last.strip()
            if len(last) > self.width:
                width = self.width - len(self.current_indent) - len(self.r_indent)
                spaces_left = len(last) - len(last.lstrip())
                spaces_right = len(last) - len(last.rstrip())
                lines = textwrap.wrap(last,width,drop_whitespace=True)
                self.last_line += spaces_left*" "
                while len(lines) > 1:
                    l = lines.pop(0)
                    self.last_line += l
                    self._endline()
                if len(lines) == 1:
                    li = lines[0]
                    self.last_line += li + spaces_right*" "
            else:
                self.last_line = last

        def get_final(self):
            self.close_all()
            self._endline()
            #if no content, we still add the title
            self._title_first()
            lines = self.final_text.splitlines()
            lines2 = []
            termspace = shutil.get_terminal_size()[0]
            #Following code instert blanck spaces to center the content
            if self.center and termspace > term_width():
                margin = int((termspace - term_width())//2)
            else:
                margin = 0
            for l in lines :
                lines2.append(margin*" "+l)
            return "\n".join(lines2)

    def get_subscribe_links(self):
        return [[self.url,self.get_mime(),self.get_title()]]
    def is_valid(self):
        return self.validity
    def set_mode(self,mode):
        self.last_mode = mode
    def get_mode(self):
        return self.last_mode
    def get_link(self,nb):
        links = self.get_links()
        if len(links) < nb:
            print("Index too high! No link %s for %s" %(nb,self.url))
            return None
        else:
            return links[nb-1]

    #get_title is about the "content title", so the title in the page itself
    def get_title(self):
        return "Abstract title"

    def get_page_title(self):
        title = self.get_title()
        if not title or len(title) == 0:
            title = self.get_url_title()
        else:
            title += " (%s)" %self.get_url_title()
        return title
    
    def get_formatted_title(self):
        title = self.get_url_title()
        nbr = len(self.get_links())
        if is_local(self.url):
            title += " (%s items)"%nbr
            str_last = "local file"
        else:
            str_last = "last accessed on %s"\
                            %time.ctime(netcache.cache_last_modified(self.url))
            title += " (%s links)"%nbr
        return self._window_title(title,info=str_last)

    #this function is about creating a title derived from the URL
    def get_url_title(self):
        #small intelligence to try to find a good name for a capsule
        #we try to find eithe ~username or /users/username
        #else we fallback to hostname
        if not self.url: return ""
        if is_local(self.url):
            splitpath = self.url.split("/")
            filename = splitpath[-1]
            return filename
        path = self.url
        parsed = urllib.parse.urlparse(self.url)
        red_title = parsed.hostname
        if "user" in path:
            i = 0
            splitted = path.split("/")
            while i < (len(splitted)-1):
                if splitted[i].startswith("user"):
                    red_title = splitted[i+1]
                i += 1
        if "~" in path:
            for pp in path.split("/"):
                if pp.startswith("~"):
                    red_title = pp[1:]
        return red_title

    # This function return a list of URL which should be downloaded
    # before displaying the page (images in HTML pages, typically)
    def get_images(self,mode=None):
        if not mode: mode = self.last_mode
        if not mode in self.images:
            self.get_body(mode=mode)
            # we also invalidate the body that was done without images
            self.rendered_text.pop(mode)
        if mode in self.images:
            return self.images[mode]
        else:
            return []
    #This function will give gemtext to the gemtext renderer
    def prepare(self,body,mode=None):
        return [[body,None]]

    def _build_body_and_links(self,mode,width=None):
        if not width:
            width = term_width()
        prepared_bodies = self.prepare(self.body,mode=mode)
        self.rendered_text[mode] = ""
        self.links[mode] = []
        for b in prepared_bodies:
            results = None
            size = len(self.links[mode])
            if b[1] in _FORMAT_RENDERERS:
                r = _FORMAT_RENDERERS[b[1]](b[0],self.url,center=self.center)
                results = r.render(b[0],width=width,mode=mode,startlinks=size)
            else:
                results = self.render(b[0],width=width,mode=mode,startlinks=size)
            if results:
                self.rendered_text[mode] += results[0] + "\n"
                #we should absolutize all URLs here
                for l in results[1]:
                    ll = l.split()[0]
                    try:
                        abs_l = urllib.parse.urljoin(self.url,ll)
                        self.links[mode].append(abs_l) 
                    except Exception as err:
                        print("Urljoin Error: Could not make an URL out of %s and %s"%(self.url,ll))
                for l in self.get_subscribe_links()[1:]:
                    self.links[mode].append(l[0])

    def get_body(self,width=None,mode=None):
        if not mode: mode = self.last_mode
        if mode not in self.rendered_text:
            self._build_body_and_links(mode,width)
        return self.rendered_text[mode]
    def get_links(self,mode=None):
        if not mode: mode = self.last_mode
        if mode not in self.links :
            self._build_body_and_links(mode)
        return self.links[mode]

    def _window_title(self,title,info=None):
        title_r = self.representation(term_width(),theme=self.theme)
        title_r.open_theme("window_title")
        title_r.add_text(title)
        title_r.close_theme("window_title")
        if info:
            title_r.open_theme("window_subtitle")
            title_r.add_text("   (%s)"%info)
            title_r.close_theme("window_subtitle")
        return title_r.get_final()

    # An instance of AbstractRenderer should have a self.render(body,width,mode) method.
    # 3 modes are used : readable (by default), full and links_only (the fastest, when
    # rendered content is not used, only the links are needed)
    # The prepare() function is called before the rendering. It is useful if
    # your renderer output in a format suitable for another existing renderer (such as gemtext)
    # The prepare() function output a list of tuple. Each tuple is [output text, format] where
    # format should be in _FORMAT_RENDERERS. If None, current renderer is used

class PlaintextRenderer(AbstractRenderer):
    def get_mime(self):
        return "text/plain"
    def get_title(self):
        if self.title:
            return self.title
        elif self.body:
            lines = self.body.splitlines()
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
        else:
            return "(unknown)"
    def render(self,gemtext, width=None,mode=None,startlinks=0):
        return gemtext, []

# Gemtext Rendering Engine
class GemtextRenderer(AbstractRenderer):
    def get_mime(self):
        return "text/gemini"
    def get_title(self):
        if self.title:
            return self.title
        elif self.body:
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
        else:
            return "(unknown)"

    #render_gemtext
    def render(self,gemtext, width=None,mode=None,startlinks=0):
        if not width:
            width = term_width()
        r = self.representation(width,theme=self.theme)
        links = []
        hidden_links = []
        preformatted = False
        def format_link(url,index,name=None):
            if "://" in url:
                protocol,adress = url.split("://",maxsplit=1)
                protocol = " %s" %protocol
            else:
                adress = url
                protocol = ""
            if "gemini" in protocol or "list" in protocol:
                protocol = ""
            if not name:
                name = adress
            line = "[%d%s] %s" % (index, protocol, name)
            return line
        for line in gemtext.splitlines():
            r.newline()
            if line.startswith("```"):
                preformatted = not preformatted
                if preformatted:
                    r.open_theme("preformatted")
                else:
                    r.close_theme("preformatted")
            elif preformatted:
                # infinite line to not wrap preformated
                r.add_block(line+"\n",theme="preformatted")
            elif len(line.strip()) == 0:
                r.newparagraph(force=True)
            elif line.startswith("=>"):
                strippedline = line[2:].strip()
                if strippedline:
                    links.append(strippedline)
                    splitted = strippedline.split(maxsplit=1)
                    url = splitted[0]
                    name = None
                    if len(splitted) > 1:
                        name = splitted[1]
                    link = format_link(url,len(links)+startlinks,name=name)
                    # If the link point to a page that has been cached less than
                    # 600 seconds after this page, we consider it as a new_link
                    current_modif = netcache.cache_last_modified(self.url)
                    link_modif = netcache.cache_last_modified(url)
                    if current_modif and link_modif and current_modif - link_modif < 600 and\
                                r.open_theme("new_link"):
                        theme = "new_link"
                    elif r.open_theme("oneline_link"):
                        theme = "oneline_link"
                    else:
                        theme = "link"
                        r.open_theme("link")
                    startpos = link.find("] ") + 2
                    r.startindent("",sub=startpos*" ")
                    r.add_text(link)
                    r.close_theme(theme)
                    r.endindent()
            elif line.startswith("* "):
                line = line[1:].lstrip("\t ")
                r.startindent("• ",sub="  ")
                r.add_text(line)
                r.endindent()
            elif line.startswith(">"):
                line = line[1:].lstrip("\t ")
                r.startindent("> ")
                r.open_theme("blockquote")
                r.add_text(line)
                r.close_theme("blockquote")
                r.endindent()
            elif line.startswith("###"):
                line = line[3:].lstrip("\t ")
                if r.open_theme("subsubtitle"):
                    theme = "subsubtitle"
                else:
                    r.open_theme("subtitle")
                    theme = "subtitle"
                r.add_text(line)
                r.close_theme(theme)
            elif line.startswith("##"):
                line = line[2:].lstrip("\t ")
                r.open_theme("subtitle")
                r.add_text(line)
                r.close_theme("subtitle")
            elif line.startswith("#"):
                line = line[1:].lstrip("\t ")
                if not self.title:
                    self.title = line
                r.open_theme("title")
                r.add_text(line)
                r.close_theme("title")
            else:
                if "://" in line:
                    words = line.split()
                    for w in words:
                        if "://" in w and looks_like_url(w):
                            hidden_links.append(w)
                r.add_text(line.rstrip())
        links += hidden_links
        return r.get_final(), links

class EmptyRenderer(GemtextRenderer):
    def get_mime(self):
        return "text/empty"
    def prepare(self,body,mode=None):
        text= "(empty file)"
        return [[text, "GemtextRenderer"]]

class GopherRenderer(AbstractRenderer):
    def get_mime(self):
        return "text/gopher"
    def get_title(self):
        if not self.title:
            self.title = ""
            if self.body:
                firstline = self.body.splitlines()[0]
                firstline = firstline.split("\t")[0]
                if firstline.startswith("i"):
                    firstline = firstline[1:]
                self.title = firstline
        return self.title

    #menu_or_text
    def render(self,body,width=None,mode=None,startlinks=0):
        if not width:
            width = term_width()
        try:
            render,links = self._render_goph(body,width=width,mode=mode,startlinks=startlinks)
        except Exception as err:
            print("Error rendering Gopher ",err)
            r = self.representation(width,theme=self.theme)
            r.add_block(body)
            render = r.get_final()
            links = []
        return render,links

    def _render_goph(self,body,width=None,mode=None,startlinks=0):
        if not width:
            width = term_width()
        # This was copied straight from Agena (then later adapted)
        links = []
        r = self.representation(width,theme=self.theme)
        for line in self.body.split("\n"):
            r.newline()
            if line.startswith("i"):
                towrap = line[1:].split("\t")[0]
                if len(towrap.strip()) > 0:
                    r.add_text(towrap)
                else:
                    r.newparagraph()
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
                    url = url.replace(" ","%20")
                    linkline = url + " " + name
                    links.append(linkline)
                    number = len(links) + startlinks
                    towrap = "[%s] "%str(number)+ name
                    r.add_text(towrap)
                else:
                    r.add_text(line)
        return r.get_final(),links


class FolderRenderer(GemtextRenderer):
    #it was initialized with:
    #self.renderer = FolderRenderer("",self.get_cache_path(),datadir=xdg("data"))
    def __init__(self,content,url,center=True,datadir=None):
        GemtextRenderer.__init__(self,content,url,center)
        self.datadir = datadir

    def get_mime(self):
        return "Directory"
    def prepare(self,body,mode=None):
        def get_first_line(l):
            path = os.path.join(listdir,l+".gmi")
            with open(path) as f:
                first_line = f.readline().strip()
                f.close()
            if first_line.startswith("#"):
                return first_line
            else:
                return None
        def write_list(l):
            body = ""
            for li in l:
                path = "list:///%s"%li
                r = renderer_from_file(netcache.get_cache_path(path))
                size = len(r.get_links())
                body += "=> %s %s (%s items)\n" %(str(path),li,size)
            return body
        listdir = os.path.join(self.datadir,"lists")
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
            frozen = []
            lists.sort()
            for l in lists:
                if l in ["history","to_fetch","archives","tour"]:
                    system_lists.append(l)
                else:
                    first_line = get_first_line(l)
                    if first_line and "#subscribed" in first_line:
                        subscriptions.append(l)
                    elif first_line and "#frozen" in first_line:
                        frozen.append(l)
                    else:
                        my_lists.append(l)
            if len(my_lists) > 0:
                body+= "\n## Bookmarks Lists (updated during sync)\n"
                body += write_list(my_lists)
            if len(subscriptions) > 0:
                body +="\n## Subscriptions (new links in those are added to tour)\n"
                body += write_list(subscriptions)
            if len(frozen) > 0:
                body +="\n## Frozen (fetched but never updated)\n"
                body += write_list(frozen)
            if len(system_lists) > 0:
                body +="\n## System Lists\n"
                body += write_list(system_lists)
            return [[body,None]]

class FeedRenderer(GemtextRenderer):
    def get_mime(self):
        return "application/rss+xml"
    def is_valid(self):
        if _DO_FEED:
            try:
                parsed = feedparser.parse(self.body)
            except:
                parsed = False
        else:
            return False
        if not parsed:
            return False
        elif parsed.bozo:
            return False
        else:
            #If no content, then fallback to HTML
            return len(parsed.entries) > 0

    def get_title(self):
        if not self.title:
            self.get_body()
        return self.title

    def prepare(self,content,mode=None,width=None):
        if not mode: mode = self.last_mode
        if not width:
            width = term_width()
        self.title = "RSS/Atom feed"
        toreturn = []
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
            toreturn.append([page,None])
            if len(parsed.entries) < 1:
                self.validity = False
            postslist = ""
            for i in parsed.entries:
                if "link" in i:
                    line = "=> %s " %i.link
                elif "links" in i and len(i.links) > 0:
                    link = None
                    j = 0
                    while not link and j < len(i.links):
                        link = i.links[j].href
                    if link:
                        line = "=> %s "%link
                    else:
                        line = "* "
                else:
                    line = "* "
                if "published" in i:
                    #sometimes fails so protect it
                    try:
                        pub_date = time.strftime("%Y-%m-%d",i.published_parsed)
                        line += pub_date + " : "
                    except:
                        pass
                if "title" in i:
                    line += "%s" %(i.title)
                if "author" in i:
                    line += " (by %s)"%i.author
                if mode == "full":
                    toreturn.append([line,None])
                    if "summary" in i:
                        toreturn.append([i.summary,"text/html"])
                        toreturn.append(["------------",None])
                else:
                    postslist += line + "\n"
            #If each posts is append to toreturn, a \n is inserted
            #between each item of the list. I don’t like it. Hence this hack
            if mode != "full":
                toreturn.append([postslist,None])
        return toreturn

class ImageRenderer(AbstractRenderer):
    def get_mime(self):
        return "image/*"
    def is_valid(self):
        if _RENDER_IMAGE:
            return True
        else:
            return False
    def get_links(self,mode=None):
        return []
    def get_title(self):
        return "Picture file"
    def render(self,img,width=None,mode=None,startlinks=0):
        #with inline, we use symbols to be rendered with less.
        #else we use the best possible renderer.
        if mode in ["full_links_only","links_only"]:
            return "", []
        if not width:
            width = term_width()
            spaces = 0
        else:
            spaces = int((term_width() - width)//2)
        ansi_img = inline_image(img,width)
        #Now centering the image
        lines = ansi_img.splitlines()
        new_img = ""
        for l in lines:
            new_img += spaces*" " + l + "\n"
        return new_img, []

    def has_direct_display(self):
        return _RENDER_IMAGE

    def display(self,mode=None,directdisplay=False):
        wtitle = self.get_formatted_title()
        if not directdisplay:
            body = wtitle + "\n" + self.get_body(mode=mode)
            return body
        else:
            print(self._window_title(wtitle))
            terminal_image(self.body)
            return True

class HtmlRenderer(AbstractRenderer):
    def get_mime(self):
        return "text/html"
    def is_valid(self):
        if not _DO_HTML:
            print("HTML document detected. Please install python-bs4 and python-readability.")
        return _DO_HTML and self.validity
    def get_subscribe_links(self):
        subs = [[self.url,self.get_mime(),self.get_title()]]
        soup = BeautifulSoup(self.body, 'html.parser')
        links = soup.find_all("link",rel="alternate",recursive=True)
        for l in links:
            ty = l.get("type")
            if ty :
                if "rss" in ty or "atom" in ty or "feed" in ty:
                    # some rss links are relatives: we absolutise_url
                    sublink = urllib.parse.urljoin(self.url, l.get("href"))
                    subs.append([sublink,ty,l.get("title")])
        return subs

    def get_title(self):
        if self.title:
            return self.title
        elif self.body:
            if _HAS_READABILITY:
                try:
                    readable = Document(self.body)
                    self.title = readable.short_title()
                    return self.title
                except Exception as err:
                    pass
            soup = BeautifulSoup(self.body,"html.parser")
            if soup.title:
                self.title = str(soup.title.string)
            else:
                self.title = ""
            return self.title
        else:
            return ""

    # Our own HTML engine (crazy, isn’t it?)
    # Return [rendered_body, list_of_links]
    # mode is either links_only, readable or full
    def render(self,body,mode=None,width=None,add_title=True,startlinks=0):
        if not mode: mode = self.last_mode
        if not width:
            width = term_width()
        if not _DO_HTML:
            print("HTML document detected. Please install python-bs4 and python-readability.")
            return
        # This method recursively parse the HTML
        r = self.representation(width,title=self.get_title(),center=self.center,theme=self.theme)
        links = []
        # You know how bad html is when you realize that space sometimes meaningful, somtimes not.
        # CR are not meaniningful. Except that, somethimes, they should be interpreted as spaces.
        # HTML is real crap. At least the one people are generating.

        def render_image(src,width=40,mode=None):
            ansi_img = ""
            imgurl,imgdata = looks_like_base64(src,self.url)
            if _RENDER_IMAGE and mode not in ["full_links_only","links_only"] and imgurl:
                try:
                    #4 followings line are there to translate the URL into cache path
                    img = netcache.get_cache_path(imgurl)
                    if imgdata:
                        os.makedirs(os.path.dirname(img), exist_ok=True)
                        with open(img,"wb") as cached:
                            cached.write(base64.b64decode(imgdata))
                            cached.close()
                    if netcache.is_cache_valid(img):
                        renderer = ImageRenderer(img,imgurl)
                        # Image are 40px wide except if terminal is smaller
                        if width > 40:
                            size = 40
                        else:
                            size = width
                        ansi_img = "\n" + renderer.get_body(width=size,mode="inline")
                except Exception as err:
                    #we sometimes encounter really bad formatted files or URL
                    ansi_img = textwrap.fill("[BAD IMG] %s - %s"%(err,src),width) + "\n"
            return ansi_img
        def sanitize_string(string):
            #never start with a "\n"
            #string = string.lstrip("\n")
            string = string.replace("\r","").replace("\n", " ").replace("\t"," ")
            endspace = string.endswith(" ") or string.endswith("\xa0")
            startspace = string.startswith(" ") or string.startswith("\xa0")
            toreturn = string.replace("\n", " ").replace("\t"," ").strip()
            while "  " in toreturn:
                toreturn = toreturn.replace("  "," ")
            toreturn = html.unescape(toreturn)
            if endspace and not toreturn.endswith(" ") and not toreturn.endswith("\xa0"):
                toreturn += " "
            if startspace and not toreturn.startswith(" ") and not toreturn.startswith("\xa0"):
                toreturn = " " + toreturn
            return toreturn
        def recursive_render(element,indent="",preformatted=False):
            if element.name in ["blockquote", "dd"]:
                r.newparagraph()
                r.startindent("   ",reverse="     ")
                for child in element.children:
                    r.open_theme("blockquote")
                    recursive_render(child,indent="\t")
                    r.close_theme("blockquote")
                r.endindent()
            elif element.name in ["div","p","dt"]:
                r.newparagraph()
                for child in element.children:
                    recursive_render(child,indent=indent)
                r.newparagraph()
            elif element.name in ["span"]:
                r.add_space()
                for child in element.children:
                    recursive_render(child,indent=indent)
                r.add_space()
            elif element.name in ["h1","h2","h3","h4","h5","h6"]:
                if element.name in ["h1"]:
                    r.open_theme("title")
                elif element.name in ["h2","h3"]:
                    r.open_theme("subtitle")
                elif element.name in ["h4","h5","h6"]:
                    if not r.open_theme("subsubtitle"):
                        r.open_theme("subtitle")
                r.newparagraph()
                for child in element.children:
                    recursive_render(child)
                    #r.close_all()
                r.close_all()
                r.newparagraph()
            elif element.name in ["code","tt"]:
                for child in element.children:
                   recursive_render(child,indent=indent,preformatted=True)
            elif element.name in ["pre"]:
                r.newparagraph()
                r.add_block(element.text,theme="preformatted")
                r.newparagraph(force=True)
            elif element.name in ["li"]:
                r.startindent(" • ",sub="   ")
                for child in element.children:
                    recursive_render(child,indent=indent)
                r.endindent()
            elif element.name in ["tr"]:
                r.startindent("|",reverse="|")
                for child in element.children:
                    recursive_render(child,indent=indent)
                r.endindent()
            elif element.name in ["td","th"]:
                r.add_text("| ")
                for child in element.children:
                    recursive_render(child)
                r.add_text(" |")
            # italics
            elif element.name in ["em","i"]:
                r.open_color("italic")
                for child in element.children:
                    recursive_render(child,indent=indent,preformatted=preformatted)
                r.close_color("italic")
            #bold
            elif element.name in ["b","strong"]:
                r.open_color("bold")
                for child in element.children:
                    recursive_render(child,indent=indent,preformatted=preformatted)
                r.close_color("bold")
            elif element.name == "a":
                link = element.get('href')
                # support for images nested in links
                if link:
                    text = ""
                    imgtext = ""
                    #we display images first in a link
                    for child in element.children:
                        if child.name == "img":
                            recursive_render(child)
                            imgtext = "[IMG LINK %s]"
                    links.append(link+" "+text)
                    link_id = str(len(links)+startlinks)
                    r.open_theme("link")
                    for child in element.children:
                        if child.name != "img":
                            recursive_render(child,preformatted=preformatted)
                    if imgtext != "":
                        r.center_line()
                        r.add_text(imgtext%link_id)
                    else:
                        r.add_text(" [%s]"%link_id)
                    r.close_theme("link")
                else:
                    #No real link found
                    for child in element.children:
                        recursive_render(child,preformatted=preformatted)
            elif element.name == "img":
                src = element.get("src")
                text = ""
                ansi_img = render_image(src,width=width,mode=mode)
                alt = element.get("alt")
                if alt:
                    alt = sanitize_string(alt)
                    text += "[IMG] %s"%alt
                else:
                    text += "[IMG]"
                if src:
                    if not mode in self.images:
                        self.images[mode] = []
                    abs_url,data = looks_like_base64(src,self.url)
                    #if abs_url is None, it means we don’t support
                    #the image (such as svg+xml). So we hide it.
                    if abs_url:
                        links.append(abs_url+" "+text)
                        self.images[mode].append(abs_url)
                        link_id = " [%s]"%(len(links)+startlinks)
                        r.add_block(ansi_img)
                        r.open_theme("image_link")
                        r.center_line()
                        r.add_text(text + link_id)
                        r.close_theme("image_link")
                        r.newline()

            elif element.name == "video":
                poster = element.get("poster")
                src = element.get("src")
                for child in element.children:
                    if not src:
                        if child.name == "source":
                            src = child.get("src")
                text = ""
                if poster:
                    ansi_img = render_image(poster,width=width,mode=mode)
                alt = element.get("alt")
                if alt:
                    alt = sanitize_string(alt)
                    text += "[VIDEO] %s"%alt
                else:
                    text += "[VIDEO]"

                if poster:
                    if not mode in self.images:
                        self.images[mode] = []
                    poster_url,d = looks_like_base64(poster,self.url)
                    if poster_url:
                        vid_url,d2 = looks_like_base64(src,self.url)
                        self.images[mode].append(poster_url)
                        r.add_block(ansi_img)
                        r.open_theme("image_link")
                        r.center_line()
                        if vid_url and src:
                            links.append(vid_url+" "+text)
                            link_id = " [%s]"%(len(links)+startlinks)
                            r.add_text(text + link_id)
                        else:
                            r.add_text(text)
                        r.close_theme("image_link")
                        r.newline()
                elif src:
                    vid_url,d = looks_like_base64(src,self.url)
                    links.append(vid_url+" "+text)
                    link_id = " [%s]"%(len(links)+startlinks)
                    r.open_theme("image_link")
                    r.center_line()
                    r.add_text(text + link_id)
                    r.close_theme("image_link")
                    r.newline()

            elif element.name == "br":
                r.newline()
            elif element.name not in ["script","style","template"] and type(element) != Comment:
                if element.string:
                    if preformatted :
                        r.open_theme("preformatted")
                        r.add_text(element.string)
                        r.close_theme("preformatted")
                    else:
                        s = sanitize_string(element.string)
                        if len(s.strip()) > 0:
                            r.add_text(s)
                else:
                    for child in element.children:
                        recursive_render(child,indent=indent)
        # the real render_html hearth
        if mode in ["full","full_links_only"]:
            summary = body
        elif _HAS_READABILITY:
            try:
                readable = Document(body)
                summary = readable.summary()
            except Exception as err:
                summary = body
        else:
            summary = body
        soup = BeautifulSoup(summary, 'html.parser')
        #soup = BeautifulSoup(summary, 'html5lib')
        if soup :
            if soup.body :
                recursive_render(soup.body)
            else:
                recursive_render(soup)
        return r.get_final(),links


# Mapping mimetypes with renderers
# (any content with a mimetype text/* not listed here will be rendered with as GemText)
_FORMAT_RENDERERS = {
    "text/gemini":  GemtextRenderer,
    "text/html" :   HtmlRenderer,
    "text/xml" : FeedRenderer,
    "text/plain" : PlaintextRenderer,
    "application/xml" : FeedRenderer,
    "application/rss+xml" : FeedRenderer,
    "application/atom+xml" : FeedRenderer,
    "text/gopher": GopherRenderer,
    "image/*": ImageRenderer,
    "application/javascript": HtmlRenderer,
    "application/json": HtmlRenderer,
    "text/empty": EmptyRenderer,
}
def get_mime(path,url=None):
    #Beware, this one is really a shaddy ad-hoc function
    if not path:
        return None
    #If the file is empty, simply returns it
    elif os.path.exists(path) and os.stat(path).st_size == 0:
        return "text/empty"
    elif url and url.startswith("gopher://"):
        #special case for gopher
        #code copy/pasted from netcache
        parsed = urllib.parse.urlparse(url)
        if len(parsed.path) >= 2:
            itemtype = parsed.path[1]
            path = parsed.path[2:]
        else:
            itemtype = "1"
            path = ""
        if itemtype == "0":
            mime = "text/gemini"
        elif itemtype == "1":
            mime = "text/gopher"
        elif itemtype == "h":
            mime = "text/html"
        elif itemtype in ("9","g","I","s",";"):
            mime = "binary"
        else:
            mime = "text/gopher"
    elif path.startswith("mailto:"):
        mime = "mailto"
    elif os.path.isdir(path):
        mime = "Local Folder"
    elif path.endswith(".gmi"):
        mime = "text/gemini"
    elif path.endswith("gophermap"):
        mime = "text/gopher"
    elif shutil.which("file") :
        mime = run("file -b --mime-type %s", parameter=path).strip()
        mime2,encoding = mimetypes.guess_type(path,strict=False)
        #If we hesitate between html and xml, takes the xml one
        #because the FeedRendered fallback to HtmlRenderer
        if mime2 and mime != mime2 and "html" in mime and "xml" in mime2:
            mime = "text/xml"
        # If it’s a xml file, consider it as such, regardless of what file thinks
        elif path.endswith(".xml"):
            mime = "text/xml"
        # If it doesn’t end with .svg, it is probably an xml, not a SVG file
        elif "svg" in mime and not path.endswith(".svg"):
            mime = "text/xml"
        #Some xml/html document are considered as octet-stream
        if mime == "application/octet-stream":
            mime = "text/xml"
    else:
        mime,encoding = mimetypes.guess_type(path,strict=False)
    #gmi Mimetype is not recognized yet
    if not mime and not shutil.which("file") :
        print("Cannot guess the mime type of the file. Please install \"file\".")
    if mime.startswith("text") and mime not in _FORMAT_RENDERERS:
        if mime2 and mime2 in _FORMAT_RENDERERS:
            mime = mime2
        else:
            #by default, we consider it’s gemini except for html
            mime = "text/gemini"
    #file doesn’t recognise gemtext. It should be the default renderer.
    #the only case were it doesn’t make sense is if the file is .txt
    if mime == "text/plain" and not path.endswith(".txt"):
        mime = "text/gemini"
    return mime

def renderer_from_file(path,url=None,theme=None):
    if not path:
        return None
    mime = get_mime(path,url=url)
    if not url:
        url = path
    if os.path.exists(path):
        if mime.startswith("text/") or mime in _FORMAT_RENDERERS:
            with open(path,errors="ignore") as f:
                content = f.read()
                f.close()
        else:
            content = path
        toreturn = set_renderer(content,url,mime,theme=theme)
    else:
        toreturn = None
    return toreturn

def set_renderer(content,url,mime,theme=None):
    renderer = None
    if mime == "Local Folder":
        renderer = FolderRenderer("",url,datadir=xdg("data"))
        if theme:
            renderer.set_theme(theme)
        return renderer
    mime_to_use = []
    for m in _FORMAT_RENDERERS:
        if fnmatch.fnmatch(mime, m):
            mime_to_use.append(m)
    if len(mime_to_use) > 0:
        current_mime = mime_to_use[0]
        func = _FORMAT_RENDERERS[current_mime]
        if current_mime.startswith("text"):
            renderer = func(content,url)
            # We double check if the renderer is correct.
            # If not, we fallback to html
            # (this is currently only for XHTML, often being
            # mislabelled as xml thus RSS feeds)
            if not renderer.is_valid():
                func = _FORMAT_RENDERERS["text/html"]
                #print("Set (fallback)RENDERER to html instead of %s"%mime)
                renderer = func(content,url)
        else:
            #TODO: check this code and then remove one if.
            #we don’t parse text, we give the file to the renderer
            renderer = func(content,url)
            if not renderer.is_valid():
                renderer = None
    if renderer and theme:
        renderer.set_theme(theme)
    return renderer

def render(input,path=None,format="auto",mime=None,url=None,mode=None):
    if not url: url = ""
    else: url=url[0]
    if format == "gemtext":
        r = GemtextRenderer(input,url)
    elif format == "html":
        r = HtmlRenderer(input,url)
    elif format == "feed":
        r = FeedRenderer(input,url)
    elif format == "gopher":
        r = GopherRenderer(input,url)
    elif format == "image":
        r = ImageRenderer(input,url)
    elif format == "folder":
        r = FolderRenderer(input,url)
    elif format in ["plaintext","text"]:
        r = PlaintextRenderer(input,url)
    else:
        if not mime and path:
            r= renderer_from_file(path,url)
        else:
            r = set_renderer(input,url,mime)
    if r:
        r.display(directdisplay=True,mode=mode)
    else:
        print("Could not render %s"%input)


def main():
    descri = "ansicat is a terminal rendering tool that will render multiple formats (HTML, \
            Gemtext, RSS, Gophermap, Image) into ANSI text and colors.\n\
            When used on a file, ansicat will try to autodetect the format. When used with \
            standard input, the format must be manually specified.\n\
            If the content contains links, the original URL of the content can be specified \
            in order to correctly modify relatives links."
    parser = argparse.ArgumentParser(prog="ansicat",description=descri)
    parser.add_argument("--format", choices=["auto","gemtext","html","feed","gopher","image","folder","text","plaintext"],
                        help="Renderer to use. Available: auto, gemtext, html, feed, gopher, image, folder, plaintext")
    parser.add_argument("--mime", help="Mime of the content to parse")
    ## The argument needs to be a path to a file. If none, then stdin is used which allows
    ## to pipe text directly into ansirenderer
    parser.add_argument("--url",metavar="URL", nargs="*",
                        help="Original URL of the content")
    parser.add_argument("--mode", metavar="MODE",
                        help="Which mode should be used to render: normal (default), full or source.\
                                With HTML, the normal mode try to extract the article.")
    parser.add_argument("content",metavar="INPUT", nargs="*", type=argparse.FileType("r"), 
                         default=sys.stdin, help="Path to the text to render (default to stdin)")
    args = parser.parse_args()
    # Detect if we are running interactively or in a pipe
    if sys.stdin.isatty():
        #we are interactive, not in stdin, we can have multiple files as input
        if isinstance(args.content,list):
            for f in args.content:
                path = os.path.abspath(f.name)
                try:
                    content = f.read()
                except UnicodeDecodeError:
                    content = f
                render(content,path=path,format=args.format,url=args.url,mime=args.mime,mode=args.mode)
        else:
            print("Ansicat needs at least one file as an argument")
    else:
        #we are in stdin
        if not args.format and not args.mime:
            print("Format or mime should be specified when running with stdin")
        else:
            render(args.content.read(),path=None,format=args.format,url=args.url,mime=args.mime,mode=args.mode)

if __name__ == '__main__':
    main()
