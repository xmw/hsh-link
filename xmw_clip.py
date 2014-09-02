# vim: tabstop=4
# copyright Michael Weber (michael at xmw dot de) 2014


#from re import match
#from urllib import unquote
from mod_python import apache, util
#from mod_python.util import redirect

from config import STORAGE_DIR

import hashlib, os


get_query = lambda req, key: dict(map(lambda s: s.split('=', 1), req.args.split('&'))).get(key, None)
remote_inet = lambda req: req.get_remote_host(apache.REMOTE_NOLOOKUP, True)[0]

def encapsulate(req, raw, html=False):
    if html:
        req.content_type = "text/html; charset=utf-8"
        req.write('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" ' + \
            '"http://www.w3.org/TR/html4/loose.dtd">\n')
        req.write('<HTML>\n<HEAD>\n<META http-equiv="Content-Type" content="text/html; charset=utf-8">\n')
        req.write('<TITLE>%s</TITLE>\n</HEAD>\n<BODY>\n<CENTER>' % req.headers_in['Host'])
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
    
    create = False
    agent = req.headers_in.get('User-Agent', '').lower()
    html = agent.count('mozilla') or agent.count('opera') or agent.count('validator')

    #lookup
    obj = os.path.normpath(req.uri)[1:]
    if not obj:
        encapsulate(req, "add clipboard name as URI path!\n", html)
        return apache.OK

    fn = os.path.join(STORAGE_DIR, obj)
    if not os.path.exists(fn):
        obj = hashlib.sha1(obj).hexdigest()
        fn = os.path.join(STORAGE_DIR, obj)

    # update action
    new_content = None
    if req.method == 'GET':
        if req.args:
            get = util.FieldStorage(req, keep_blank_values=True)
            if get.getlist('raw'):
                html = False
            new_content = get.getfirst('content')
    elif req.method == 'POST':
        get = util.FieldStorage(req, keep_blank_values=True)
        if get.getlist('raw'):
            html = False
        new_content = get.getfirst('content')
    elif req.method == 'DELETE':
        if os.path.exists(fn):
            os.unlink(fn)
    else:
        encapsulate(req, "Invalid method!\n", html)
        return apache.OK
    
    if new_content:
            write_storage(fn, new_content)

    #read
    content = read_storage(fn) or ""

    #output
    if html:
        encapsulate(req, """%s
<FORM method="POST" action="%s"><BR>
  <TEXTAREA name="content">%s</TEXTAREA><BR>
  <INPUT type="submit" value="update"><INPUT type="reset" value="reset">
</FORM>""" % (content and obj or "new clipboard", req.uri, content), True)
    else:
        encapsulate(req, content, html)

    return apache.OK
