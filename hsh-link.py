# vim: tabstop=4
# copyright Michael Weber (michael at xmw dot de) 2014

from config import STORAGE_DIR, LINK_DIR, FILE_SIZE_MAX, MIME_ALLOWED
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
    
def get_last_value(fieldstorage, name, default=None):
    cand = fieldstorage.getlist(name)
    if cand:
        return cand[-1].value
    return default
       
def handler(req):
    base_url = "http://%s/" % req.headers_in['Host']
    var = mod_python.util.FieldStorage(req, keep_blank_values=True)

    #guess mime
    mime = "text/plain"
    agent = req.headers_in.get('User-Agent', '').lower()
    if agent.count('mozilla') or agent.count('opera') or agent.count('validator'):
        mime = 'text/html'
    mime = get_last_value(var, 'mime', mime)
    if not mime in MIME_ALLOWED:
        return HTTP_BAD_REQUEST
    req.content_type = mime + "; charset=utf-8"
    html = mime == 'text/html' #TODO drop me

    # new_content
    if req.method in ('DELETE', 'PUT'):
        req.write("future DELETE and PUT not yet implented.\n")
        return HTTP_BAD_REQUEST
    elif req.method == 'GET':
        new_content = get_last_value(var, 'content')
        
    elif req.method == 'POST':
        if req.args:
            req.write("Mixed POST and GET not supported.\n")
            return HTTP_BAD_REQUEST
        new_content = get_last_value(var, 'content')

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
        append_content = get_last_value(var, 'append')
        if append_content:
            new_content = content + append_content

    # store
    new_blob = None
    if new_content:
        if len(new_content) > FILE_SIZE_MAX:
            return mod_python.apache.HTTP_REQUEST_ENTITY_TOO_LARGE
        new_blob = base64.urlsafe_b64encode(hashlib.sha1(new_content).digest())
        if new_blob != blob:
            write_storage(os.path.join(STORAGE_DIR, new_blob), new_content)
            content, blob = new_content, new_blob
    new_link_name = get_last_value(var, 'link')
    if new_link_name == link_name:
        new_link_name = None
    if new_link_name:
        new_link_hash = base64.urlsafe_b64encode(hashlib.sha1(new_link_name).digest())
        if blob:
            write_storage(os.path.join(LINK_DIR, new_link_hash), blob)
        link_name, link_hash = new_link_name, new_link_hash
    if new_blob and link_hash:
        write_storage(os.path.join(LINK_DIR, link_hash), new_blob)
    if html:
        if new_link_name:
            mod_python.util.redirect(req, "/%s" % new_link_name)
        elif new_blob:
            if link_name:
                mod_python.util.redirect(req, "/%s" % link_name)
            else:
                mod_python.util.redirect(req, "/%s" % new_blob)
    
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
<body onLoad="body_loaded()">""" % req.headers_in['Host'],
        '<div id="container">',
        '<form action="%s" method="POST" enctype="multipart/form-data">' % (link_name or '/'),
        '<div id="text"><textarea placeholder="Start typing ..." cols="81" rows="24" name="content" oninput="data_modified()">%s</textarea></div>' % (new_content or content),
        '<div id="control"><A href="/" title="start from scratch/">new</A>',
        'symlink:<input type="text" placeholder="enter name" name="link" oninput="data_modified()" value="%s">' % (link_name or "")]
        if content:
            if blob:
                text.append('<a href="/%s" title="immutable hash: %s/%s">permalink</A>' % (blob, base_url, blob))
                text.append('<input type="hidden" name="prev" value="%s">' % blob)
            text.append(' | view: <select name="mime" id="mime" onchange="mime_selected()">')
            for mime_ in 'text/plain', 'text/html':
                text.append('<option value="%s"%s>%s</option>' % (mime_, mime == mime_ and ' selected' or '', mime_))
            text.append('</select>')
        text.append('<input type="submit" id="store" title="safe changed data" value="%s">' % \
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
