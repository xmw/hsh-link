# vim: tabstop=4
# vim: set fileencoding=utf-8
# copyright Michael Weber (michael at xmw dot de) 2014

from config import STORAGE_DIR, LINK_DIR, FILE_SIZE_MAX, MIME_ALLOWED, BASE_PROTO, BASE_PATH, COOKIE_SECRET, THEMES
OUTPUT = 'raw', 'html', 'link', 'short', 'qr', 'qr_png', 'qr_utf8', 'qr_ascii'

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

def get_link_history(link, ret=None):
    data = read_storage(LINK_DIR, hsh(link))
    if data:
        ret = []
        for line in data.rstrip('\n').split('\n'):
            rev_, hash_ = line.split('\t', 1)
            ret.append((int(rev_), hash_))
    return ret

def get_link(link, rev=None, ret=(None, None)):
    data = get_link_history(link)
    if data:
        if rev != None:
            for (rev_, data_) in data[::-1]:
                if rev_ == rev:
                    return rev_, data_
        else:
            return data[-1]
    return ret

def append_link_history(link, data_hash):
    hist = get_link_history(link, [])
    if len(hist):
        num = hist[-1][0] + 1
    else:
        num = 0
    hist.append((num, data_hash))
    write_storage(LINK_DIR, hsh(link),
        '\n'.join(map(lambda s: '%i\t%s' % (s[0], s[1]), hist)) + '\n')
    return num

def find_storage(repo, partfn):
    d, partfn = subdirfn(repo, partfn)
    if not os.path.exists(d):
        return None
    cand = list(filter(lambda s: s.startswith(partfn), os.listdir(d)))
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
    elif len(s) == 8:
        return ipaddress.ip_address('.'.join(map(lambda s: str(int(s, 16)),
        ('{6}{7}.{4}{5}.{2}{3}.{0}{1}'.format(*s)).split('.'))))
    else:
        raise ValueError("Unsupported IP address length")
    
def is_mptcp(req):
    ip = ipaddress.ip_address(req.subprocess_env['REMOTE_ADDR'])
    port = int(req.subprocess_env['REMOTE_PORT'])
    for line in open('/proc/net/mptcp', 'r').readlines()[1:]:
        mp_ip, mp_port = line.split()[5].split(':')
        if ip == mptcp2ipaddress(mp_ip) and port == int(mp_port, 16):
            return True
    return False


