import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland

Scope {
    id: root
    SystemTheme { id: systemTheme }

    readonly property string screenName: Quickshell.env("QS_POWER_SCREEN") || ""
    readonly property int pointerX: Number(Quickshell.env("QS_POWER_X") || 0)
    readonly property int topOffset: Number(Quickshell.env("QS_POWER_Y") || 60)
    readonly property var targetScreen: {
        for (var i = 0; i < Quickshell.screens.length; ++i) {
            if (Quickshell.screens[i].name === screenName)
                return Quickshell.screens[i]
        }
        return Quickshell.screens.length ? Quickshell.screens[0] : null
    }
    readonly property int menuWidth: 272
    readonly property int menuX: targetScreen
        ? Math.max(8, Math.min(pointerX - menuWidth / 2, targetScreen.width - menuWidth - 8))
        : 8
    readonly property var profiles: [
        { id: "power-saver", label: "Энергосбережение", detail: "Дольше работает от батареи", symbol: "󰌪" },
        { id: "balanced", label: "Обычный", detail: "Баланс скорости и расхода", symbol: "󰾅" },
        { id: "performance", label: "Производительность", detail: "Максимальная скорость", symbol: "󰓅" }
    ]

    property string currentProfile: ""
    property string pendingProfile: ""
    property string errorText: ""
    property bool busy: false
    property bool open: false
    property bool closing: false
    property real revealProgress: open ? 1 : 0

    // One timeline keeps the whole card synchronized, including its contents.
    Behavior on revealProgress {
        NumberAnimation {
            duration: root.closing ? 140 : 190
            easing.type: root.closing ? Easing.InCubic : Easing.OutCubic
        }
    }

    onRevealProgressChanged: {
        if (closing && revealProgress === 0)
            Qt.callLater(Qt.quit)
    }

    function dismiss() {
        if (closing)
            return
        closing = true
        open = false
        if (revealProgress === 0)
            Qt.quit()
    }

    function selectProfile(profile) {
        if (busy)
            return
        if (profile === currentProfile) {
            dismiss()
            return
        }
        busy = true
        errorText = ""
        pendingProfile = profile
        setProfile.command = ["python3", Quickshell.env("HOME") + "/.config/hypr/power-profile.py", "set", profile]
        setProfile.running = true
    }

    Process {
        id: getProfile
        command: ["python3", Quickshell.env("HOME") + "/.config/hypr/power-profile.py", "get"]
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                root.currentProfile = this.text.trim()
            }
        }
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0)
                root.errorText = "Не удалось прочитать режим питания"
        }
    }

    Process {
        id: setProfile
        onExited: (exitCode, exitStatus) => {
            root.busy = false
            if (exitCode === 0) {
                root.currentProfile = root.pendingProfile
                root.dismiss()
            } else {
                root.errorText = "Не удалось сменить режим питания"
                getProfile.running = true
            }
        }
    }

    PanelWindow {
        id: menu
        screen: root.targetScreen
        anchors {
            top: true
            left: true
        }
        margins {
            top: root.topOffset
            left: root.menuX
        }
        implicitWidth: root.menuWidth
        implicitHeight: root.errorText ? 252 : 222
        exclusionMode: ExclusionMode.Ignore
        focusable: true
        aboveWindows: true
        color: "transparent"
        WlrLayershell.namespace: "quickshell-power-menu"
        mask: Region { item: card }
        onWindowConnected: Qt.callLater(function() {
            if (!root.closing) {
                grab.active = true
                root.open = true
            }
        })

        Rectangle {
            id: card
            x: 0
            // Extra space below the card prevents clipping during its 6px slide.
            y: 6 * (1 - root.revealProgress)
            width: parent.width
            height: parent.height - 12
            radius: 15
            color: systemTheme.surface
            border.width: 1
            border.color: systemTheme.border
            opacity: root.revealProgress
            layer.enabled: true

            Column {
                anchors.fill: parent
                anchors.margins: 9
                spacing: 4

                Text {
                    width: parent.width
                    height: 30
                    leftPadding: 9
                    verticalAlignment: Text.AlignVCenter
                    text: "Режим питания"
                    font.pixelSize: 14
                    font.bold: true
                    color: systemTheme.text
                }

                Repeater {
                    id: profileRows
                    model: root.profiles

                    Rectangle {
                        id: row
                        required property var modelData
                        required property int index
                        readonly property bool selected: root.currentProfile === modelData.id
                        width: parent.width
                        height: 48
                        radius: 10
                        color: selected ? systemTheme.greenSoft : "transparent"
                        readonly property bool hovered: rowMouse.containsMouse
                        readonly property real hoverOpacity: hoverBackground.opacity

                        // Fixed-colour overlay: animate alpha, never RGB from transparent black.
                        Rectangle {
                            id: hoverBackground
                            anchors.fill: parent
                            radius: parent.radius
                            color: row.selected ? systemTheme.greenHover : systemTheme.hover
                            opacity: rowMouse.containsMouse && !root.closing ? 1 : 0
                            Behavior on opacity {
                                NumberAnimation { duration: 110; easing.type: Easing.OutQuad }
                            }
                        }
                        Rectangle {
                            width: 3
                            height: 26
                            radius: 2
                            anchors.left: parent.left
                            anchors.leftMargin: 2
                            anchors.verticalCenter: parent.verticalCenter
                            color: "#55a360"
                            opacity: row.selected ? 1 : 0

                            Behavior on opacity { NumberAnimation { duration: 170 } }
                        }

                        Text {
                            x: 10
                            width: 28
                            height: parent.height
                            verticalAlignment: Text.AlignVCenter
                            text: modelData.symbol
                            font.pixelSize: 18
                            color: selected ? systemTheme.green : systemTheme.muted
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }

                        Column {
                            x: 42
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 1

                            Text {
                                text: modelData.label
                                font.pixelSize: 13
                                font.weight: Font.Medium
                                color: systemTheme.text
                            }
                            Text {
                                text: modelData.detail
                                font.pixelSize: 10
                                color: systemTheme.muted
                            }
                        }

                        Text {
                            anchors.right: parent.right
                            anchors.rightMargin: 11
                            height: parent.height
                            verticalAlignment: Text.AlignVCenter
                            text: "✓"
                            font.pixelSize: 16
                            font.bold: true
                            color: systemTheme.green
                            opacity: selected ? 1 : 0

                            Behavior on opacity { NumberAnimation { duration: 170 } }
                        }

                        MouseArea {
                            id: rowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            enabled: !root.busy && !root.closing
                            onClicked: root.selectProfile(modelData.id)
                        }
                    }
                }

                Text {
                    visible: root.errorText !== ""
                    width: parent.width
                    height: visible ? 25 : 0
                    leftPadding: 9
                    verticalAlignment: Text.AlignVCenter
                    text: root.errorText
                    font.pixelSize: 11
                    color: systemTheme.light ? "#b34242" : "#f38b9a"
                }
            }
        }

    }

    IpcHandler {
        target: "powerMenu"
        function dismiss(): void { root.dismiss() }
        function state(): string {
            return JSON.stringify({light: systemTheme.light, open: root.open, closing: root.closing,
                progress: root.revealProgress, profile: root.currentProfile,
                cardY: card.y, cardOpacity: card.opacity,
                rows: root.profiles.map(function(profile, index) {
                    let row = profileRows.itemAt(index)
                    return row ? {id: profile.id, hovered: row.hovered,
                        opacity: row.hoverOpacity, width: row.width, height: row.height} : null
                })})
        }
    }

    HyprlandFocusGrab {
        id: grab
        windows: [menu]
        onCleared: root.dismiss()
    }

}
