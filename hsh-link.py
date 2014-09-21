# vim: tabstop=4
# vim: set fileencoding=utf-8
# copyright Michael Weber (michael at xmw dot de) 2014

from config import STORAGE_DIR, LINK_DIR, FILE_SIZE_MAX, MIME_ALLOWED, BASE_PROTO, BASE_PATH, COOKIE_SECRET, THEMES
OUTPUT = 'default', 'raw', 'html', 'link', 'short', 'qr', 'qr_png', 'qr_utf8', 'qr_ascii'

import base64, hashlib, io, ipaddress, magic, mod_python.util, mod_python.apache, mod_python.Cookie, os, PIL.ImageOps, qrencode, re, time

import fixup

try:
    import pyclamd
    clamav = pyclamd.ClamdAgnostic()
    clamav.ping()
except (ValueError, NameError):
    clamav = None

hsh = lambda s: base64.urlsafe_b64encode(hashlib.sha1(s.encode()).digest()).decode().rstrip('=')

def subdirfn(repo, fn):
    if fn.count('/') or len(fn) < 4:
        return ['', '']
    return os.path.join(repo, fn[0:2], fn[2:4]), fn

def is_storage(repo, fn):
    return os.path.exists(os.path.join(*subdirfn(repo, fn)))

def read_storage(repo, fn):
    fn = os.path.join(*subdirfn(repo, fn))
    if os.path.exists(fn):
        f = open(fn, 'r')
        content = f.read()
        f.close()
        return content
    return None

def write_storage(repo, fn, data):
    d, fn = subdirfn(repo, fn)
    if not os.path.exists(d):
        os.makedirs(d, mode=0o770)
    f = open(os.path.join(d, fn), 'w')
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

def mptcp2ipaddress(s):
    if len(s) == 32:
        return ipaddress.ip_address((
                '{06}{07}{04}{05}:{02}{03}{00}{01}:' +
                '{14}{15}{12}{13}:{10}{11}{08}{09}:' +
                '{22}{23}{20}{21}:{18}{19}{16}{17}:' +
                '{30}{31}{28}{29}:{26}{27}{24}{25}' ).format(*s))
    else:
        return ipaddress.ip_address('.'.join(map(lambda s: str(int(s, 16)),
        ('{6}{7}.{4}{5}.{2}{3}.{0}{1}'.format(*s)).split('.'))))
    
def is_mptcp(req):
    ip = ipaddress.ip_address(req.subprocess_env['REMOTE_ADDR'])
    port = int(req.subprocess_env['REMOTE_PORT'])
    for line in open('/proc/net/mptcp', 'r').readlines()[1:]:
        mp_ip, mp_port = line.split()[5].split(':')
        if ip == mptcp2ipaddress(mp_ip) and port == int(mp_port, 16):
            return True
    return False

