#!/bin/bash
# parse-anaconda-kickstart.sh: handle kickstart settings

# No need to do this twice.
[ -e /tmp/ks.cfg.done ] && return

# Clear everything.
rm -f /tmp/ks_net /tmp/ks_local

# Process all inst.ks arguments.
# inst.ks provides an "URI" for the kickstart file
for kickstart in $(getargs ks= inst.ks=); do

    if [ -z "$kickstart" ]; then
        getargbool 0 ks inst.ks && kickstart='nfs:auto'
    fi

    case "${kickstart%%:*}" in
        http|https|ftp|nfs|nfs4)
            # Network kickstart files.
            echo $kickstart >> /tmp/ks_net
        ;;
        file|path)
            # Local kickstart files.
            echo $kickstart >> /tmp/ks_local
        ;;
    esac
done

# No root? The kickstart file will probably tell us what our root device is.
[ -e /tmp/ks_local -o -e /tmp/ks_net ] && [ -z "$root" ] && root="anaconda-kickstart"

# Try to get one of the local files.
if [ -f /tmp/ks_local ]; then

    for kickstart in $(cat /tmp/ks_local); do
        # Split the argument.
        # file:<path> or path:<path> (accepted but deprecated)
        splitsep ":" "$kickstart" kstype kspath

        # Does the file exist?
        if [ -f "$kspath" ]; then
            # Parse the file.
            info "anaconda: parsing kickstart $kspath"
            cp $kspath /tmp/ks.cfg
            parse_kickstart /tmp/ks.cfg
            [ "$root" = "anaconda-kickstart" ] && root=""
            > /tmp/ks.cfg.done

            # Export the kickstart variable and return.
            export kickstart
            return
        else
            # Show warnings and continue.
            warn "inst.ks='$kickstart'"
            warn "can't find $kspath!"
        fi
    done
fi

# If no local file was found, we will try the network files later.
if [ -f /tmp/ks_net ]; then

    # Set the variable to the first file on the list.
    kickstart=$(head -n 1 /tmp/ks_net)

    # We need the network.
    set_neednet
fi

# Export the kickstart variable and return.
export kickstart
