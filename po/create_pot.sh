#!/usr/bin/env bash

cd ..

# get all "normal" translatable strings
xgettext --add-comments=TRANSLATORS *py -o po/messages_xgettext.pot

# get only docstrings from offpunk, for interactive help
pygettext3 -K -D offpunk.py

# get rid of indentation caused by docstrings' nature
sed -e 's/"        /"/' messages.pot >messages2.pot

# merge regular messages and docstrings
xgettext -o po/messages.pot messages2.pot po/messages_xgettext.pot

# delete temporal files
rm messages.pot messages2.pot  po/messages_xgettext.pot

cd po



# previous version of this script, included in case 
# someone has any trouble with the current one.
# Just uncomment the following lines:
#
#./extract_docstrings.py > ../docstrings.py
#
#
#cd ..
#xgettext --add-comments=TRANSLATORS *py -o po/messages.pot
#rm docstrings.py
#cd po
