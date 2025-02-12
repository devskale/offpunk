# OFFPUNK

A command-line and offline-first smolnet browser/feed reader for Gemini, Gopher, Spartan and Web by [Ploum](https://ploum.net).

The goal of Offpunk is to be able to synchronise your content once (a day, a week, a month) and then browse/organise it while staying disconnected.

Official page : [Offpunk.net](https://offpunk.net)
Development (repository/mailing lists) : [sr.ht](https://sr.ht/~lioploum/offpunk/)

![Screenshot HTML page with picture](screenshots/1.png)
![Screenshot Gemini page](screenshots/2.png)

Offpunk is a fork of the original [AV-98](https://tildegit.org/solderpunk/AV-98) by Solderpunk and was originally called AV-98-offline as an experimental branch.

## How to use

Offpunk is a set of python files. Installation is optional, you can simply git clone the project and run "./offpunk.py" or "python3 offpunk.py" in a terminal. You can also a packaged version:

- [List of existing Offpunk packages (Repology)](https://repology.org/project/offpunk/versions)
- Please contribute packages for other systems, there’s a [mailing-list dedicated to packaging](https://lists.sr.ht/~lioploum/offpunk-packagers).

To get started, launch offpunk then type "tutorial".

You can also consults it online: [Offpunk tutorial](https://offpunk.net/firststeps.html)

At any point, you can use "help" to get the list of commands and "help command" to get a small help about "command".

## More

Important news and releases will be announced on the [offpunk-devel mailing list](https://lists.sr.ht/~lioploum/offpunk-devel)

Questions can be asked on [the users mailing](list https://lists.sr.ht/~lioploum/offpunk-users)

## Dependencies

Offpunk has few "strict dependencies", i.e. it should run and work without anything
else beyond the Python standard library and the "less" pager. However, it will "opportunistically import" a few other libraries if they are available to offer an improved
experience or some other features such as HTTP/HTML or image support.

To avoid using unstable or too recent libraries, the rule of thumb is that a library should be packaged in Debian/Ubuntu. Keep in mind that Offpunk is mainly tested will all libraries installed. If you encounter a crash without one optional dependencies, please report it. Patches and contributions to remove dependencies or support alternatives are highly appreciated.

- PIP: [requirements file to install dependencies with pip](requirements.txt)
- Ubuntu/Debian: [command to install dependencies on Ubuntu/Debian without pip](ubuntu_dependencies.txt)

Run command `version` in offpunk to see if you are missing some dependencies.

Mandatory or highly recommended (packagers should probably make those mandatory):

- [less](http://www.greenwoodsoftware.com/less/): mandatory but is probably already on your system
- [file](https://www.darwinsys.com/file/) is used to get the MIME type of cached objects. Should already be on your system.
- [xdg-utils](https://www.freedesktop.org/wiki/Software/xdg-utils/) provides xdg-open which is highly recommended to open files without a renderer or a handler. It is also used for mailto: command.
- The [cryptography library](https://pypi.org/project/cryptography/) will provide a better and slightly more secure experience when using the default TOFU certificate validation mode and is recommended (apt-get install python3-cryptography).

Dependencies to enable web browsing (packagers may put those in an offpunk-web meta-package but it is recommended to have it for a better offpunk experience)

- [Python-requests](http://python-requests.org) is needed to handle http/https requests natively (apt-get install python3-requests). Without it, http links will be opened in an external browser
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup) is needed to render HTML. Without it, HTML will not be rendered or be sent to an external parser like Lynx. (apt-get install python3-bs4)
- [Readability](https://github.com/buriy/python-readability) is highly suggested to trim useless part of most html pages (apt-get install python3-readability or pip3 install readability-lxml)
- [Python-feedparser](https://github.com/kurtmckee/feedparser) will allow parsing of RSS/Atom feeds and thus subscriptions to them. (apt-get install python3-feedparser)
- [Chafa](https://hpjansson.org/chafa/) allows to display pictures in your console. Install it and browse to an HTML page with picture to see the magic.

Gopher dependencies:

- [Python-chardet](https://github.com/chardet/chardet) is used to detect the character encoding on Gopher (and may be used more in the future)

Nice to have (packagers should may make those optional):

- [Xsel](http://www.vergenet.net/~conrad/software/xsel/) allows to `go` to the URL copied in the clipboard without having to paste it (both X and traditional clipboards are supported). Also needed to use the `copy` command. (apt-get install xsel). Xclip can be used too.
- [Wl-clipboard](https://github.com/bugaevc/wl-clipboard) allows the same feature than xsel but under Wayland
- [Python-setproctitle](https://github.com/dvarrazzo/py-setproctitle) will change the process name from "python" to "offpunk". Useful to kill it without killing every python service.

## Features

- Browse https/gemini/gopher without leaving your keyboard and without distractions
- Customize your experience with the `theme` command.
- Built-in documentation: type `help` to get the list of command or a specific help about a command.
- Offline mode to browse cached content without a connection. Requested elements are automatically fetched during the next synchronization and are added to your tour.
- HTML pages are prettified to focus on content. Read without being disturbed or see the full page with `view full`.
- RSS/Atom feeds are automatically discovered by `subscribe` and rendered as gemlogs. They can be explored with `view feed` and `view feeds`.
- Support "subscriptions" to a page. New content seen in subscribed pages are automatically added to your next tour.
- Complex bookmarks management through multiple lists, built-in edition, subscribing/freezing lists and archiving content.
- Advanced navigation tools like `tour` and `mark` (as per VF-1). Unlike AV-98, tour is saved on disk accross sessions.
- Ability to specify external handler programs for different MIME types (use `handler`)
- Enhanced privacy with `redirect` which allows to block a http domain or to redirect all request to a privacy friendly frontent (such as nitter for twitter).
- Non-interactive cache-building with configurable depth through the --sync command. The cache can easily be used by other software.
- `netcache`, a standalone CLI tool to retrieve the cached version of a network ressource.
- `ansicat`, a standalone CLI tool to render HTML/Gemtext/image in a terminal.
- `opnk`, a standalone CLI tool to open any kind of ressources (local or network) and display it in your terminal or, if not possible, fallback to `xdg-open`.

## RC files

You can use an RC file to automatically run any sequence of valid Offpunk
commands upon start up. This can be used to make settings controlled with the
`set`, `handler` or `themes` commands persistent. You can also put a `go` command in
your RC file to visit a "homepage" automatically on startup, or to pre-prepare
a `tour` of your favourite Gemini sites or `offline` to go offline by default.

The RC file should be called `offpunkrc` and goes in $XDG_CONFIG_DIR/offpunk (or .config/offpunk or .offpunk if xdg not available). In that file, simply write one command per line, just like you would type them in offpunk.

## Cache design

The offline content is stored in ~/.cache/offpunk/ as plain .gmi/.html files. The structure of the Gemini-space is tentatively recreated. One key element of the design is to avoid any database. The cache can thus be modified by hand, content can be removed, used or added by software other than offpunk.

The cache can be accessed/built with the `netcache` tool. See `netcache -h` for more informations.

There’s no feature to automatically trim the cache. But any part of the cache can safely be removed manually as there are no databases or complex synchronisation.

## Tests

Be sure to install the dev requirements (`pytest` and `pytest-mock`) with:

    pip install -r requirements-dev.txt

And then run the test suite using `pytest`.
