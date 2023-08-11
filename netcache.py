#!/bin/python
import os
import sys
import urllib.parse
import argparse
import requests
import codecs
import getpass
import socket
import ssl
import glob
import datetime
import hashlib
import sqlite3
from ssl import CertificateError
import ansicat
import offutils
try:
    import chardet
    _HAS_CHARDET = True
except ModuleNotFoundError:
    _HAS_CHARDET = False

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    _HAS_CRYPTOGRAPHY = True
    _BACKEND = default_backend()
except ModuleNotFoundError:
    _HAS_CRYPTOGRAPHY = False

_home = os.path.expanduser('~')
cache_home = os.environ.get('XDG_CACHE_HOME') or\
                os.path.join(_home,'.cache')
#_CACHE_PATH = os.path.join(cache_home,"offpunk/")
#Debug (TODO: get path from offpunk):
_CACHE_PATH = "/home/ploum/dev/netcache/"
_DATA_DIR = "/home/ploum/dev/netcache/"
_CONFIG_DIR = "/home/ploum/dev/netcache/"
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

CRLF = '\r\n'
DEFAULT_TIMEOUT = 10
_MAX_REDIRECTS = 5

# monkey-patch Gemini support in urllib.parse
# see https://github.com/python/cpython/blob/master/Lib/urllib/parse.py
urllib.parse.uses_relative.append("gemini")
urllib.parse.uses_netloc.append("gemini")
urllib.parse.uses_relative.append("spartan")
urllib.parse.uses_netloc.append("spartan")


class UserAbortException(Exception):
    pass


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
    # Sometimes, cache_path became a folder! (which happens for index.html/index.gmi)
    # In that case, we need to reconstruct it
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
    if len(cache_path) > 259:
        print("Path is too long. This is an OS limitation.\n\n")
        print(url)
        return None
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


def set_error(url,err):
# If we get an error, we want to keep an existing cache
# but we need to touch it or to create an empty one
# to avoid hitting the error at each refresh
    cache = get_cache_path(url)
    if is_cache_valid(url):
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
                cache.write("ERROR while caching %s\n\n" %url)
                cache.write("*****\n\n")
                cache.write(str(type(err)) + " = " + str(err))
                #cache.write("\n" + str(err.with_traceback(None)))
                cache.write("\n*****\n\n")
                cache.write("If you believe this error was temporary, type ""reload"".\n")
                cache.write("The ressource will be tentatively fetched during next sync.\n")
                cache.close()
    return cache

def _fetch_http(url,max_size=None,timeout=DEFAULT_TIMEOUT,**kwargs):
    def too_large_error(url,length,max_size):
        err = "Size of %s is %s Mo\n"%(url,length)
        err += "Offpunk only download automatically content under %s Mo\n" %(max_size/1000000)
        err += "To retrieve this content anyway, type 'reload'."
        return set_error(url,err)
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
    with requests.get(url,headers=header, stream=True,timeout=DEFAULT_TIMEOUT) as response:
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
        if max_size and length > max_size:
            response.close()
            return too_large_error(url,str(length/100),max_size)
        elif max_size and length == 0:
            body = b''
            downloaded = 0
            for r in response.iter_content():
                body += r
                #We divide max_size for streamed content
                #in order to catch them faster
                size = sys.getsizeof(body)
                max = max_size/2
                current = round(size*100/max,1)
                if current > downloaded:
                    downloaded = current
                    print("  -> Receiving stream: %s%% of allowed data"%downloaded,end='\r')
                #print("size: %s (%s\% of maxlenght)"%(size,size/max_size))
                if size > max_size/2:
                    response.close()
                    return too_large_error(url,"streaming",max_size)
            response.close()
        else:
            body = response.content
            response.close()
    if mime and "text/" in mime:
        body = body.decode("UTF-8","replace")
    cache = write_body(url,body,mime)
    return cache

def _fetch_gopher(url,timeout=DEFAULT_TIMEOUT,**kwargs):
    parsed =urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or 70
    if len(parsed.path) >= 2:
        itemtype = parsed.path[1]
        selector = parsed.path[2:]
    else:
        itemtype = "1"
        selector = ""
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
            if _HAS_CHARDET:
                detected = chardet.detect(response)
                response = response.decode(detected["encoding"])
            else:
                raise UnicodeDecodeError
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
    cache = write_body(url,response,mime)
    return cache

