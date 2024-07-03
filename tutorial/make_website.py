#!/bin/python
import os
import unicodedata
import html
from datetime import datetime

baseurl = "offpunk.net"
htmldir="../../public_html/"
html_page_template = "page_template.html"
today = datetime.today().strftime("%Y-%m-%d")

#Convert gmi to html
# Also convert locals links that ends .gmi to .html
def gmi2html(raw,signature=None,relative_links=True,local=False):
    lines = raw.split("\n")
    inquote = False
    inpre = False
    inul = False
    inpara = False
    def sanitize(line):
        line = unicodedata.normalize('NFC', line)
        return html.escape(line)
    content = ""
    title = ""
    h2_nbr = 1
    for line in lines:
        if inul and not line.startswith("=>") and not line.startswith("* "):
            content += "</ul>\n"
            inul = False
        if inquote and not line.startswith(">"):
            content += "</blockquote>\n"
            inquote = False
        if line.startswith("```"):
            if inpara:
                content += "</p>\n"
                inpara = False
            if inpre:
                content += "</pre>\n"
            else:
                content += "<pre>"
            inpre = not inpre
        elif inpre:
            content += sanitize(line) + "\n"
        elif line.startswith("* "):
            if not inul:
                if inpara:
                    content += "</p>\n"
                    inpara = False
                content +="<ul>"
                inul = True
            content += "<li>%s</li>\n" %sanitize(line[2:])
        elif line.startswith(">"):
            if not inquote:
                if inpara:
                    content += "</p>\n"
                    inpara = False
                content += "<blockquote>"
                inquote = True
            content += sanitize(line[1:]) + "<br>"
        elif line.startswith("##"):
            if inpara:
                content += "</p>\n"
                inpara = False
            content += "<h2 id=\"soustitre-%s\">"%str(h2_nbr)
            h2_nbr += 1
            content += sanitize(line.lstrip("# "))
            content += "</h2>\n"
        elif line.startswith("# "):
            #We don’t add directly the first title as it is used in the template
            if inpara:
                content += "</p>\n"
                inpara = False
            if not title:
                title = sanitize(line[2:])
            else:
                content += "<h1>"
                content += sanitize(line[2:])
                content += "</h1>\n"
        elif line.startswith("=>"):
            if inpara:
                content += "</p>\n"
                inpara = False
            splitted = line[2:].strip().split(maxsplit=1)
            link = splitted[0]
            link.removeprefix("https://"+baseurl)
            link.removeprefix("gemini://"+baseurl)
            #removing the server part if local
            #converting local links to html (if gmi)
            if "://" not in link and link.endswith(".gmi"):
                link = link[:-4] + ".html"
            if not relative_links and "://" not in link:
                link = "https://" + base_url + "/" + link.lstrip("./")
            elif local:
                link = local_url + link.lstrip("./")
            if len(splitted) == 1:
                description = ""
                name = link
            else:
                name = sanitize(splitted[1])
                description = name
            # Displaying picture if link ends with a picture extension. 
            #Except for commons.wikimedia.org
            if (link[-4:] in [".jpg",".png",".gif"] or link[-5:] in [".jpeg",".webp"]) and\
                not link.startswith("https://commons.wikimedia.org"):
                if inul:
                    content += "</ul>\n"
                    inul = False
                #content += "<div class=\"center\">"
                content += "<figure>\n"
                imgtag = "<img alt=\"%s\" src=\"%s\" width=\"450\" class=\"center\">"%(name,link)
                content += "<a href=\"%s\">"%link + imgtag + "</a>\n"
                #content += "</div>"
                if description:
                    content += "<figcaption>%s</figcaption>\n"%description
                content += "</figure>\n"
            else:
                if not inul:
                    content += "<ul>\n"
                    inul = True
                content += "<li><a href=\"%s\">%s</a></li>"%(link,name)
                content += "\n"
        elif line.strip() :
            if not inpara:
                content += "<p>"
                inpara = True
            content += "%s<br>\n"%sanitize(line)
        elif inpara:
            if content[-5:] == "<br>\n":
                content = content[:-5]
            content += "</p>\n"
            inpara = False
    if inul:
        content += "</ul>\n"
        inul = False
    if signature:
        content += "\n<div class=\"signature\">" + signature + "</div>"
    return title, content

if __name__=="__main__":
    files = os.listdir()
    for f in files:
        if f.endswith(".gmi"):
            content = ""
            #Extracting gmi content from the file
            with open(f) as fi:
                content = fi.read()
                fi.close()
            #converting content to html
            title, html_content = gmi2html(content)
            gemlink = "gemini://" + baseurl + "/" + f
            f_html = f[:-4] + ".html"
            httplink = "https://" + baseurl + "/" + f_html
            image_preview = "screenshots/1.png"
            #writing html into its template
            with open(html_page_template) as f:
                template = f.read()
                f.close()
            final_page = template.replace("$CONTENT",html_content).\
                                replace("$TITLE",title).\
                                replace("$GEMLINK",gemlink).\
                                replace("$HTMLLINK",httplink).\
                                replace("$PUBLISHED_DATE",today).\
                                replace("$IMAGE_PREVIEW",image_preview)
            path = htmldir + f_html
            with open(path, mode="w") as f:
                f.write(final_page)
                f.close()

