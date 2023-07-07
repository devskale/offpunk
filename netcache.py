#!/bin/python
import os
import urllib.parse
import argparse
import requests

_home = os.path.expanduser('~')
cache_home = os.environ.get('XDG_CACHE_HOME') or\
                os.path.join(_home,'.cache')
#_CACHE_PATH = os.path.join(cache_home,"offpunk/")
#Debug:
_CACHE_PATH = "/home/ploum/dev/netcache/"

if not os.path.exists(_CACHE_PATH):
    print("Creating cache directory {}".format(_CACHE_PATH))
    os.makedirs(_CACHE_PATH)

# This list is also used as a list of supported protocols
standard_ports = {
        "gemini" : 1965,
        "gopher" : 70,
        "finger" : 79,
        "http"   : 80,
        "https"  : 443,
        "spartan": 300,
}
default_protocol = "gemini"

def parse_mime(mime):
    options = {}
    if mime:
        if ";" in mime:
            splited = mime.split(";",maxsplit=1)
            mime = splited[0]
            if len(splited) >= 1:
                options_list = splited[1].split()
                for o in options_list:
                    spl = o.split("=",maxsplit=1)
                    if len(spl) > 0:
                        options[spl[0]] = spl[1]
    return mime, options

def normalize_url(url):
    if "://" not in url and ("./" not in url and url[0] != "/"):
        if not url.startswith("mailto:"):
            url = "gemini://" + url
    return url


def cache_last_modified(url):
    path = get_cache_path(url)
    if path:
        return os.path.getmtime(path)
    elif self.local:
        return 0
    else:
        print("ERROR : NO CACHE in cache_last_modified")
        return None

def is_cache_valid(url,validity=0):
    # Validity is the acceptable time for
    # a cache to be valid  (in seconds)
    # If 0, then any cache is considered as valid
    # (use validity = 1 if you want to refresh everything)
    cache = get_cache_path(url)
    # TODO FIXME : detect if we are local
    #if self.local:
    #    return os.path.exists(cache)
    if cache :
        # If path is too long, we always return True to avoid
        # fetching it.
        if len(cache) > 259:
            print("We return False because path is too long")
            return False
        if os.path.exists(cache) and not os.path.isdir(cache):
            if validity > 0 :
                last_modification = cache_last_modified(url)
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



def get_cache_path(url):
    #First, we parse the URL
    parsed = urllib.parse.urlparse(url)
    if url[0] == "/" or url.startswith("./"):
        scheme = "file"
    elif parsed.scheme:
        scheme = parsed.scheme
    else:
        scheme = default_protocol
    if scheme in ["file","mailto","list"]:
        local = True
        host = ""
        port = None
        # file:// is 7 char
        if url.startswith("file://"):
            path = self.url[7:]
        elif scheme == "mailto":
            path = parsed.path
        elif url.startswith("list://"):
            listdir = os.path.join(_DATA_DIR,"lists")
            listname = url[7:].lstrip("/")
            if listname in [""]:
                name = "My Lists"
                path = listdir
            else:
                name = listname
                path = os.path.join(listdir, "%s.gmi"%listname)
        else:
            path = url
    else:
        local = False
        # Convert unicode hostname to punycode using idna RFC3490
        host = parsed.hostname #.encode("idna").decode()
        port = parsed.port or standard_ports.get(scheme, 0)
        # special gopher selector case
        if scheme == "gopher":
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
            elif itemtype in ("9","g","I","s"):
                mime = "binary"
            else:
                mime = "text/gopher"
        else:
            path = parsed.path
        if parsed.query:
            # we don’t add the query if path is too long because path above 260 char
            # are not supported and crash python.
            # Also, very long query are usually useless stuff
            if len(path+parsed.query) < 258:
                path += "/" + parsed.query

    # Now, we have a partial path. Let’s make it full path.
    if local:
        cache_path = path
    else:
        cache_path = os.path.expanduser(_CACHE_PATH + scheme + "/" + host + path)
        #There’s an OS limitation of 260 characters per path.
        #We will thus cut the path enough to add the index afterward
        cache_path = cache_path[:249]
        # FIXME : this is a gross hack to give a name to
        # index files. This will break if the index is not
        # index.gmi. I don’t know how to know the real name
        # of the file. But first, we need to ensure that the domain name
        # finish by "/". Else, the cache will create a file, not a folder.
        if scheme.startswith("http"):
            index = "index.html"
        elif scheme == "finger":
            index = "index.txt"
        elif scheme == "gopher":
            index = "gophermap"
        else:
            index = "index.gmi"
        if path == "" or os.path.isdir(cache_path):
            if not cache_path.endswith("/"):
                cache_path += "/"
            if not url.endswith("/"):
                url += "/"
        if cache_path.endswith("/"):
            cache_path += index
        #sometimes, the index itself is a dir
        #like when folder/index.gmi?param has been created
        #and we try to access folder
        if os.path.isdir(cache_path):
            cache_path += "/" + index
    return cache_path