def _fetch_finger(url,timeout=DEFAULT_TIMEOUT,**kwargs):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or standard_ports["finger"]
    query = parsed.path.lstrip("/") + "\r\n"
    with socket.create_connection((host,port)) as sock:
        sock.settimeout(timeout)
        sock.send(query.encode())
        response = sock.makefile("rb").read().decode("UTF-8")
        cache = write_body(response,"text/plain")
    return cache

# Originally copied from reference spartan client by Michael Lazar
def _fetch_spartan(url,**kwargs):
    cache = None
    url_parts = urllib.parse.urlparse(url)
    host = url_parts.hostname
    port = url_parts.port or standard_ports["spartan"]
    path = url_parts.path or "/"
    query = url_parts.query
    redirect_url = None
    with socket.create_connection((host,port)) as sock:
        if query:
            data = urllib.parse.unquote_to_bytes(query)
        else:
            data = b""
        encoded_host = host.encode("idna")
        ascii_path = urllib.parse.unquote_to_bytes(path)
        encoded_path = urllib.parse.quote_from_bytes(ascii_path).encode("ascii")
        sock.send(b"%s %s %d\r\n" % (encoded_host,encoded_path,len(data)))
        fp = sock.makefile("rb")
        response = fp.readline(4096).decode("ascii").strip("\r\n")
        parts = response.split(" ",maxsplit=1)
        code,meta = int(parts[0]),parts[1]
        if code == 2:
            body = fp.read()
            if meta.startswith("text"):
                body = body.decode("UTF-8")
            cache = write_body(url,body,meta)
        elif code == 3:
            redirect_url = url_parts._replace(path=meta).geturl()
        else:
            return set_error(url,"Spartan code %s: Error %s"%(code,meta))
    if redirect_url:
        cache = _fetch_spartan(redirect_url)
    return cache

def _activate_client_cert(certfile, keyfile):
    #TODO
    #self.client_certs["active"] = (certfile, keyfile)
    #self.active_cert_domains = []
    #self.prompt = self.cert_prompt + "+" + os.path.basename(certfile).replace('.crt','') + "> " + "\001\x1b[0m\002"
    pass

def _deactivate_client_cert():
    #TODO
# if self.active_is_transient:
#        for filename in self.client_certs["active"]:
#            os.remove(filename)
#        for domain in self.active_cert_domains:
#            self.client_certs.pop(domain)
#    self.client_certs["active"] = None
#    self.active_cert_domains = []
#    self.prompt = self.no_cert_prompt
#    self.active_is_transient = False
    pass

def _choose_client_cert():
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
        _activate_client_cert(certfile, keyfile)
    else:
        print("What?")

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
    _activate_client_cert(certfile, keyfile)

def _generate_client_cert(certdir, basename, transient=False):
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
    _activate_client_cert(certfile, keyfile)

def _generate_transient_cert_cert():
    """
    Use `openssl` command to generate a new transient client certificate
    with 24 hours of validity.
    """
    certdir = os.path.join(_CONFIG_DIR, "transient_certs")
    name = str(uuid.uuid4())
    _generate_client_cert(certdir, name, transient=True)
    #TODO
    #self.active_is_transient = True
    #self.transient_certs_created.append(name)

def _generate_persistent_client_cert():
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
    _generate_client_cert(certdir, name)

def _handle_cert_request(meta):
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


def _validate_cert(address, host, cert,accept_bad_ssl=False,automatic_choice=None):
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
        if accept_bad_ssl:
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

    db_path = os.path.join(_CONFIG_DIR, "tofu.db")
    db_conn = sqlite3.connect(db_path)
    db_cur = db_conn.cursor()

    db_cur.execute("""CREATE TABLE IF NOT EXISTS cert_cache
        (hostname text, address text, fingerprint text,
        first_seen date, last_seen date, count integer)""")
    # Have we been here before?
    db_cur.execute("""SELECT fingerprint, first_seen, last_seen, count
        FROM cert_cache
        WHERE hostname=? AND address=?""", (host, address))
    cached_certs = db_cur.fetchall()

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
                db_cur.execute("""UPDATE cert_cache
                    SET last_seen=?, count=?
                    WHERE hostname=? AND address=? AND fingerprint=?""",
                    (now, count+1, host, address, fingerprint))
                db_conn.commit()
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
            if automatic_choice:
                choice = automatic_choice
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
        db_cur.execute("""INSERT INTO cert_cache
            VALUES (?, ?, ?, ?, ?, ?)""",
            (host, address, fingerprint, now, now, 1))
        db_conn.commit()
        certdir = os.path.join(_CONFIG_DIR, "cert_cache")
        if not os.path.exists(certdir):
            os.makedirs(certdir)
        with open(os.path.join(certdir, fingerprint+".crt"), "wb") as fp:
            fp.write(cert)

