import QtQuick

FocusScope {
    id: control
    required property var theme
    property string label: ""
    property bool primary: false
    property bool compact: false
    property bool selected: activeFocus
    signal clicked()
    implicitWidth: Math.max(compact ? 38 : 110, caption.implicitWidth + (compact ? 20 : 34))
    implicitHeight: compact ? 36 : 44
    activeFocusOnTab: enabled && visible
    opacity: enabled ? 1 : 0.45
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.onPressAction: if (enabled) clicked()
    Keys.onPressed: event => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (!event.isAutoRepeat && enabled) clicked()
            event.accepted = true
        }
    }
    Rectangle {
        anchors.fill: parent
        radius: control.compact ? 10 : 12
        color: control.primary ? control.theme.accent
            : pointer.containsMouse || control.selected ? control.theme.accentSoft : control.theme.panel
        border.color: control.primary ? control.theme.accent
            : control.selected ? control.theme.accent : control.theme.border
        border.width: 1
        scale: pointer.pressed ? 0.98 : 1
        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on scale { NumberAnimation { duration: 100 } }
        Text {
            id: caption
            anchors.centerIn: parent
            text: control.label
            color: control.primary ? (control.theme.light ? "#ffffff" : "#152639") : control.theme.text
            font { family: "Roboto"; pixelSize: 13; weight: Font.DemiBold }
        }
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: { control.forceActiveFocus(); control.clicked() }
    }
}
