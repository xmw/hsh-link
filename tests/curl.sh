#!/bin/zsh

URL='dev.hsh.link/'
alias curl="curl --silent"

echo -n "up&down fixed string (POST): "
up=$(date -I)
link=$(curl -F "content=$up" $URL)
down=$(curl $link)
[ "$up" = "$down" ] && echo pass || echo "fail up=>$up<, link=>$link<, down=>$down<"

echo -n "up&down fixed string again (POST): "
up=$(date -I)
link=$(curl -F "content=$up" $URL)
down=$(curl $link)
[ "$up" = "$down" ] && echo pass || echo "fail up=>$up<, link=>$link<, down=>$down<"

echo -n "up&down random string (POST): "
up=$(date)
link=$(curl -F "content=$up" $URL)
down=$(curl $link)
[ "$up" = "$down" ] && echo pass || echo "fail up=>$up<, link=>$link<, down=>$down<"

echo -n "up&down random string (GET): "
up=$(date)b
link=$(curl -G --data-urlencode "content=$up" $URL)
down=$(curl $link)
[ "$up" = "$down" ] && echo pass || echo "fail up=>$up<, link=>$link<, down=>$down<"

echo -n "define symlink on existing data (POST): "
sym=$(date +%s)
link2=$(curl -F "link=$sym" $link)
down=$(curl $URL$sym)
[ "$up" = "$down" -a "$link" = "$link2" ] && echo pass || echo "fail up=>$up<, link2=>$link2<, down=>$down<, link=>$link<"

echo -n "define symlink on existing data (GET): "
sym=$(date +%s)b
link2=$(curl -G -d "link=$sym" $link)
down=$(curl $URL$sym)
[ "$up" = "$down" -a "$link" = "$link2" ] && echo pass || echo "fail up=>$up<, link2=>$link2<, down=>$down<, link=>$link<"

echo -n "define symlink on identical data (POST): "
sym=$(date +%s)c
link2=$(curl -F "link=$sym" -F "content=$up" $URL)
down=$(curl $URL$sym)
[ "$up" = "$down" -a "$link" = "$link2" ] && echo pass || echo "fail up=>$up<, link2=>$link2<, down=>$down<, link=>$link<"

echo "output as raw"
curl -G -d output=raw $URL$sym
echo
echo "output as html"
curl -G -d output=html $URL$sym | wc
echo "output as link"
curl -G -d output=link $URL$sym
echo "output as qr utf-8 art"
curl -G -d output=qr $URL$sym
echo "output as qr png"
curl -A Mozilla -G -d output=qr $URL$sym | wc