def _fetch_gemini(url,timeout=DEFAULT_TIMEOUT,**kwargs):
    cache = None
    url_parts = urllib.parse.urlparse(url)
    host = url_parts.hostname
    port = url_parts.port or standard_ports["gemini"]
    path = url_parts.path or "/"
    query = url_parts.query
    # Be careful with client certificates!
    # Are we crossing a domain boundary?
    # TODO : code should be adapted to netcache
#    if self.active_cert_domains and host not in self.active_cert_domains:
#        if self.active_is_transient:
#            print("Permanently delete currently active transient certificate?")
#            resp = input("Y/N? ")
#            if resp.strip().lower() in ("y", "yes"):
#                print("Destroying certificate.")
#                self._deactivate_client_cert()
#            else:
#                print("Staying here.")
#                raise UserAbortException()
#        else:
#            print("PRIVACY ALERT: Deactivate client cert before connecting to a new domain?")
#            resp = input("Y/N? ")
#            if resp.strip().lower() in ("n", "no"):
#                print("Keeping certificate active for {}".format(host))
#            else:
#                print("Deactivating certificate.")
#                self._deactivate_client_cert()
#
#    # Suggest reactivating previous certs
#    if not self.client_certs["active"] and host in self.client_certs:
#        print("PRIVACY ALERT: Reactivate previously used client cert for {}?".format(host))
#        resp = input("Y/N? ")
#        if resp.strip().lower() in ("y", "yes"):
#            self._activate_client_cert(*self.client_certs[host])
#        else:
#            print("Remaining unidentified.")
#            self.client_certs.pop(host)

    # In AV-98, this was the _send_request method
    #Send a selector to a given host and port.
    #Returns the resolved address and binary file with the reply."""
    host = host.encode("idna").decode()
    # Do DNS resolution
    # DNS lookup - will get IPv4 and IPv6 records if IPv6 is enabled
    if ":" in host:
        # This is likely a literal IPv6 address, so we can *only* ask for
        # IPv6 addresses or getaddrinfo will complain
        family_mask = socket.AF_INET6
    elif socket.has_ipv6:
        # Accept either IPv4 or IPv6 addresses
        family_mask = 0
    else:
        # IPv4 only
        family_mask = socket.AF_INET
    addresses = socket.getaddrinfo(host, port, family=family_mask,
            type=socket.SOCK_STREAM)
    # Sort addresses so IPv6 ones come first
    addresses.sort(key=lambda add: add[0] == socket.AF_INET6, reverse=True)
    ## Continuation of send_request
    # Prepare TLS context
    protocol = ssl.PROTOCOL_TLS_CLIENT if sys.version_info.minor >=6 else ssl.PROTOCOL_TLSv1_2
    context = ssl.SSLContext(protocol)
    context.check_hostname=False
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

    #TODO: certificate handling to refactor
#        # Load client certificate if needed
#        if self.client_certs["active"]:
#            certfile, keyfile = self.client_certs["active"]
#            context.load_cert_chain(certfile, keyfile)

        # Connect to remote host by any address possible
    err = None
    for address in addresses:
        s = socket.socket(address[0], address[1])
        s.settimeout(timeout)
        s = context.wrap_socket(s, server_hostname = host)
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

    # Do TOFU
    cert = s.getpeercert(binary_form=True)
    # TODO: another cert handling to refactor
    # Remember that we showed the current cert to this domain...
    #TODO : accept badssl and automatic choice
    _validate_cert(address[4][0], host, cert,automatic_choice="y")