def handler(req):
    req.add_common_vars()
    var = mod_python.util.FieldStorage(req)
    def get_last_value(name, default=None):
        ret = var.getlist(name) and var.getlist(name)[-1].value or default
        if isinstance(ret, bytes):
            ret = ret.decode()
        return ret

    #var = mod_python.util.FieldStorage(req, keep_blank_values=True)
    BASE_URL = BASE_PROTO + req.headers_in['Host'] + BASE_PATH

    #guess output format
    output = 'default'
    agent = req.headers_in.get('User-Agent', '').lower()
    if list(filter(lambda a: agent.count(a), ('mozilla', 'opera', 'validator', 'w3m', 'lynx', 'links'))):
        agent = 'graphic'
    else:
        agent = 'text'
    output = get_last_value('output', output)
    if not output in OUTPUT:
        return mod_python.apache.HTTP_BAD_REQUEST
    if output == 'qr':
        if agent == 'graphic':
            output = 'qr_png'
        else:
            output = 'qr_utf8'

    # new_content
    if req.method == 'DELETE':
        req.write("DELETE not yet implented.\n")
        return mod_python.apache.HTTP_BAD_REQUEST
    elif req.method == 'PUT':
        new_data = req.read()
    elif req.method == 'GET':
        new_data = get_last_value('content')
    elif req.method == 'POST':
        new_data = get_last_value('content')
    else:
        return mod_python.apache.HTTP_BAD_REQUEST
    # append
    append = get_last_value('append')

    new_link_name = get_last_value('link')

    # data_hash, link_name or abrev. data_hash
    data, data_hash, link_name, link_hash = None, None, None, None
    #obj = req.uri[len(BASE_PATH):]
    obj = req.unparsed_uri[len(BASE_PATH):].split('?')[0]
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

    # wait for data or update of link
    if get_last_value('wait') != None:
        data_hash = read_storage(LINK_DIR, link_hash)
        ref = data_hash
        while ref == data_hash:
            time.sleep(1)
            data_hash = read_storage(LINK_DIR, link_hash)

    # url shortener, mime image magic
    if output == 'default' and link_name == None:
        if data_hash != None and data == None:
            data = read_storage(STORAGE_DIR, data_hash)
        if data != None and not req.headers_in.get('referer', '').startswith(BASE_URL):
            m = re.compile('^(?:http|https|ftp)://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+$')
            if m.match(data):
                mod_python.util.redirect(req, data.rstrip(), permanent=True, text=data)
            m = magic.Magic(magic.MAGIC_MIME).from_buffer(data).decode()
            if m.startswith('image/') or m == 'application/pdf':
                output = 'raw'

    if output == 'default':
        if agent == 'text':
            if new_link_name and not data_hash and not new_data:
                return mod_python.apache.HTTP_NOT_FOUND
            if new_link_name or new_data:
                output = 'link'
            else:
                output = 'raw'
        else:
            output = 'html'

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
        if get_last_value('linefeed') == 'unix':
            new_data = new_data.replace('\r\n', '\n')
        new_data_hash = hsh(new_data)
        if not is_storage(STORAGE_DIR, new_data_hash):
            if clamav and clamav.scan_stream(new_data.encode()):
                return mod_python.apache.HTTP_FORBIDDEN
            write_storage(STORAGE_DIR, new_data_hash, new_data)
        data, data_hash  = new_data, new_data_hash

    # update link?
    if new_link_name != None or new_data != None:
        if link_hash != None and data_hash != None:
            write_storage(LINK_DIR, link_hash, data_hash)

    # update browser url?
    if output == 'html':
        if new_link_name and data_hash:
            mod_python.util.redirect(req, "%s%s" % (BASE_URL, link_name))
            return mod_python.apache.OK
        if not link_name and new_data:
            mod_python.util.redirect(req, "%s%s" % (BASE_PATH, data_hash))
            return mod_python.apache.OK

    #output
    req.content_type = "text/plain; charset=utf-8"
    text = []
    out = text.append
    if output == 'html':
        # handle theme
        theme = THEMES[0]
        cookie = mod_python.Cookie.get_cookie(req, 'theme', mod_python.Cookie.MarshalCookie, secret=COOKIE_SECRET)
        if type(cookie) is mod_python.Cookie.MarshalCookie:
            if cookie.value in THEMES:
                theme = cookie.value
        if get_last_value('theme') in THEMES:
            theme = get_last_value('theme')
            cookie = mod_python.Cookie.MarshalCookie('theme', theme, secret=COOKIE_SECRET)
            cookie.expires = time.time() + 86400 * 365
            mod_python.Cookie.add_cookie(req, cookie)

        req.content_type = "text/html; charset=utf-8"
        out('<!DOCTYPE html>\n\n<html>\n<head>')
        out('<meta http-equiv="Content-Type" content="text/html; charset=utf-8">')
        out('<link rel="stylesheet" type="text/css" href="%s.artwork/hsh-link-%s.css">' % (BASE_PATH, theme))
        out('<script src="%s.artwork/hsh-link.js"></script>' % BASE_PATH)
        out('<title>%s</title>\n</head>' % BASE_URL)
        out('<body onLoad="body_loaded()">\n<div class="container">')
        out('<form action="%s%s" method="POST" enctype="multipart/form-data">' % \
            (BASE_URL, link_name or ''))
        out('<div class="control"><a href="%s" title="start from scratch/">clear</a> | ' % BASE_PATH)
        link_text_ = 'symlink'
        if link_name:
            link_text_ = '<a href="%s%s">symlink</a>' % (BASE_URL, link_name)
        out('%s=<input type="text" placeholder="add a name" name="link" oninput="data_modified()" value="%s">' % (link_text_, link_name or ""))
        if data_hash:
            short_hash, css_hide = uniq_name(STORAGE_DIR, data_hash), ''
        else:
            short_hash, css_hide = '', ' style="visibility: hidden;"'
        out('<a href="%s%s" title="immutable hash: %s%s"%s>permalink</a>' % (BASE_PATH, data_hash or "", BASE_URL, data_hash or "", css_hide))
        out('<a href="%s%s" title="immutable hash: %s%s"%s>short</a>' % (BASE_PATH, short_hash, BASE_URL, short_hash, css_hide))
        if data_hash:
            out('<input type="hidden" name="prev" value="%s">' % data_hash)
        out(' linefeed=<select name="linefeed" id="linefeed" onchange="data_modified()">')
        lf = (data and data.count('\r\n')) and ('', ' selected') or (' selected', '')
        out('<option value="unix"%s>unix</option><option value="dos"%s>dos</option></select>' % lf)
        out(' output=<select name="output" id="output" onchange="output_selected()">')
        for output_ in OUTPUT:
            out('<option value="%s"%s>%s</option>' % (output_, output == output_ and ' selected' or '', output_))
        out('</select><input type="submit" id="store"'
                    ' title="save changed data" value="save"></div>')
        out('<div class="text"><textarea placeholder="Start typing ..." name="content" id="content" onclick="update_lineno()" onkeyup="update_lineno()" oninput="data_modified()">%s</textarea></div>' % (data or ""))
        out('<div class="footer">(c) <a href="http://xmw.de/">xmw.de</a> 2014 '
            '<a href="https://github.com/xmw/hsh-link">sources</a> '
            '<a href="http://validator.w3.org/check?uri=referer">html5</a> '
            '<a href="http://jigsaw.w3.org/css-validator/check/referer">css3</a> '
            'theme=<a href="?theme=xmw">xmw</a> '
            '<a href="?theme=white">white</a>'
            ' line=<input type="text" name="lineno" id="lineno" value="" size="4" readonly>')
        out('<a href="http://www.multipath-tcp.org/">mptcp</a>=<a href="http://cdn.meme.am/instances/500x/54513486.jpg">%s</a>'
            % (is_mptcp(req) and 'yes' or 'no'))
        out('</div></form></div>\n</body>\n</html>\n')
    elif output in ('qr_png', 'qr_ascii', 'qr_utf8'):
        ver, s, img = qrencode.encode(BASE_URL + (link_name or data_hash or ''), 
            level=qrencode.QR_ECLEVEL_L, hint=qrencode.QR_MODE_8, case_sensitive=True)
        img = PIL.ImageOps.expand(img, border=1, fill='white')
        if output == 'qr_png':
            img = img.resize((s * 8, s * 8), PIL.Image.NEAREST)
            req.content_type = "image/png; charset=utf-8"
            img.save(req, 'PNG')
        elif output == 'qr_ascii':
            sym = ('  ', '@@')
            for y in range(img.size[1]):
                out(''.join(map(lambda x: sym[img.getpixel((x,y)) != 0], range(img.size[0]))))
            out('')
        elif output == 'qr_utf8':
            sym = (' ', '▄') , ('▀', '█')
            for y in range(img.size[1]//2):
                out(''.join(map(lambda x: sym[img.getpixel((x,y*2)) != 0][img.getpixel((x,y*2+1)) != 0], range(img.size[0]))))
            if img.size[1] % 2:
                out(''.join(map(lambda x: sym[img.getpixel((x,img.size[1]-1)) != 0][0], range(img.size[0]))))
            out('')
    elif output == 'raw':
        req.content_type = ''
        if not data:
             return mod_python.apache.HTTP_NOT_FOUND
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
