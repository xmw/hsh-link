# vim: tabstop=4 fileencoding=utf-8
# copyright Michael Weber (michael at xmw dot de) 2014

from config import STORAGE_DIR, LINK_DIR, FILE_SIZE_MAX, MIME_ALLOWED, BASE_PROTO, BASE_PATH
OUTPUT = 'default', 'raw', 'html', 'link', 'short', 'qr', 'qr_png', 'qr_utf8', 'qr_ascii'

import base64, hashlib, mod_python.apache, os

hsh = lambda s: base64.urlsafe_b64encode(hashlib.sha1(s).digest()).rstrip('=')

def subdirfn(repo, fn):
    if len(fn) < 4:
        return ['', '']
    return os.path.join(repo, fn[0:2], fn[2:4]), fn

def is_storage(repo, fn):
    return os.path.exists(os.path.join(*subdirfn(repo, fn)))

def read_storage(repo, fn):
    fn = os.path.join(*subdirfn(repo, fn))
    if os.path.exists(fn):
        f = file(fn, 'r')
        content = f.read()
        f.close()
        return content
    return None

def write_storage(repo, fn, data):
    d, fn = subdirfn(repo, fn)
    if not os.path.exists(d):
        os.makedirs(d, mode=0770)
    f = file(os.path.join(d, fn), 'w')
    f.write(data)
    f.close()

def find_storage(repo, partfn):
    d, partfn = subdirfn(repo, partfn)
    if not os.path.exists(d):
        return None
    cand = filter(lambda s: s.startswith(partfn), os.listdir(d))
    if not cand:
        return None
    return sorted(cand, key=lambda fn: os.lstat(os.path.join(d, fn)).st_ctime)[0]

def uniq_name(repo, fn):
    for i in range(4, len(fn)):
        if find_storage(repo, fn[:i]) == fn:
            return fn[:i]
    return fn
    
def get_last_value(fieldstorage, name, default=None):
    cand = fieldstorage.getlist(name)
    if cand:
        return cand[-1].value
    return default
       