def write_body(url,body,mime=None):
    ## body is a copy of the raw gemtext
    ## Write_body() also create the cache !
    # DEFAULT GEMINI MIME
    mime, options = parse_mime(mime)
    cache_path = get_cache_path(url)
    if cache_path:
        if mime and mime.startswith("text/"):
            mode = "w"
        else:
            mode = "wb"
        cache_dir = os.path.dirname(cache_path)
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
        with open(cache_path, mode=mode) as f:
            f.write(body)
            f.close()
        return cache_path

def _fetch_http(url,max_length=None):
    def set_error(item,length,max_length):
        err = "Size of %s is %s Mo\n"%(item.url,length)
        err += "Offpunk only download automatically content under %s Mo\n" %(max_length/1000000)
        err += "To retrieve this content anyway, type 'reload'."
        item.set_error(err)
        return item
    header = {}
    header["User-Agent"] = "Netcache"
    parsed = urllib.parse.urlparse(url)
    # Code to translate URLs to better frontends (think twitter.com -> nitter)
    #if options["redirects"]:
    #    netloc = parsed.netloc
    #   if netloc.startswith("www."):
#            netloc = netloc[4:]
#        if netloc in self.redirects:
#            if self.redirects[netloc] == "blocked":
#                text = "This website has been blocked.\n"
#                text += "Use the redirect command to unblock it."
#                gi.write_body(text,"text/gemini")
#                return gi
#            else:
#                parsed = parsed._replace(netloc = self.redirects[netloc])
    url = urllib.parse.urlunparse(parsed)
    with requests.get(url,headers=header, stream=True,timeout=5) as response:
        #print("This is header for %s"%gi.url)
        #print(response.headers)
        if "content-type" in response.headers:
            mime = response.headers['content-type']
        else:
            mime = None
        if "content-length" in response.headers:
            length = int(response.headers['content-length'])
        else:
            length = 0
        if max_length and length > max_length:
            response.close()
            return set_error(gi,str(length/1000000),max_length)
        elif max_length and length == 0:
            body = b''
            downloaded = 0
            for r in response.iter_content():
                body += r
                #We divide max_size for streamed content
                #in order to catch them faster
                size = sys.getsizeof(body)
                max = max_length/2
                current = round(size*100/max,1)
                if current > downloaded:
                    downloaded = current
                    print("  -> Receiving stream: %s%% of allowed data"%downloaded,end='\r')
                #print("size: %s (%s\% of maxlenght)"%(size,size/max_length))
                if size > max_length/2:
                    response.close()
                    return set_error(gi,"streaming",max_length)
            response.close()
        else:
            body = response.content
            response.close()
    if mime and "text/" in mime:
        body = body.decode("UTF-8","replace")
    cache = write_body(url,body,mime)
    return cache


def fetch(url):
    url = normalize_url(url)
    if "://" in url:
        scheme = url.split("://")[0]
        if scheme in ("http","https"):
            path=_fetch_http(url)
            print("Path = %s"%path)
        else:
            print("scheme %s not implemented yet")
    else:
        print("Not a supproted URL")


def main():
    
    # Parse arguments
    parser = argparse.ArgumentParser(description=__doc__)
    
    # No argument: write help
    parser.add_argument('url', metavar='URL', nargs='*',
                        help='download URL and returns the path to the cache of it')
    # arg = URL: download and returns cached URI
    # --cache-validity : do not download if cache is valid
    # --offline : do not attempt to download, return Null if no cached version
    # --validity : returns the date of the cached version, Null if no version
    # --force-download : download and replace cache, even if valid
    # --max-size-download : cancel download of items above that size. Returns Null.
    args = parser.parse_args()
    
    for u in args.url:
        print("Download URL: %s" %u)
        fetch(u)



if __name__== '__main__':
    main()
