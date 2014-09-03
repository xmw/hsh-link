hsh.link
========

A minimalistic online clipboard

Features:
  Objects are stored as files named according the contents sha1 hash
  These objects are accessible via permanent links and immutable.
  Updates result in new objects being created.
  Human readable symlinks can be created to link to chain of objects.
  
API
  content=, append= new content to be stored at, appended to location <link>
  uri-path first assumtion for storage location
  link= override storage location, create symlink to mentioned uri-path or content=
  output= specify the output returned to the clien
    html HTML5 with edit capabilities, CSS3 and some javascript.
    raw plain data as "Content-Type: text/plain
    link the url to the (created) symlink or just created hash referende
    qr a qr code representing the "link" either as image/png or utf-8 art
    
Commandline examples
  curl -F content=`date` hsh.link/?output=link
    create new hash, containing current date, no link, return hash link
  curl -F content=`date` hsh.link/foo?output=qr
    create new hash, create or update symlink /foo and return qr code

(c) 2014 Michael Weber http://xmw.de/
