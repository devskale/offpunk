#!/usr/bin/env bash
./extract.py > ../docstrings.py

cd ..
xgettext --add-comments=TRANSLATORS *py -o po/messages.pot
rm docstrings.py
cd po