#    if self.client_certs["active"]:
#        self.active_cert_domains.append(host)
#        self.client_certs[host] = self.client_certs["active"]
    # Send request and wrap response in a file descriptor
    url = urllib.parse.urlparse(url)
    new_netloc = host
    if port != standard_ports["gemini"]:
        new_netloc += ":" + str(port)
    url = urllib.parse.urlunparse(url._replace(netloc=new_netloc))
    s.sendall((url + CRLF).encode("UTF-8"))
    f= s.makefile(mode = "rb")
    ## end of send_request in AV98
    # Spec dictates <META> should not exceed 1024 bytes,
    # so maximum valid header length is 1027 bytes.
    header = f.readline(1027)
    header = urllib.parse.unquote(header.decode("UTF-8"))
    if not header or header[-1] != '\n':
        raise RuntimeError("Received invalid header from server!")
    header = header.strip()
    # Validate header
    status, meta = header.split(maxsplit=1)
    if len(meta) > 1024 or len(status) != 2 or not status.isnumeric():
        f.close()
        raise RuntimeError("Received invalid header from server!")
    # Update redirect loop/maze escaping state
    if not status.startswith("3"):
        previous_redirectors = set()
    #TODO FIXME
    else:
        #we set a previous_redirectors anyway because refactoring in progress
        previous_redirectors = set()
    # Handle non-SUCCESS headers, which don't have a response body
    # Inputs
    if status.startswith("1"):
        print(meta)
        if status == "11":
            user_input = getpass.getpass("> ")
        else:
            user_input = input("> ")
        return _fetch_gemini(query(user_input))
    # Redirects
    elif status.startswith("3"):
        newurl = urllib.parse.urljoin(url,meta)
        if newurl == url:
            raise RuntimeError("URL redirects to itself!")
        elif newurl in previous_redirectors:
            raise RuntimeError("Caught in redirect loop!")
        elif len(previous_redirectors) == _MAX_REDIRECTS:
            raise RuntimeError("Refusing to follow more than %d consecutive redirects!" % _MAX_REDIRECTS)
# TODO: redirections handling should be refactored
#        elif "interactive" in options and not options["interactive"]:
#            follow = self.automatic_choice
#        # Never follow cross-domain redirects without asking
#        elif new_gi.host.encode("idna") != gi.host.encode("idna"):
#            follow = input("Follow cross-domain redirect to %s? (y/n) " % new_gi.url)
#        # Never follow cross-protocol redirects without asking
#        elif new_gi.scheme != gi.scheme:
#            follow = input("Follow cross-protocol redirect to %s? (y/n) " % new_gi.url)
#        # Don't follow *any* redirect without asking if auto-follow is off
#        elif not self.options["auto_follow_redirects"]:
#            follow = input("Follow redirect to %s? (y/n) " % new_gi.url)
#        # Otherwise, follow away
        else:
            follow = "yes"
        if follow.strip().lower() not in ("y", "yes"):
            raise UserAbortException()
        previous_redirectors.add(url)
#        if status == "31":
#            # Permanent redirect
#            self.permanent_redirects[gi.url] = new_gi.url
        return _fetch_gemini(newurl)
    # Errors
    elif status.startswith("4") or status.startswith("5"):
        raise RuntimeError(meta)
    # Client cert
    elif status.startswith("6"):
        _handle_cert_request(meta)
        _fetch_gemini(url)
    # Invalid status
    elif not status.startswith("2"):
        raise RuntimeError("Server returned undefined status code %s!" % status)
    # If we're here, this must be a success and there's a response body
    print("status : %s"%status)
    assert status.startswith("2")
    mime = meta
    # Read the response body over the network
    fbody = f.read()
    # DEFAULT GEMINI MIME
    if mime == "":
        mime = "text/gemini; charset=utf-8"
    shortmime, mime_options = parse_mime(mime)
    if "charset" in mime_options:
        try:
            codecs.lookup(mime_options["charset"])
        except LookupError:
            #raise RuntimeError("Header declared unknown encoding %s" % mime_options)
            #If the encoding is wrong, there’s a high probably it’s UTF-8 with a bad header
            mime_options["charset"] = "UTF-8"
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
    cache = write_body(url,body,mime)
    return cache


