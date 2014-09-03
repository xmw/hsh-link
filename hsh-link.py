# vim: tabstop=4 fileencoding=utf-8
# copyright Michael Weber (michael at xmw dot de) 2014

from config import STORAGE_DIR, LINK_DIR, FILE_SIZE_MAX, MIME_ALLOWED, BASE_PROTO, BASE_HOST, BASE_PATH
BASE_URL = BASE_PROTO + BASE_HOST + BASE_PATH
OUTPUT = 'default', 'raw', 'html', 'link', 'qr'

import base64, hashlib, mod_python.apache, os, qrencode, PIL.ImageOps

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

    # new_content
    if req.method in ('DELETE', 'PUT'):
        req.write("future DELETE and PUT not yet implented.\n")
        return mod_python.apache.HTTP_BAD_REQUEST
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
        if new_link_name:
            mod_python.util.redirect(req, "/%s" % link_name, link_name)
            return mod_python.apache.OK
        if link_name == None and new_data:
            mod_python.util.redirect(req, "/%s" % data_hash, data_hash)
            return mod_python.apache.OK

    #output
    text = []
    if output == 'html':
        req.content_type = "text/html; charset=utf-8"
        text += ["""<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<link rel="stylesheet" type="text/css" href="%s.artwork/hsh-link.css">
<script src="%s.artwork/hsh-link.js"></script>
<title>%s</title>
</head>
<body onLoad="body_loaded()">""" % (BASE_PATH, BASE_PATH, BASE_URL),
        '<div class="container">',
        '<form action="%s" method="POST" enctype="multipart/form-data">' % (link_name or BASE_PATH),
        '<div class="text"><textarea placeholder="Start typing ..." cols="81" rows="24" name="content" oninput="data_modified()">%s</textarea></div>' % (data or ""),
        '<div class="control"><a href="%s" title="start from scratch/">clear</a> | ' % BASE_PATH,
        '%s: <input type="text" placeholder="add a name" name="link" oninput="data_modified()" value="%s">' %
            (link_name and ('<a href="%s%s" title="variable named link">symlink</a>' % (BASE_PATH, link_name)) or "symlink", link_name or "")]
        if data_hash:
            short_hash, css_hide = uniq_name(STORAGE_DIR, data_hash), ''
        else:
            short_hash, css_hide = '', ' style="visibility: hidden;"'
        text.append('<a href="%s%s" title="immutable hash: %s%s"%s>permalink</a>' % (BASE_PATH, data_hash, BASE_URL, data_hash, css_hide))
        text.append('<a href="%s%s" title="immutable hash: %s%s"%s>short</a>' % (BASE_PATH, short_hash, BASE_URL, short_hash, css_hide))
        if data_hash:
            text.append('<input type="hidden" name="prev" value="%s">' % data_hash)
        text.append(' | output: <select name="output" id="output" onchange="output_selected()">')
        for output_ in OUTPUT:
            text.append('<option value="%s"%s>%s</option>' % (output_, output == output_ and ' selected' or '', output_))
        text.append('</select>')
        text.append('<input type="submit" id="store" title="safe changed data" value="save">')
        text.append("""</div>
</form>
<div class="footer">(c) <a href="http://xmw.de/">xmw.de</a> 2014 <a href="https://github.com/xmw/hsh-link">sources</a>
<a href="http://validator.w3.org/check?uri=referer">html5</a></div>
</div>
</body>
</html>
""")
    elif output == 'qr':
        d = BASE_URL + (link_name or data_hash or '')
        version, size, img = qrencode.encode(d, hint=qrencode.QR_MODE_8, case_sensitive=True)
        img = PIL.ImageOps.expand(img, border=1, fill='white')
        if agent == 'graphic':
            req.content_type = "image/png; charset=utf-8"
            img.resize((img.size[0] * 8, img.size[1] * 8), PIL.Image.NEAREST).save(req, 'PNG')
        else:
            req.content_type = "text/plain; charset=utf-8"
            pixels = img.load()
            width, height = img.size
            for row in range(height//2):
                for col in range(width):
                    if pixels[col, row * 2] and pixels[col, row * 2 + 1]:
                        req.write('█')
                    elif pixels[col, row * 2]:
                        req.write('▀')
                    elif pixels[col, row * 2 + 1]:
                        req.write('▄')
                    else:
                        req.write(' ')
                req.write('\n')
            if height % 2:
                for col in range(width):
                    if pixels[col, height-1]:
                        req.write('▀')
                    else:
                         req.write(' ')
                req.write('\n')
    elif output == 'raw':
        req.content_type = "text/plain; charset=utf-8"
        req.write(data)
    elif output == 'link':
        if not data_hash:
            return mod_python.apache.HTTP_NOT_FOUND
        req.content_type = "text/plain; charset=utf-8"
        text.append("%s%s\n" % (BASE_URL, data_hash))
    elif output == 'default':
        if new_data or new_link_name:
            req.content_type = "text/plain; charset=utf-8"
            text.append("%s%s\n" % (BASE_URL, data_hash))
        else:
            if data == None and data_hash != None:
                data = read_storage(STORAGE_DIR, data_hash)
            if data == None:
                return mod_python.apache.HTTP_NOT_FOUND
            req.content_type = "text/plain; charset=utf-8"
            text.append(data)
    req.write("\n".join(text))
    return mod_python.apache.OK
