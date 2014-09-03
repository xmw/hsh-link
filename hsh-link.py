# vim: tabstop=4
# copyright Michael Weber (michael at xmw dot de) 2014

from config import STORAGE_DIR, LINK_DIR, FILE_SIZE_MAX
from mod_python.apache import OK, HTTP_NOT_FOUND, HTTP_BAD_REQUEST

import base64, hashlib, mod_python, os

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
    base_url = "http://%s/" % req.headers_in['Host']
    agent = req.headers_in.get('User-Agent', '').lower()
    var = mod_python.util.FieldStorage(req, keep_blank_values=True)
    if not var.getlist('raw') and (agent.count('mozilla') or agent.count('opera') or agent.count('validator')):
        html = True
        req.content_type = "text/html; charset=utf-8"
    else:
        html = False
        req.content_type = "text/plain; charset=utf-8"

    # new_content
    if req.method in ('DELETE', 'PUT'):
        req.write("future DELETE and PUT not yet implented.\n")
        return HTTP_BAD_REQUEST
    elif req.method == 'GET':
        new_content = var.getfirst('content')
        
    elif req.method == 'POST':
        if req.args:
            req.write("Mixed POST and GET not supported.\n")
            return HTTP_BAD_REQUEST
        new_content = var.getfirst('content')

    # lookup
    obj = os.path.normpath(req.uri)[1:]
    link_name = None
    link_hash = None
    blob = None
    if obj:
        if os.path.exists(os.path.join(STORAGE_DIR, obj)):
            blob = obj
        else:
            cand = filter(lambda s: s.startswith(obj), os.listdir(STORAGE_DIR))
            if cand:
                blob = sorted(cand, key=lambda fn: os.lstat(os.path.join(STORAGE_DIR, fn)).st_ctime)[0]
        if not blob:
            link_name = obj
            link_hash = base64.urlsafe_b64encode(hashlib.sha1(link_name).digest())
            if os.path.exists(os.path.join(LINK_DIR, link_hash)):
                blob = read_storage(os.path.join(LINK_DIR, link_hash))

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
        if len(new_content) > FILE_SIZE_MAX:
            return mod_python.apache.HTTP_REQUEST_ENTITY_TOO_LARGE
        new_blob = base64.urlsafe_b64encode(hashlib.sha1(new_content).digest())
        if new_blob != blob:
            write_storage(os.path.join(STORAGE_DIR, new_blob), new_content)
            if link_hash:
                write_storage(os.path.join(LINK_DIR, link_hash), new_blob)
            if html:
                mod_python.util.redirect(req, "/%s?link=%s" % (link_name or new_blob, var.getfirst('link')), new_blob)
            content = new_content
            blob = new_blob
    new_link_name = var.getfirst('link')
    if blob and new_link_name and new_link_name != link_name:
        new_link_hash = base64.urlsafe_b64encode(hashlib.sha1(new_link_name).digest())
        write_storage(os.path.join(LINK_DIR, new_link_hash), blob)
        if html:
            mod_python.util.redirect(req, "/%s" % new_link_name, new_link_name)
    
    #output
    text = []
    if html:
        text += ["""<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<link rel="stylesheet" type="text/css" href="hsh-link.css">
<script src="hsh-link.js"></script>
<title>%s</title>
</head>
<body onLoad="hide()">""" % req.headers_in['Host'],
        '<div id="container">',
        '<form action="%s" method="GET" enctype="multipart/form-data">' % (link_name or '/'),
        '<div id="text"><textarea placeholder="Start typing ..." cols="81" rows="24" name="content" oninput="show()">%s</textarea></div>' % (new_content or content),
        '<div id="control"><A href="/" title="start from scratch/">new</A>',
        '<input type="text" placeholder="link name ..." name="link" oninput="show()" value="%s">' % (link_name or "")]
        if content:
            if link_name:
                text.append('<a href="/%s" title="mutable tag: %s/%s">symlink</A>' % (link_name, base_url, link_name))
                text.append('<a href="/%s?raw" title="mutable tag: %s/%s?raw">/raw</A>' % (link_name, base_url, link_name))
            if blob:
                text.append('<a href="/%s" title="immutable hash: %s/%s">permalink</A>' % (blob, base_url, blob))
                text.append('<a href="/%s?raw" title="immutable hash: %s/%s?raw">/raw</A>' % (blob, base_url, blob))
                text.append('<input type="hidden" name="prev" value="%s">' % blob)
        text.append('<input type="submit" id="submit" value="%s">' % \
            (content and 'update' or 'save'))
        text.append("""</div>
</form>
<div id="footer">(c) <a href="http://xmw.de/">xmw.de</a> 2014 <a href="https://github.com/xmw/hsh-link">sources</a>
<a href="http://validator.w3.org/check?uri=referer">html5</a></div>
</div>
</body>
</html>""")
    else:
        if new_content:
            text.append("%s/%s\n" % (base_url, new_blob))
        else:
            text.append(content)
    req.write("\n".join(text))
    return OK
