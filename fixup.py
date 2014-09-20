import base64, hmac, marshal, mod_python.util, mod_python.Cookie
from mod_python.Cookie import CookieError, PY2

def fixup(self, value):
    try:
        if isinstance(value, str):
            return bytes.__new__(self, value.encode())
        else:
            return bytes.__new__(self, value)
    except:
        raise ValueError(str(type(value)))
mod_python.util.StringField.__new__ = fixup

def fixup2(self):
    m = base64.encodestring(marshal.dumps(self.value))
    # on long cookies, the base64 encoding can contain multiple lines
    # separated by \n or \r\n
    if isinstance(m, bytes):
        m = m.decode()
    m = ''.join(m.split())

    result = ["%s=%s%s" % (self.name, self.hexdigest(m), m)]
    for name in self._valid_attr:
        if hasattr(self, name):
            if name in ("secure", "discard", "httponly"):
                result.append(name)
            else:
                result.append("%s=%s" % (name, getattr(self, name)))
    return "; ".join(result)
mod_python.Cookie.MarshalCookie.__str__ = fixup2

def fixup3(self, str):
    import hmac
    if not self.__data__["secret"]:
        raise CookieError("Cannot sign without a secret")
    if PY2:
        _hmac = hmac.new(self.__data__["secret"], self.name)
        _hmac.update(str)
    else:
        _hmac = hmac.new(self.__data__["secret"].encode(), self.name.encode())
        _hmac.update(str.encode())
    return _hmac.hexdigest()
mod_python.Cookie.SignedCookie.hexdigest = fixup3

def fixup4(self, secret):
    import hmac
    sig, val = self.value[:32], self.value[32:]
    
    if PY2:
        mac = hmac.new(secret, self.name)
        mac.update(val)
    else:
        mac = hmac.new(secret.encode(), self.name.encode())
        mac.update(val.encode())

    if mac.hexdigest() == sig:
        self.value = val
        self.__data__["secret"] = secret
    else:
        raise mod_python.Cookie.CookieError("Incorrectly Signed Cookie: %s=%s" % (self.name, self.value))
mod_python.Cookie.SignedCookie.unsign = fixup4

def fixup5(self, secret):

    self.unsign(secret)

    try:
        if PY2:
            data = base64.decodestring(self.value)
        else:
            data = base64.decodestring(self.value.encode())
    except:
        raise mod_python.Cookie.CookieError("Cannot base64 Decode Cookie: %s=%s" % (self.name, self.value))

    try:
        self.value = marshal.loads(data)
    except (EOFError, ValueError, TypeError):
        raise CookieError("Cannot Unmarshal Cookie: %s=%s" % (self.name, self.value))
mod_python.Cookie.MarshalCookie.unmarshal = fixup5

