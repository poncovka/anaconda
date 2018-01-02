set pagination off
set logging file /tmp/gdb.log
set logging on
set breakpoint pending on

# Xserver is signalling start to anaconda via SIGUSR1, we don't want to pause gdb
handle SIGUSR1 nostop

handle SIGSEGV

continue
detach
set logging off
quit