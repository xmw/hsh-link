hsh.link
========

A minimalistic online clipboard/pastebin.

## Features
* Objects are stored as files named according the contents SHA1 hash.
  These objects are accessible via permanent links and immutable.
* Updates result in new objects being created.
* Human readable symlinks can be created to link to chain of objects.
  
## API

To upload to hsh.link, use POST requests (GET parameters are ok):

* content=, append= new content to be stored at, resp. appended to location link=
* /uri-path first assumption for storage location
* link= override storage location, create symlink to mentioned uri-path or content=
* output= specify the output returned to the client:
  * `html` HTML5 with edit capabilities, CSS3 and some javascript
  * `raw` plain data as `Content-Type: text/plain`
  * `link` the url just created hash
  * `qr` a QR code representing the "link" either as image/png or UTF-8 art
    
## Commandline examples

Create new hash, containing current date, no link, return hash link:

    curl -F content="`date`" hsh.link/?output=link

Create new hash, create or update symlink /foo and return QR code:

    curl -F content=`date` hsh.link/foo?output=qr



(c) 2014 Michael Weber http://xmw.de/
