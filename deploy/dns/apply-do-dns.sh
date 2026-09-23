#!/bin/sh
# Create the nexuscanon.com zone on DigitalOcean DNS from
# nexuscanon.com.records, next to this script. Needs an authenticated doctl
# (`doctl auth init`).
#
#   ./apply-do-dns.sh <droplet-ipv4>
#
# Additive and rerunnable: the domain is created only if it is absent, and a
# record is created only if no record with the same type, name and data
# exists. It never deletes or changes a record; a clash (say an A record for
# the same name with another address) is reported for an operator to resolve.
#
# doctl flags, per docs.digitalocean.com/reference/doctl/reference/compute/
# domain/records/create/: --record-type, --record-name, --record-data,
# --record-priority (MX), --record-ttl, and for CAA --record-flags and
# --record-tag, with the authority domain alone in --record-data. The API
# refuses an issue value without its trailing dot (422 "Data needs to be a
# FQDN"), so the records file writes letsencrypt.org. and the comparison below
# ignores that dot either way.
set -eu

DOMAIN=nexuscanon.com
RECORDS="$(cd "$(dirname "$0")" && pwd)/$DOMAIN.records"
TAB=$(printf '\t')

ip=${1:-}
[ -n "$ip" ] || { echo "usage: $0 <droplet-ipv4>" >&2; exit 2; }
# Four dot-separated decimal octets, each 0-255, no leading zeros.
octet='(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])'
printf '%s\n' "$ip" | grep -Eqx "$octet\.$octet\.$octet\.$octet" \
    || { echo "apply-do-dns: '$ip' is not an IPv4 address" >&2; exit 2; }

command -v doctl >/dev/null 2>&1 || { echo "apply-do-dns: doctl is not installed" >&2; exit 1; }
[ -r "$RECORDS" ] || { echo "apply-do-dns: cannot read $RECORDS" >&2; exit 1; }

# A trailing dot and the zone's own name are spellings of the same data.
DOMAIN_RE=$(printf '%s' "$DOMAIN" | sed 's/\./\\./g')
normalise() {
    printf '%s' "$1" | sed -e 's/\.$//' -e "s/^$DOMAIN_RE\$/@/"
}

domains=$(doctl compute domain list --format Domain --no-header)
if printf '%s\n' "$domains" | grep -qx "$DOMAIN"; then
    echo "apply-do-dns: domain $DOMAIN exists"
else
    echo "apply-do-dns: creating domain $DOMAIN"
    doctl compute domain create "$DOMAIN" >/dev/null
fi

# The listing runs on its own so `set -e` stops the script if it fails: sh
# has no pipefail, and an empty listing would re-create every record (a
# second SPF TXT record is a permerror, RFC 7208 section 4.5).
raw=$(doctl compute domain records list "$DOMAIN" --format Type,Name,Data --no-header)

# "type|name|data" per existing record. Data is the last column and may hold
# spaces (TXT), so it is everything after the second field.
existing=$(printf '%s\n' "$raw" \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    | sed -e 's/^\([^[:space:]]*\)[[:space:]][[:space:]]*\([^[:space:]]*\)[[:space:]]*/\1|\2|/' \
    | while IFS= read -r row; do
          printf '%s|%s\n' "$(printf '%s' "$row" | cut -d'|' -f1,2)" \
              "$(normalise "$(printf '%s' "$row" | cut -d'|' -f3-)")"
      done)

created=0
skipped=0
clashes=""
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    type=$(printf '%s\n' "$line" | cut -f1)
    name=$(printf '%s\n' "$line" | cut -f2)
    data=$(printf '%s\n' "$line" | cut -f3 | sed "s/{{DROPLET_IP}}/$ip/g")
    priority=$(printf '%s\n' "$line" | cut -f4)
    ttl=$(printf '%s\n' "$line" | cut -f5)
    case "$data" in *'{{'*) echo "apply-do-dns: unfilled placeholder in: $line" >&2; exit 1 ;; esac

    set -- --record-type "$type" --record-name "$name" --record-ttl "$ttl"
    if [ "$type" = CAA ]; then
        # "<flags> <tag> <value>", value quoted in zone-file style.
        flags=${data%% *}
        rest=${data#* }
        tag=${rest%% *}
        value=$(printf '%s' "${rest#* }" | sed -e 's/^"//' -e 's/"$//')
        set -- "$@" --record-flags "$flags" --record-tag "$tag" --record-data "$value"
        key="CAA|$name|$(normalise "$value")"
    else
        set -- "$@" --record-data "$data"
        [ "$type" = MX ] && set -- "$@" --record-priority "$priority"
        key="$type|$name|$(normalise "$data")"
    fi

    if printf '%s\n' "$existing" | grep -qxF "$key"; then
        echo "  exists   $type $name $data"
        skipped=$((skipped + 1))
        continue
    fi
    if [ "$type" = A ] || [ "$type" = CNAME ]; then
        other=$(printf '%s\n' "$existing" | grep -E "^(A|CNAME)\|$(printf '%s' "$name" | sed 's/\./\\./g')\|" || true)
        [ -z "$other" ] || clashes="$clashes$type $name: also has $(printf '%s' "$other" | tr '\n' ' ')$TAB"
    fi
    # </dev/null: the loop's stdin is the records file, which doctl must not read.
    doctl compute domain records create "$DOMAIN" "$@" </dev/null >/dev/null
    echo "  created  $type $name $data"
    created=$((created + 1))
done < "$RECORDS"

echo "apply-do-dns: $DOMAIN: $created created, $skipped already present, none deleted"
if [ -n "$clashes" ]; then
    echo "apply-do-dns: names that now hold more than one A/CNAME answer; remove the stale one by hand:" >&2
    printf '%s' "$clashes" | tr "$TAB" '\n' | sed 's/^/  /' >&2
fi