def fetch(url,offline=False,download_image_first=True,validity=0,**kwargs):
    url = normalize_url(url)
    path=None
    print_error = "print_error" in kwargs.keys() and kwargs["print_error"]
    if is_cache_valid(url,validity=validity):
        path = get_cache_path(url)
    #If we are offline, any cache is better than nothing
    elif offline and is_cache_valid(url,validity=0):
        path = get_cache_path(url)
    elif "://" in url and not offline:
        try:
            scheme = url.split("://")[0]
            if scheme not in standard_ports:
                print("%s is not a supported protocol"%scheme)
                path = None
            elif scheme in ("http","https"):
                path=_fetch_http(url,**kwargs)
            elif scheme == "gopher":
                path=_fetch_gopher(url,**kwargs)
            elif scheme == "finger":
                path=_fetch_finger(url,**kwargs)
            elif scheme == "gemini":
                path=_fetch_gemini(url,**kwargs)
            else:
                print("scheme %s not implemented yet")
        except UserAbortException:
            return
        except Exception as err:
            cache = set_error(url, err)
            # Print an error message
            # we fail silently when sync_only
            if isinstance(err, socket.gaierror):
                if print_error:
                    print("ERROR: DNS error!")
            elif isinstance(err, ConnectionRefusedError):
                if print_error:
                    print("ERROR1: Connection refused!")
            elif isinstance(err, ConnectionResetError):
                if print_error:
                    print("ERROR2: Connection reset!")
            elif isinstance(err, (TimeoutError, socket.timeout)):
                if print_error:
                    print("""ERROR3: Connection timed out!
    Slow internet connection?  Use 'set timeout' to be more patient.""")
            elif isinstance(err, FileExistsError):
                if print_error:
                    print("""ERROR5: Trying to create a directory which already exists
                        in the cache : """)
                print(err)
            elif isinstance(err,requests.exceptions.SSLError):
                if print_error:
                    print("""ERROR6: Bad SSL certificate:\n""")
                    print(err)
                    print("""\n If you know what you are doing, you can try to accept bad certificates with the following command:\n""")
                    print("""set accept_bad_ssl_certificates True""")
            elif isinstance(err,requests.exceptions.ConnectionError):
                if print_error:
                    print("""ERROR7: Cannot connect to URL:\n""")
                    print(str(err))
            else:
                if print_error:
                    import traceback
                    print("ERROR4: " + str(type(err)) + " : " + str(err))
                    #print("\n" + str(err.with_traceback(None)))
                    print(traceback.format_exc())
            return cache
        # We download images contained in the document (from full mode)
        if not offline and download_image_first:
            renderer = ansicat.renderer_from_file(path,url)
            for image in renderer.get_images(mode="full"):
                if image and is_cache_valid(image):
                    width = offutils.term_width() - 1
                    toprint = "Downloading %s" %image
                    toprint = toprint[:width]
                    toprint += " "*(width-len(toprint))
                    print(toprint,end="\r")
                    #d_i_f is False to avoid recursive downloading 
                    #if that ever happen
                    fetch(image,offline=offline,download_image_first=False,validity=0,**kwargs)
    else:
        print("Not cached URL or not supported format (TODO)")
    return path


def main():
    
    # Parse arguments
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="store_true",
                        help="return path to the cache instead of the content of the cache")
    parser.add_argument("--offline", action="store_true",
                        help="Do not attempt to download, return cached version or error")
    parser.add_argument("--max-size", type=int,
                        help="Cancel download of items above that size (value in Mb).")
    parser.add_argument("--timeout", type=int,
                        help="Time to wait before cancelling connection (in second).")
    # No argument: write help
    parser.add_argument('url', metavar='URL', nargs='*',
                        help='download URL and returns the content or the path to a cached version')
    # arg = URL: download and returns cached URI
    # --cache-validity : do not download if cache is valid
    # --validity : returns the date of the cached version, Null if no version
    # --force-download : download and replace cache, even if valid
    args = parser.parse_args()

    param = {}
    
    for u in args.url:
        if args.offline:
            path = get_cache_path(u)
        else:
            print("Download URL: %s" %u)
            path = fetch(u,max_size=args.max_size,timeout=args.timeout)
        if args.path:
            print(path)
        else:
            with open(path,"r") as f:
                print(f.read())
                f.close()

        
if __name__== '__main__':
    main()
