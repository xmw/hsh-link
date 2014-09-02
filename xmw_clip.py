# vim: tabstop=4
# copyright Michael Weber (michael at xmw dot de) 2014

from config import STORAGE_DIR, LINK_DIR
from mod_python.apache import OK, HTTP_NOT_FOUND

import hashlib, mod_python, os


def encapsulate(req, raw, html=False):
    if html:
        req.content_type = "text/html; charset=utf-8"
        req.write('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" ' + \
            '"http://www.w3.org/TR/html4/loose.dtd">\n')
        req.write('<HTML>\n<HEAD>\n<META http-equiv="Content-Type" content="text/html; charset=utf-8">\n')
        req.write('<script>function hide() { document.getElementById("submit").style.visibility="hidden"; }')
        req.write('  function show() { document.getElementById("submit").style.visibility="inherit"; }</script>')
        req.write('<TITLE>%s</TITLE>\n</HEAD>\n<BODY onLoad="hide()">\n<CENTER>' % req.headers_in['Host'])
    else:
        req.content_type = "text/plain; charset=utf-8"

    req.write(raw)

    if html:
        req.write('<BR>\n(c) xmw.de 2014<BR>\n<A href="http://validator.w3.org/check?uri=referer">' + \
            '<FONT color="#FFFFFF"><IMG src="http://www.w3.org/Icons/valid-html401-blue"' + \
	    'alt="Valid HTML 4.01 Transitional" height="31" width="88"></FONT></A>\n</CENTER>\n</BODY>\n</HTML>\n')
 

def read_storage(fn):
    if os.path.exists(fn):
        f = file(fn, 'r')
        content = f.read()
        f.close()
        return content

def write_storage(fn, data):
    f = file(fn, 'w')
    f.write(data)
    f.close()
    
       
def handler(req):
    agent = req.headers_in.get('User-Agent', '').lower()
    html = agent.count('mozilla') or agent.count('opera') or agent.count('validator')
    var = mod_python.util.FieldStorage(req, keep_blank_values=True)
    if var.getlist('raw'):
        html = False

    # new_content
    if req.method in ('DELETE', 'PUT'):
        encapsulate(req, "future DELETE and PUT not yet implented.\n", html)
        return OK
    elif req.method == 'GET':
        new_content = var.getfirst('content')
    elif req.method == 'POST':
        if req.args:
            encapsulate(req, "Mixed POST and GET not supported.\n", html)
            return OK
        new_content = var.getfirst('content')

    # lookup
    obj = os.path.normpath(req.uri)[1:]
    link = None
    blob = None
    if obj:
        if os.path.exists(os.path.join(STORAGE_DIR, obj)):
            blob = obj
        else:
            cand = filter(lambda s: s.startswith(obj), os.listdir(STORAGE_DIR))
            if cand:
                blob = sorted(cand, key=lambda fn: os.lstat(os.path.join(STORAGE_DIR, fn)).st_ctime)[0]
        if not blob:
            link = obj
            if os.path.exists(os.path.join(LINK_DIR, link)):
                blob = read_storage(os.path.join(LINK_DIR, link))

    if blob and os.path.exists(os.path.join(STORAGE_DIR, blob)):
        content = read_storage(os.path.join(STORAGE_DIR, blob))
    else:
        content = ""

    # append
    if not new_content:
        append_content = var.getfirst('append')
        if append_content:
            new_content = content + append_content

    # store
    if new_content:
        new_blob = hashlib.sha1(new_content).hexdigest()
        if new_blob != blob:
            write_storage(os.path.join(STORAGE_DIR, new_blob), new_content)
            if link:
                write_storage(os.path.join(LINK_DIR, link), new_blob)
            if html:
                mod_python.util.redirect(req, "/%s" % (link or new_blob), new_blob)
    
    #output
    if html:
        text = []
        text.append('<FORM enctype="multipart/form-data" method="POST" action="%s">' % (link or '/'))
        text.append('<TEXTAREA placeholder="Start typing ..." border="0" cols="81" rows="24" name="content" oninput="show()">%s</TEXTAREA><BR>' % (new_content or content))
        if content:
            if link:
                text.append('<A href="%s" text="mutable tag: %s">symlink</A>' % (link, link))
            if blob:
                text.append('<A href="%s" text="immutable hash: %s">context</A>' % (blob, blob))
                text.append('<INPUT type="hidden" name="prev" value="%s">' % blob)
        text.append('<INPUT type="submit" id="submit" value="store">')
        text.append('</FORM>')
        if var.getlist('debug'):
            text.append(str(req.headers_in))
        encapsulate(req, '\n'.join(text), True)
    else:
        if new_content:
            encapsulate(req, req.headers_in['Host'] + '/' + new_blob, False)
        else:
            encapsulate(req, content, False)
            

    return OK