def handler(req):
    var = mod_python.util.FieldStorage(req, keep_blank_values=True)
    BASE_URL = BASE_PROTO + req.headers_in['Host'] + BASE_PATH

    #guess output format
    output = 'default'
    agent = req.headers_in.get('User-Agent', '').lower()
    if agent.count('mozilla') or agent.count('opera') or agent.count('validator'):
        output = 'html'
        agent = 'graphic'
    else:
        agent = 'text'
    output = get_last_value(var, 'output', output)
    if not output in OUTPUT:
        return mod_python.apache.HTTP_BAD_REQUEST
    if output == 'qr':
        if agent == 'graphic':
            output = 'qr_png'
        else:
            output = 'qr_text'

    # new_content
    if req.method == 'DELETE':
        req.write("DELETE not yet implented.\n")
        return mod_python.apache.HTTP_BAD_REQUEST
    elif req.method == 'PUT':
        new_data = req.read()
    elif req.method in ('GET', 'POST'):
        new_data = get_last_value(var, 'content')
    else:
        return mod_python.apache.HTTP_BAD_REQUEST
    # append
    append = get_last_value(var, 'append')

    new_link_name = get_last_value(var, 'link')

    # data_hash, link_name or abrev. data_hash
    data, data_hash, link_name, link_hash = None, None, None, None
    obj = os.path.normpath(req.uri)[len(BASE_PATH):]
    if obj == 'robots.txt' or obj.startswith('.artwork/'):
        return mod_python.apache.DECLINED
    if not len(obj):
        pass
    elif is_storage(STORAGE_DIR, obj):
        data_hash = obj
    else:
        t = hsh(obj)
        if is_storage(LINK_DIR, t):
            link_name, link_hash = obj, t
        else:
            t = find_storage(STORAGE_DIR, obj)
            if t:
                data_hash = t
            else:
                new_link_name = obj

    # don't just replay
    if output == 'raw':
        if not data_hash and not link_name:
            return mod_python.apache.HTTP_BAD_REQUEST

    # switch to new link_name
    if new_link_name != None:
        if new_link_name == link_name: # no update
            new_link_name = None
        else:
            # deref old symlink, if new_link but no new_data
            if link_hash == None and link_name != None:
                link_hash = hsh(link_name)
            if data_hash == None and link_hash != None:
                data_hash = read_storage(LINK_DIR, link_hash)
            link_name, link_hash = new_link_name, hsh(new_link_name)

    # need old elements?
    if link_hash == None and link_name != None:
        link_hash = hsh(link_name)
    if data_hash == None and link_hash != None:
        data_hash = read_storage(LINK_DIR, link_hash)
    if append or output in ('html', 'raw'):
        if data == None and data_hash != None:
            data = read_storage(STORAGE_DIR, data_hash)

    # switch to new data
    if new_data != None:
        if append: # need old data
            new_data = (data or "") + new_data
        if len(new_data) > FILE_SIZE_MAX:
            return mod_python.apache.HTTP_REQUEST_ENTITY_TOO_LARGE
        new_data_hash = hsh(new_data)
        if not is_storage(STORAGE_DIR, new_data_hash):
            write_storage(STORAGE_DIR, new_data_hash, new_data)
        data, data_hash  = new_data, new_data_hash

    # update link?
    if new_link_name != None or new_data != None:
        if link_hash != None and data_hash != None:
            write_storage(LINK_DIR, link_hash, data_hash)

    # update browser url?
    if output == 'html':
        if new_link_name and data_hash:
            mod_python.util.redirect(req, "%s%s" % (BASE_PATH, link_name), link_name)
            return mod_python.apache.OK
        if not link_name and new_data:
            mod_python.util.redirect(req, "%s%s" % (BASE_PATH, data_hash), data_hash)
            return mod_python.apache.OK

    #output
    req.content_type = "text/plain; charset=utf-8"
    text = []
    out = text.append
    if output == 'default':
        if agent == 'text':
            if new_link_name and not data_hash:
                return mod_python.apache.HTTP_BAD_REQUEST
        else:
            output = 'html'
    if output == 'html':
        req.content_type = "text/html; charset=utf-8"
        out('<!DOCTYPE html>\n\n<html>\n<head>')
        out('<meta http-equiv="Content-Type" content="text/html; charset=utf-8">')
        out('<link rel="stylesheet" type="text/css" href="%s.artwork/hsh-link.css">' % BASE_URL)
        out('<script src="%s.artwork/hsh-link.js"></script>' % BASE_URL)
        out('<title>%s</title>\n</head>' % BASE_URL)
        out('<body onLoad="body_loaded()">\n<div class="container">')
        out('<form action="%s" method="POST" enctype="multipart/form-data">' % \
            (link_name or BASE_PATH))
        out('<div class="text"><textarea placeholder="Start typing ..." cols="81" rows="24" name="content" oninput="data_modified()">%s</textarea></div>' % (data or ""))
        out('<div class="control"><a href="%s" title="start from scratch/">clear</a> | ' % BASE_PATH)
        out('%s: <input type="text" placeholder="add a name" name="link" oninput="data_modified()" value="%s">' %
            (link_name and ('<a href="%s%s" title="variable named link">symlink</a>' % (BASE_PATH, link_name)) or "symlink", link_name or ""))
        if data_hash:
            short_hash, css_hide = uniq_name(STORAGE_DIR, data_hash), ''
        else:
            short_hash, css_hide = '', ' style="visibility: hidden;"'
        out('<a href="%s%s" title="immutable hash: %s%s"%s>permalink</a>' % (BASE_PATH, data_hash, BASE_URL, data_hash, css_hide))
        out('<a href="%s%s" title="immutable hash: %s%s"%s>short</a>' % (BASE_PATH, short_hash, BASE_URL, short_hash, css_hide))
        if data_hash:
            out('<input type="hidden" name="prev" value="%s">' % data_hash)
        out(' | output: <select name="output" id="output" onchange="output_selected()">')
        for output_ in OUTPUT:
            out('<option value="%s"%s>%s</option>' % (output_, output == output_ and ' selected' or '', output_))
        out('</select><input type="submit" id="store"'
                    ' title="safe changed data" value="save"></div></form>')
        out('<div class="footer">(c) <a href="http://xmw.de/">xmw.de</a> 2014 '
            '<a href="https://github.com/xmw/hsh-link">sources</a> '
            '<a href="http://validator.w3.org/check?uri=referer">html5</a> '
            '<a href="http://jigsaw.w3.org/css-validator/check/referer">css3</a> '
            '</div>\n</div>\n</body>\n</html>\n')
    elif output == 'qr_png':
        import qrencode, PIL.ImageOps
        ver, s, img = qrencode.encode(BASE_URL + (link_name or data_hash or ''), 
            level=qrencode.QR_ECLEVEL_L, hint=qrencode.QR_MODE_8, case_sensitive=True)
        img = PIL.ImageOps.expand(img, border=1, fill='white')
        img = img.resize((s * 8, s * 8), PIL.Image.NEAREST)
        req.content_type = "image/png; charset=utf-8"
        img.save(req, 'PNG')
    elif output == 'qr_ascii':
        import qr_encode
        v, s, img = qr_encode.encode(BASE_URL + (link_name or data_hash or ''), 0, 0, 2, True)
        sym = lambda p: ('  ', '@@')[ord(p)/255]
        out('@@' * (s + 2))
        for y in range(s):
            out('@@' + ''.join(map(sym, img[y*s:(y+1)*s])) + '@@')
        out('@@' * (s + 2))
        out('')
    elif output == 'qr_utf8':
        import qr_encode
        v, s, img = qr_encode.encode(BASE_URL + (link_name or data_hash or ''), 0, 0, 2, True)
        sym = lambda (u, l): ((' ', '▄') , ('▀', '█'))[ord(u)/255][ord(l)/255]
        img = '\xff'*s + img + '\xff'*s + '\xff'*s
        for y in range((s + 1) / 2 + 1):
            out('█' + ''.join(map(sym, zip(
                img[(y*2)*s:(y*2+1)*s],img[(y*2+1)*s:(y*2+2)*s]))) + '█')
        out('')
    elif output == 'raw':
        req.content_type = ''
        out(data)
    elif output == 'link':
        if not data_hash:
            return mod_python.apache.HTTP_NOT_FOUND
        out("%s%s\n" % (BASE_URL, data_hash))
    elif output == 'short':
        if not data_hash:
            return mod_python.apache.HTTP_NOT_FOUND
        out("%s%s\n" % (BASE_URL, uniq_name(STORAGE_DIR, data_hash)))
    req.write("\n".join(text))
    return mod_python.apache.OK
