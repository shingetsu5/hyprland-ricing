/* GTK3 module for Waybar: forwards only #clock crossing events.
 * Uses GTK's stable C ABI; no Waybar rebuild or development packages required. */
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef void Widget;
typedef unsigned long GType;
extern GType gtk_widget_get_type(void);
extern void *g_type_class_ref(GType);
extern void g_type_class_unref(void *);
extern const char *gtk_widget_get_name(Widget *);
extern Widget *gtk_widget_get_parent(Widget *);
extern Widget *gtk_widget_get_toplevel(Widget *);
extern int gtk_widget_translate_coordinates(Widget *, Widget *, int, int, int *, int *);
extern int gtk_widget_get_allocated_width(Widget *);
extern int gtk_widget_get_allocated_height(Widget *);
extern void *g_value_get_object(const void *);
extern void *g_object_get_data(void *, const char *);
extern void g_object_set_data(void *, const char *, void *);
extern unsigned int g_signal_lookup(const char *, GType);
extern unsigned long g_signal_add_emission_hook(unsigned int, unsigned int,
    int (*)(void *, unsigned int, const void *, void *), void *, void *);
extern unsigned long g_signal_connect_data(void *, const char *, void (*)(void),
    void *, void *, int);
extern void gtk_widget_add_events(Widget *, int);

static void send_event(Widget *clock, const char *kind) {
    const char *runtime = getenv("XDG_RUNTIME_DIR");
    if (!runtime) return;
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (fd < 0) return;
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    int length = snprintf(addr.sun_path, sizeof(addr.sun_path),
                          "%s/waybar-calendar.sock", runtime);
    if (length < 0 || length >= (int)sizeof(addr.sun_path)) { close(fd); return; }
    int x = 0, y = 0;
    gtk_widget_translate_coordinates(clock, gtk_widget_get_toplevel(clock), 0, 0, &x, &y);
    char message[160];
    length = snprintf(message, sizeof(message), "%s %d %d %d %d", kind, x, y,
        gtk_widget_get_allocated_width(clock), gtk_widget_get_allocated_height(clock));
    sendto(fd, message, (size_t)length, MSG_DONTWAIT,
           (struct sockaddr *)&addr, sizeof(addr));
    close(fd);
}
static int entered(Widget *box, void *event, void *clock) {
    (void)box; (void)event; send_event(clock, "enter"); return 0;
}
static int left(Widget *box, void *event, void *clock) {
    (void)box; (void)event; send_event(clock, "leave"); return 0;
}
static int realized(void *hint, unsigned int count, const void *values, void *data) {
    (void)hint; (void)count; (void)data;
    Widget *clock = g_value_get_object(values);
    if (strcmp(gtk_widget_get_name(clock), "clock") != 0 ||
        g_object_get_data(clock, "calendar-hook")) return 1;
    Widget *box = gtk_widget_get_parent(clock);
    if (!box) return 1;
    g_object_set_data(clock, "calendar-hook", (void *)1);
    gtk_widget_add_events(box, (1 << 12) | (1 << 13)); /* ENTER/LEAVE_NOTIFY */
    g_signal_connect_data(box, "enter-notify-event", (void (*)(void))entered, clock, NULL, 0);
    g_signal_connect_data(box, "leave-notify-event", (void (*)(void))left, clock, NULL, 0);
    return 1;
}
void gtk_module_init(int *argc, char ***argv) {
    (void)argc; (void)argv;
    GType type = gtk_widget_get_type();
    void *klass = g_type_class_ref(type); /* Register GtkWidget signals before lookup. */
    unsigned int signal = g_signal_lookup("realize", type);
    if (signal) g_signal_add_emission_hook(signal, 0, realized, NULL, NULL);
    g_type_class_unref(klass);
}
