set pagination off
set logging file /tmp/gdb.log
set logging on
set breakpoint pending on

# Xserver is signalling start to anaconda via SIGUSR1, we don't want to pause gdb
handle SIGUSR1 nostop

break gtk_widget_queue_resize_on_widget if strcmp(gtk_widget_get_name(widget),"pyanaconda+ui+gui+MainWindow") == 0
commands 1
print gtk_widget_get_name(widget)
print widget
py-bt
bt
continue
end

# break gtk_notebook_buildable_add_child
# print gtk_widget_get_name(buildable)

break g_log_structured if log_level == G_LOG_LEVEL_WARNING
commands 2
py-bt
bt
#continue
detach
quit
end

continue
detach
set logging off
quit
