import QtQuick
import QtQuick.Layouts
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root
    SystemTheme { id: systemTheme }
    property bool opened: false
    property bool clockHovered: false
    property bool cardHovered: false
    property string screenName: ""
    property real clockCenter: 0
    property real clockBottom: 48
    property date today: new Date()
    property date selected: today
    property int shownYear: today.getFullYear()
    property int shownMonth: today.getMonth()
    property int pendingMonthSteps: 0
    property int monthDirection: 1
    property real monthOpacity: 1
    property real monthShift: 0
    property real wheelRemainder: 0
    readonly property var months: ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    readonly property var weekDays: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    readonly property var russian: Qt.locale("ru_RU")
    readonly property color ink: systemTheme.text
    readonly property color muted: systemTheme.muted
    readonly property color accent: systemTheme.accent

    function sameDay(a, b) {
        return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
            && a.getDate() === b.getDate()
    }
    function dateAt(index) {
        let first = new Date(shownYear, shownMonth, 1, 12)
        let offset = (first.getDay() + 6) % 7
        return new Date(shownYear, shownMonth, 1 - offset + index, 12)
    }
    function applyMonthStep(step) {
        let date = new Date(shownYear, shownMonth + step, 1, 12)
        shownYear = date.getFullYear()
        shownMonth = date.getMonth()
    }
    function beginMonthTransition() {
        if (pendingMonthSteps === 0) return
        monthDirection = pendingMonthSteps > 0 ? 1 : -1
        monthTransition.start()
    }
    function changeMonth(step) {
        if (step === 0) return
        if (!opened) {
            applyMonthStep(step)
            return
        }
        // Accumulate rapid clicks/scrolls instead of interrupting the animation.
        pendingMonthSteps += step
        if (!monthTransition.running) beginMonthTransition()
    }
    function scrollMonths(angle, pixels) {
        let threshold = pixels !== 0 ? 60 : 120
        let delta = pixels !== 0 ? pixels : angle
        if (delta === 0) return
        wheelIdle.restart()
        if (wheelRemainder * delta < 0) wheelRemainder = 0
        wheelRemainder += delta
        let steps = Math.trunc(wheelRemainder / threshold)
        if (steps !== 0) {
            wheelRemainder -= steps * threshold
            changeMonth(-steps) // Down: next month. Up: previous month.
        }
    }
    function resetMonthTransition() {
        monthTransition.stop()
        pendingMonthSteps = 0
        monthOpacity = 1
        monthShift = 0
        wheelRemainder = 0
        wheelIdle.stop()
    }
    function goToday() {
        resetMonthTransition()
        today = new Date()
        selected = today
        shownYear = today.getFullYear()
        shownMonth = today.getMonth()
    }
    function showOn(name, center, bottom) {
        if (!opened) goToday()
        screenName = name
        clockCenter = center
        clockBottom = bottom
        opened = true
    }
    function scheduleClose() {
        if (!clockHovered && !cardHovered) closeTimer.restart()
    }
    function receive(line) {
        try {
            let event = JSON.parse(line)
            if (event.event === "enter") {
                closeTimer.stop()
                clockHovered = true
                screenName = event.screen
                clockCenter = event.center
                clockBottom = event.bottom
                if (!opened) openTimer.restart()
            } else if (event.event === "leave") {
                clockHovered = false
                openTimer.stop()
                scheduleClose()
            }
        } catch (error) { console.warn("Calendar event:", error) }
    }

    SequentialAnimation {
        id: monthTransition
        ParallelAnimation {
            NumberAnimation { target: root; property: "monthOpacity"; to: 0; duration: 90; easing.type: Easing.InCubic }
            NumberAnimation { target: root; property: "monthShift"; to: -12 * root.monthDirection; duration: 90; easing.type: Easing.InCubic }
        }
        ScriptAction {
            script: {
                root.applyMonthStep(root.pendingMonthSteps)
                root.pendingMonthSteps = 0
                root.monthShift = 12 * root.monthDirection
            }
        }
        ParallelAnimation {
            NumberAnimation { target: root; property: "monthOpacity"; to: 1; duration: 180; easing.type: Easing.OutCubic }
            NumberAnimation { target: root; property: "monthShift"; to: 0; duration: 180; easing.type: Easing.OutCubic }
        }
        onFinished: root.beginMonthTransition()
    }
    Timer { id: wheelIdle; interval: 220; onTriggered: root.wheelRemainder = 0 }
    Timer {
        id: openTimer
        interval: 300
        onTriggered: if (root.clockHovered) root.showOn(root.screenName, root.clockCenter, root.clockBottom)
    }
    Timer {
        id: closeTimer
        interval: 350
        onTriggered: if (!root.clockHovered && !root.cardHovered) root.opened = false
    }
    Timer { interval: 60000; running: true; repeat: true; onTriggered: root.today = new Date() }
    Process {
        id: bridge
        command: ["/usr/bin/python3", Qt.resolvedUrl("hover-bridge.py").toString().replace("file://", "")]
        running: true
        stdout: SplitParser { onRead: data => root.receive(data) }
        onExited: (code, status) => {
            root.opened = false
            console.warn("Calendar hover bridge stopped:", code)
        }
    }
    IpcHandler {
        target: "calendar"
        function reveal(screen: string, center: real, bottom: real): void {
            root.clockHovered = true
            root.showOn(screen, center, bottom)
        }
        function hide(): void {
            root.clockHovered = false
            root.cardHovered = false
            openTimer.stop()
            root.opened = false
        }
        function month(step: int): void { root.changeMonth(step) }
        function scroll(angle: real, pixels: real): void { root.scrollMonths(angle, pixels) }
        function today(): void { root.goToday() }
        function state(): string {
            return JSON.stringify({light: systemTheme.light, opened: root.opened, screen: root.screenName,
                clockHovered: root.clockHovered, cardHovered: root.cardHovered,
                year: root.shownYear, month: root.shownMonth + 1,
                animating: monthTransition.running, pending: root.pendingMonthSteps,
                monthOpacity: root.monthOpacity, monthShift: root.monthShift,
                first: root.dateAt(0).toLocaleDateString(root.russian, "yyyy-MM-dd"),
                last: root.dateAt(41).toLocaleDateString(root.russian, "yyyy-MM-dd")})
        }
    }

    PanelWindow {
        id: popup
        screen: Quickshell.screens.find(s => s.name === root.screenName) || Quickshell.screens[0]
        visible: root.opened || card.opacity > 0.001
        anchors.top: true
        anchors.left: true
        margins.top: Math.round(root.clockBottom - 10)
        margins.left: Math.round(Math.max(0, Math.min(root.clockCenter - implicitWidth / 2,
                                               screen.width - implicitWidth)))
        implicitWidth: 384
        implicitHeight: 448
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "waybar-calendar"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        mask: Region { item: card }

        Rectangle {
            id: card
            x: 12; y: 10
            width: 360; height: 420
            radius: 20
            color: systemTheme.surface
            border.color: systemTheme.border
            border.width: 1
            opacity: root.opened ? 1 : 0
            scale: root.opened ? 1 : 0.98
            transformOrigin: Item.Top
            Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
            Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: "#25000000"
                shadowBlur: 0.7
                shadowVerticalOffset: 4
                shadowHorizontalOffset: 0
                autoPaddingEnabled: true
            }
            WheelHandler {
                target: null
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                blocking: true
                onWheel: event => {
                    root.scrollMonths(event.angleDelta.y, event.pixelDelta.y)
                    event.accepted = true
                }
            }
            HoverHandler {
                onHoveredChanged: {
                    root.cardHovered = hovered
                    if (hovered) closeTimer.stop()
                    else root.scheduleClose()
                }
            }
            Column {
                x: 20; y: 19
                width: 320
                spacing: 0
                Row {
                    width: parent.width
                    height: 45
                    spacing: 12
                    Rectangle {
                        width: 42; height: 42; radius: 13
                        color: systemTheme.accentSoft
                        Text {
                            anchors.centerIn: parent
                            text: root.today.getDate()
                            color: root.accent
                            font { family: "Roboto"; pixelSize: 22; bold: true }
                        }
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Text {
                            text: "Сегодня"
                            color: root.ink
                            font { family: "Roboto"; pixelSize: 15; bold: true }
                        }
                        Text {
                            text: root.today.toLocaleDateString(root.russian, "dddd, d MMMM")
                            color: root.muted
                            font { family: "Roboto"; pixelSize: 12 }
                        }
                    }
                }
                Item { width: 1; height: 16 }
                Rectangle { width: parent.width; height: 1; color: systemTheme.border }
                Item { width: 1; height: 12 }
                RowLayout {
                    width: parent.width; height: 34
                    Text {
                        Layout.fillWidth: true
                        text: root.months[root.shownMonth] + " " + root.shownYear
                        opacity: root.monthOpacity
                        transform: Translate { x: root.monthShift }
                        color: root.ink
                        font { family: "Roboto"; pixelSize: 17; bold: true }
                    }
                    Repeater {
                        model: ["‹", "›"]
                        Rectangle {
                            required property string modelData
                            required property int index
                            Layout.preferredWidth: 30; Layout.preferredHeight: 30
                            radius: 9
                            color: nav.containsMouse ? systemTheme.accentSoft : systemTheme.panel
                            Text {
                                anchors.centerIn: parent
                                anchors.verticalCenterOffset: -1
                                text: modelData
                                color: root.ink
                                font.pixelSize: 24
                            }
                            MouseArea {
                                id: nav
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.changeMonth(index === 0 ? -1 : 1)
                            }
                        }
                    }
                }
                Item { width: 1; height: 9 }
                Row {
                    width: parent.width; height: 26
                    Repeater {
                        model: root.weekDays
                        Text {
                            required property string modelData
                            required property int index
                            width: 320 / 7
                            text: modelData
                            horizontalAlignment: Text.AlignHCenter
                            color: index > 4 ? root.accent : root.muted
                            font { family: "Roboto"; pixelSize: 11; bold: true }
                        }
                    }
                }
                Grid {
                    opacity: root.monthOpacity
                    transform: Translate { x: root.monthShift }
                    enabled: !monthTransition.running
                    columns: 7
                    width: parent.width
                    Repeater {
                        model: 42
                        Item {
                            id: day
                            required property int index
                            width: 320 / 7; height: 34
                            readonly property date date: root.dateAt(index)
                            readonly property bool isToday: root.sameDay(date, root.today)
                            readonly property bool isSelected: root.sameDay(date, root.selected)
                            readonly property bool inMonth: date.getMonth() === root.shownMonth
                            Rectangle {
                                anchors.centerIn: parent
                                width: 32; height: 30; radius: 10
                                color: day.isToday ? root.accent : dayMouse.containsMouse ? systemTheme.accentSoft : "transparent"
                                border.width: day.isSelected && !day.isToday ? 1 : 0
                                border.color: "#91c7f5"
                                Text {
                                    anchors.centerIn: parent
                                    text: day.date.getDate()
                                    color: day.isToday ? "#ffffff" : !day.inMonth ? (systemTheme.light ? "#c4cad2" : "#657082")
                                        : day.index % 7 > 4 ? root.accent : root.ink
                                    font { family: "Roboto"; pixelSize: 13; bold: day.isToday }
                                }
                            }
                            MouseArea {
                                id: dayMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.selected = day.date
                            }
                        }
                    }
                }
                Item { width: 1; height: 8 }
                RowLayout {
                    width: parent.width; height: 27
                    Text {
                        Layout.fillWidth: true
                        text: root.selected.toLocaleDateString(root.russian, "dd.MM.yyyy")
                        color: root.muted
                        font { family: "Roboto"; pixelSize: 11 }
                    }
                    Rectangle {
                        Layout.preferredWidth: 76; Layout.preferredHeight: 27
                        radius: 8
                        color: todayMouse.containsMouse ? systemTheme.hover : systemTheme.accentSoft
                        Text {
                            anchors.centerIn: parent
                            text: "Сегодня"
                            color: root.accent
                            font { family: "Roboto"; pixelSize: 11; bold: true }
                        }
                        MouseArea {
                            id: todayMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.goToday()
                        }
                    }
                }
            }
        }
    }
}
