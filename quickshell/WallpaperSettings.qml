import QtQml
import Quickshell
QtObject {
    readonly property string directory: Quickshell.env("HOME") + "/Pictures/wallpapers"
}
