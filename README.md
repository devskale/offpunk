# OFFPUNK

A command-line, text-based and offline-first Gemini browser by [Ploum](gemini://rawtext.club/~ploum).

Focused on Gemini first but with some Gopher/web support available or projected, the goal of Offpunk is to be able to synchronise your content once (a day, a week, a month) and then browse it while staying disconnected.

Offpunk is a fork of the original [AV-98](https://tildegit.org/solderpunk/AV-98) by Solderpunk and was originally only called AV-98-offline as an experimental branch.

## Lightning introduction

You use the `go` command to visit a URL, e.g. `go gemini.circumlunar.space`. If xsel is installed, go will automatically fetch the URL from your clipboard.

Links in Gemini documents are assigned numerical indices.  Just type an index to
follow that link. If a Gemini document is too long to fit on your screen, use the `less` command
to pipe it to the `less` pager.

Use `add` to add a capsule to your bookmarks and `bm` to show your bookmarks (which are stored in a file in you .config).

Use `offline` to only browse cached content and `online` to go back online. While offline, the `reload` command will force a re-fetch during the next synchronisation.

Use the `help` command to learn about additional commands.

When launched with the "--sync" option, offpunk will run non-interactively and fetch content from your bookmarks and content tentatively accessed while offline. New content found in your bookmarks will be automatically added to your tour (use `tour ls` to see your current tour, `tour` without argument to access the next item and `tour X` where X is a link number to add the content of a link to your tour). Unlike AV-98, the tour is preserved accross sessions.

With "--sync", one could specify a "--cache validity" in seconds. This option will not refresh content if a cache exists and is less than the specified amount of seconds old.

For example, running

`offpunk.py --sync --cache-validity 43200`

will refresh your bookmarks if those are at least 12h old. If cache-validity is not set or set to 0, any cache is considered good and only content never cached before will be fetched. 

At the moment, caching only work for gemini:// ressources. gopher:// is not implemented and http(s):// ressources are sent to an "offline browser" (by default, None, nothing is done). It could be useful to, for example, send the http:// links to a text file in order to visit them while online.

## TODO

Known issues in the code:
* WONTFIX: Sync is slow if you have bookmarks with lot of links that change very often.
* FIXME0: Certificates error are not handled in --sync
* FIXME1: consider root file is always index.gmi
* FIXME2: offline web browser use os.system because it’s the only one that understands the ">> file.txt"

* TODO: Update blackbox to reflect cache hits.


## More

See how I browse Gemini offline => gemini://rawtext.club/~ploum/2021-12-17-offline-gemini.gmi


## Dependencies

Offpunk has no "strict dependencies", i.e. it will run and work without anything
else beyond the Python standard library.  However, it will "opportunistically
import" a few other libraries if they are available to offer an improved
experience.

* The [ansiwrap library](https://pypi.org/project/ansiwrap/) may result in
  neater display of text which makes use of ANSI escape codes to control colour.
* The [cryptography library](https://pypi.org/project/cryptography/) will
  provide a better and slightly more secure experience when using the default
  TOFU certificate validation mode and is highly recommended.
* [Python magic](https://github.com/ahupp/python-magic/) is useful to determine the MIME type of cached object. If not present, the file extension will be used but some capsules provide wrong extension or no extension at all.

## Features

* TOFU or CA server certificate validation
* Extensive client certificate support if an `openssl` binary is available
* Ability to specify external handler programs for different MIME types
* Gopher proxy support (e.g. for use with
  [Agena](https://tildegit.org/solderpunk/agena))
* Advanced navigation tools like `tour` and `mark` (as per VF-1)
* Bookmarks
* IPv6 support
* Supports any character encoding recognised by Python

## RC files

You can use an RC file to automatically run any sequence of valid Offpunk
commands upon start up.  This can be used to make settings controlled with the
`set` or `handler` commanders persistent.  You can also put a `go` command in
your RC file to visit a "homepage" automatically on startup, or to pre-prepare
a `tour` of your favourite Gemini sites or `offline` to go offline by default.

The RC file should be called `offpunkrc`.  Offpunk will look for it first in
`~/.offpunk/` and second in `~/.config/offpunk/`.  Note that either directory might
already exist even if you haven't created it manually, as Offpunk will, if
necessary, create the directory itself the first time you save a bookmark (the
bookmark file is saved in the same location).  Offpunk will create
`~/.config/offpunk` only if `~/.config/` already exists on your system, otherwise
it will create `~/.offpunk/`.
