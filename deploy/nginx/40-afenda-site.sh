#!/bin/sh
# Runs from the nginx image's /docker-entrypoint.d before nginx starts.
# Copies the read-only site mount and writes PUBLIC_URL into the page, so the
# two links follow the deployment and no URL is hard-coded in deploy/site/.
set -eu
: "${PUBLIC_URL:?PUBLIC_URL must be set}"
# One trailing slash dropped: the page appends "/request-access" itself.
PUBLIC_URL=${PUBLIC_URL%/}
# `#` is the sed delimiter, `&` and `\` are special in its replacement, and
# `"` would close the href attribute.
case "$PUBLIC_URL" in
    *'#'* | *'&'* | *'\'* | *'"'*)
        echo "40-afenda-site: PUBLIC_URL must not contain #, &, \\ or \": $PUBLIC_URL" >&2
        exit 1
        ;;
esac
rm -rf /usr/share/nginx/site && cp -R /usr/share/nginx/site-src /usr/share/nginx/site
sed -i "s#__PUBLIC_URL__#${PUBLIC_URL}#g" /usr/share/nginx/site/index.html