def handler(req):
    debug = []
    err = lambda s: debug.append(str(s) + '<br>')
    path = req.unparsed_uri[len(BASE_PATH):].split('?')[0]
    if path == 'robots.txt' or path.startswith('.artwork/'):
        # fall back to next apache handler
        return mod_python.apache.DECLINED

    if not req.method in ('GET', 'POST', 'PUT'):
        return mod_python.apache.HTTP_BAD_REQUEST

    req.add_common_vars()
    var = mod_python.util.FieldStorage(req)
    def get_last_value(name, ret=None):
        cand = var.getlist(name)
        if len(cand):
            ret = cand[-1].value
        if isinstance(ret, bytes):
            ret = ret.decode()
        return ret

    try:
        rev = int(get_last_value('rev'))
    except TypeError:
        rev=None
    except ValueError:
        return mod_python.apache.HTTP_BAD_REQUEST

    # understand path, link+revision
    link = get_last_value('link') or None # empty form input
    if link:
        rev, data_hash = get_link(link, rev, get_link(link))
    else:
        if len(path) == 0:
            data_hash = hsh('')
        elif is_storage(STORAGE_DIR, path):
            data_hash = path
        elif get_link(path)[1]:
            link = path
            rev, data_hash = get_link(link, rev, get_link(link))
        elif find_storage(STORAGE_DIR, path):
            data_hash = find_storage(STORAGE_DIR, path)
        else:
            return mod_python.apache.HTTP_NOT_FOUND

    # load data
    data = read_storage(STORAGE_DIR, data_hash or '') or ''

    # handle new data
    if req.method == 'PUT':
        content = req.read()
    else:
        content = get_last_value('content', None)
        if req.method == 'POST':
            if get_last_value('linefeed') == 'unix':
                content = content.replace('\r\n', '\n')
    if content != None:
        if get_last_value('append') in (None, '0'):
            data = ''
        data = data + content
        if len(data) > FILE_SIZE_MAX:
            return mod_python.apache.HTTP_REQUEST_ENTITY_TOO_LARGE
        data_hash = hsh(data)
        if not is_storage(STORAGE_DIR, data_hash):
            if clamav and clamav.scan_stream(data.encode()):
                return mod_python.apache.HTTP_FORBIDDEN
            write_storage(STORAGE_DIR, data_hash, data)

    #update link
    if link != None and data_hash != None:
        if data_hash != get_link(link, rev)[1]:
            rev = append_link_history(link, data_hash)

    #guess output format
    agent = req.headers_in.get('User-Agent', '').lower()
    if list(filter(lambda a: agent.count(a), ('mozilla', 'opera', 'validator', 'w3m', 'lynx', 'links'))):
        agent, output = 'graphic', 'html'
    else:
        agent, output = 'text', 'raw'
        if content:
            output = 'link'
    output = get_last_value('output', output)
    if output == 'qr':
        output = agent == 'graphic' and 'qr_png' or 'qr_utf8'

    # update browser url?
    BASE_URL = BASE_PROTO + req.headers_in['Host'] + BASE_PATH
    if get_last_value('output', 'html') == 'html':
        if link == None:
            short_hash = uniq_name(STORAGE_DIR, data_hash)
            if path != data_hash and path != short_hash:
                mod_python.util.redirect(req, "%s%s" % (BASE_URL, short_hash),
                    text="%s%s\n" % (BASE_URL, data_hash))
        else:
            if path != link:
                mod_python.util.redirect(req, "%s%s" % (BASE_URL, link),
                    text="%s%s\n" % (BASE_URL, data_hash))

    # url shortener and mime magic
    if not req.headers_in.get('referer', '').startswith(BASE_URL):
        m = re.compile('^(?:http|https|ftp)://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+$')
        if m.match(data):
            mod_python.util.redirect(req, data.rstrip(), permanent=True, text=data)
            return mod_python.apache.OK
        m = magic.Magic(magic.MAGIC_MIME).from_buffer(data).decode()
        if m.startswith('image/') or m == 'application/pdf':
            output = 'raw'

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
        out('<form action="%s" method="POST" enctype="multipart/form-data">'
            % BASE_PATH)
        out('<div class="control"><a href="%s" title="start from scratch">clear</a>' % BASE_PATH)
        short_hash = data_hash and uniq_name(STORAGE_DIR, data_hash)
        out('<a title="short hash of content: %s" href="%s%s">short</a>'
            % (short_hash, BASE_PATH, short_hash))
        out('<a title="long hash of content: %s" href="%s%s">long</a>'
            % (data_hash, BASE_PATH, data_hash))

        if link:
            out('link=<a title="latest revision of link: %s" '
                'href="%s%s">%s</a>' % (link, BASE_PATH, link, link))
            out('<input type="hidden" name="link" value="%s">' % link)
            if get_link(link, rev - 1, None):
                out('rev=<a title="previous revision of link: %s" '
                    'href="?rev=%s">-</a>' % (rev - 1, rev - 1))
            else:
                out('rev=&nbsp;')
            out('<a title="current revision of link: %s" '
                'href="?rev=%i">%i</a>' % ( rev, rev, rev ))
            if get_link(link, rev + 1, None):
                out('<a title="next revision of link: %s" '
                    'href="?rev=%s">+</a>' % (rev + 1, rev + 1))
            else:
                out('&nbsp;')
        else:
            out('link=<input type="text" placeholder="add a tag/symlink ..." '
                'name="link" class="link" value="">')
        out('linefeed=<select name="linefeed" id="linefeed" '
            'onchange="data_modified()">')
        lf = (data and data.count('\r\n')) and ('', ' selected') or (' selected', '')
        out('<option value="unix"%s>unix</option><option value="dos"%s>dos</option></select>' % lf)
        out(' output=<select name="output" id="output" onchange="output_selected()">')
        for output_ in OUTPUT:
            out('<option value="%s"%s>%s</option>'
                % (output_, output == output_ and ' selected' or '', output_))
        out('</select>')
        out('<input type="submit" id="save" title="save changes" '
            'value="save"> </div>')
        out('<div class="text"><textarea placeholder="Start typing ..." '
            'name="content" id="content" onclick="update_lineno()" '
            'onkeyup="update_lineno()" oninput="data_modified()">%s</textarea>'
            '</div>' % data)
        out('<div class="footer">(c) <a href="http://xmw.de/">xmw.de</a> 2014 '
            '<a href="https://github.com/xmw/hsh-link">sources</a> '
            '<a href="http://validator.w3.org/check?uri=referer">html5</a> '
            '<a href="http://jigsaw.w3.org/css-validator/check/referer">css3</a> '
            'theme=<a href="?theme=xmw">xmw</a> '
            '<a href="?theme=white">white</a>'
            ' line=<input type="text" name="lineno" '
            'id="lineno" value="" size="4" readonly>')
        out('<a href="http://www.multipath-tcp.org/">mptcp</a>=%s'
            % (is_mptcp(req) and 'yes' or 'no'))
        out('mimetype=%s' % magic.Magic(magic.MAGIC_MIME).from_buffer(data.encode()).decode())
        out('</div></form></div>\n</body>\n</html>\n')
    elif output in ('qr_png', 'qr_ascii', 'qr_utf8'):
        ver, s, img = qrencode.encode(BASE_URL + (link or data_hash or ''),
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
        out(data)
    elif output == 'link':
        out("%s%s\n" % (BASE_URL, data_hash))
    elif output == 'short':
        out("%s%s\n" % (BASE_URL, uniq_name(STORAGE_DIR, data_hash)))
    else:
        return mod_python.apache.HTTP_BAD_REQUEST
    text += debug
    req.write("\n".join(text))
    return mod_python.apache.OK
