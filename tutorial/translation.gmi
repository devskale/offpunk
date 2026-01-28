
# Brief how to to translate and keep offpunk translated and up to date

This is a very brief document, showing merely the commands one would need to keep offpunk translatable, and some notes for potential translators on how to add a new language to the available ones

As a pre-requirement, make sure you have gettext installed in your system. We recommend you also install poedit, a user-friendly and easy to use editor for po files:

```
# apt install gettext poedit
```

(instructions for other systems are welcome)

## Quick TL;DR

If you are interested in the details and reasons for all the commands, keep reading. Here's a quick summary of the steps you need to contribute a translation for offpunk:

```
cd <repository root>
xgettext --add-comments=TRANSLATORS *py -o po/messages.pot
cd po/
msginit -i messages.pot -o XX.po # XX should be your language code
#it will ask you details like your email
poedit XX.po 
```

poedit will create a XX.mo file that you can test in your system (see below for details)
If everything is correct, you can contribute the XX.po file. We'll be happy to accept it!

Keep reading now for details :)

## Creating and updating the "po template" (pot file)

In the gettext system, all translations start with this file. It's by default called messages.pot

To create it, this was the command used (from the root folder of the offpunk source code):

```
$ xgettext --add-comments=TRANSLATORS *py -o po/messages.pot
```

xgettext will "extract" all the translatable strings from all the python files (*py), and use po/messages.pot as the output file (-o)
The "--add-comments=TRANSLATORS" part of the command tells xgettext to copy the comments that the devs left for translators. These comments will give valuable tips to translators. See the next file for more detail:

https://www.gnu.org/software/gettext/manual/html_node/Translator-advice.html

in the future, if new "translatable" strings are added (or the strings are modified), this same command can be run again.


## Creating a translation for a new language

If you are an offpunk user and want to translate it into your language, you can do it with these steps:

first, make sure you have your system configured to use the right locale:

```
$ locale
```

Then, follow the steps above to create the "po template" file (messages.pot)

Ideally, your system would be configured to use your native language, and ideally that's the "target" language you'll translate offpunk into (but this is not strictly necessary) . Enter the i18n folder:

```
$ cd po
```

and then run this command to create a po file from the 'po template' file:

```
$ msginit -i messages.pot -o XX.po
```

XX should be the language code of the language you'll translate offpunk into. Examples are fr_FR, fr_CA, es_ES, es_AR, and others

If your system does not currently use that same language (locale), you can specify the lang running instead:

```
$ msginit -l LANG_CODE -i messages.pot -o XX.po
```

(you might want to check 'man msginit')

## Translating the messages

Po files are technically text files and can be edited with your favorite editor. However, if you are a new translator, I recommend using poedit.

```
$ poedit XX.po
```

XX.po is the file created before

Then, you can click on the different messages, and input an appropriate translation under them. When saving, poedit will create a XX.mo file (this is the binary format that your computer will actually use to show offpunk in your language. It also has a menu option to do that.

If you were interested, you can manually create this .mo file by:

```
$ msgfmt XX.po -o XX.mo
```

## Testing your translation

After you have translated the whole file (or even some of the strings), and you have a XX.mo file, you can test it by:

```
# cp XX.mo /usr/share/locale/XX/LC_MESSAGES/offpunk.mo
```

(these are the paths in a debian system. Not sure how universal this is, but right now it's more-or-less hardcoded in the .py files)

keep in mind 'XX' in that path will match the output you see when you run "locale" in your terminal

then you can start offpunk.py from the source code and check if any of the strings have to be changed

NOTE: if you current LOCALE doesn't match the one you are translating into, you can test the language anyway, tweaking the environment a bit, only for offpunk.

For example: your system is in spanish, but you also speak german, and are now translating offpunk to german. You could test the german translation by:

```
# cp de.mo /usr/share/locale/de/LC_MESSAGES/offpunk.mo #this should require "sudo", or be run as root
$ locale
LANG=es_ES.UTF-8
[...]

$ LANG=de ./offpunk.py
```


## Keeping your translation up-to-date

Every now and then, new messages will make their way into offpunk. New features are added, some messages change... In those cases, you can incorporate the new messages that appear in messages.pot (typically the devs will update the pot when they introduce new strings) to your language's po file by running:

```
$ msgmerge -U XX.po messages.pot 
```

But, if you don't want to have to remember these commands, poedit also has a menu entry that would let you, while you are translating your po file, "Update from POT file". You can find that menu entry under the "Translation" menu. Then, navigate and choose the updated messages.pot file and you are done, new untranslated strings will apear in the poedit interface for you to translate. Translate, compile the .mo file, test your translation, and you're good!

If you get into translating free software into your language, you can explore poedit's capabilities ("pre-translate" from "translation memory" will soon prove its usefulness), and other translation tools and maybe decide you like some other tool better than poedit. Poedit has been used as an example in this guide because it is powerful enough and easy enough to use that we can only recommend it as the perfect starting point.

## A note to devs

Ideally, all strings that are shown to users should be translatable, so offpunk users can benefit from it and use the program in their native language.

Making the messages translatable is not too difficult. As a general rule, if a message is to be shown, like:

```
print("Welcome to my program")
```

it would be enough to surround the actual string with the "_()" function, like this:

```
print(_("Welcome to my program"))
```

You can also add comments for the future translators that could help them understand tricky messages. Translation software often will show these hints while the translators are working on the messages.

```
#TRANSLATORS: this is a verb. Like in "open the window", not "the window is open"
print(_("Open"))
```

Take a look at this link if you are interested in the topic:
https://www.gnu.org/software/gettext/manual/html_node/Translator-advice.html



