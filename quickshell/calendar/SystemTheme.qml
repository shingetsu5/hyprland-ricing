import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: theme
    property bool light: false
    property bool ready: false
    readonly property bool busy: applyTheme.running
    readonly property color surface: light ? "#ffffff" : "#20242d"
    readonly property color panel: light ? "#f3f5f8" : "#2b313c"
    readonly property color text: light ? "#292929" : "#e7ebf3"
    readonly property color muted: light ? "#68747d" : "#a1aabb"
    readonly property color border: light ? "#d9e0e5" : "#424b5b"
    readonly property color accent: light ? "#429bee" : "#8ac0f2"
    readonly property color accentSoft: light ? "#e3f1fd" : "#2b4058"
    readonly property color hover: light ? "#edf1f3" : "#343d4b"
    readonly property color greenSoft: light ? "#e7f2e8" : "#293e32"
    readonly property color greenHover: light ? "#d9ebdc" : "#34513e"
    readonly property color green: light ? "#43804b" : "#9bd5a3"
    function setLight(value) {
        if (!ready || busy) return
        applyTheme.command = ["/usr/bin/python3", Quickshell.env("HOME") + "/.config/appearance/theme-switch.py", value ? "light" : "dark"]
        applyTheme.running = true
    }
    Process {
        running: true
        command: ["/usr/bin/python3", Quickshell.env("HOME") + "/.config/appearance/theme-switch.py", "--watch"]
        stdout: SplitParser {
            onRead: data => {
                try {
                    theme.light = JSON.parse(data).light
                    theme.ready = true
                } catch (error) { console.warn("System theme:", error) }
            }
        }
    }
    Process {
        id: applyTheme
        onExited: (code, status) => {
            if (code !== 0) console.warn("Could not apply system theme:", code)
        }
    }
}
