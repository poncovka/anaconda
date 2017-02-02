#!/bin/bash
# fetch-kickstart-net - fetch kickstart file from the network.
# runs from the "initqueue/online" hook whenever a net interface comes online

# initqueue/online hook passes interface name as $1
netif="$1"

# We already processed the kickstart - exit.
[ -e /tmp/ks.cfg.done ] && return 0

# No network kickstart requested - exit.
[ -e /tmp/ks_net ] || return 0

# User requested a specific device, but this isn't it - exit.
[ -n "$ksdevice" ] && [ "$ksdevice" != "$netif" ] && return 0

command -v getarg >/dev/null || . /lib/dracut-lib.sh
. /lib/url-lib.sh
. /lib/anaconda-lib.sh

# Try to get one of the network files.
for kickstart in $(cat /tmp/ks_net); do

    # NFS auto
    if [ "$kickstart" = "nfs:auto" ]; then
        # Server is next_server, or the dhcp server itself if missing.
        . /tmp/net.$netif.dhcpopts
        server="${new_next_server:-$new_dhcp_server_identifier}"

        # Filename is dhcp 'filename' option, or '/kickstart/' if missing.
        filename="/kickstart/"

        # Read the dhcp lease file and see if we can find 'filename'.
        { while read line; do
            val="${line#filename }"
            if [ "$val" != "$line" ]; then
                eval "filename=$val" # drop quoting and semicolon
            fi
          done
        } < /tmp/net.$netif.lease

        # Construct kickstart URL from dhcp info.
        kickstart="nfs:$server:$filename"
    fi

    # NFS
    case "$kickstart" in
        # NFS kickstart URLs that end in '/' get '$IP_ADDR-kickstart' appended
        nfs*/) kickstart="${kickstart}${new_ip_address}-kickstart" ;;
    esac

    # If we're doing sendmac, we need to run after anaconda-ks-sendheaders.sh
    if getargbool 0 inst.ks.sendmac kssendmac; then
        newjob=$hookdir/initqueue/settled/fetch-ks-${netif}.sh
    else
        newjob=$hookdir/initqueue/fetch-ks-${netif}.sh
    fi

    cat > $newjob <<__EOT__
    . /lib/url-lib.sh
    . /lib/anaconda-lib.sh
    info "anaconda fetching kickstart from $kickstart"
    if fetch_url "$kickstart" /tmp/ks.cfg; then
        parse_kickstart /tmp/ks.cfg
        run_kickstart
        break
    else
        warn "failed to fetch kickstart from $kickstart"
    fi
    rm \$job # remove self from initqueue
    __EOT__
done
