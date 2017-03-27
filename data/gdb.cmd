set pagination off
set logging file /tmp/gdb.log
set logging on
set breakpoint pending on

# Xserver is signalling start to anaconda via SIGUSR1, we don't want to pause gdb
handle SIGUSR1 nostop

#break gtk_notebook_buildable_add_child
#commands 1
#print gtk_widget_get_name(buildable)
#print buildable
#py-bt
#bt
#continue
#end

break g_log_structured if log_level == G_LOG_LEVEL_WARNING
commands 2
py-bt
bt
continue
end

continue
detach
set logging off
quit
