import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

ApplicationWindow {
    id: root
    title: "Rice Updates"
    width: 740
    height: 690
    minimumWidth: 560
    minimumHeight: 520
    visible: true
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    SystemTheme { id: systemTheme }

    readonly property string backend: Quickshell.shellDir + "/../../waybar/scripts/updates_run.py"
    readonly property string requestFile: Quickshell.env("RICE_UPDATE_DIALOG") || ""
    readonly property bool decisionMode: requestFile !== ""
    property bool opened: false
    property bool closing: false
    property bool checking: true
    property bool confirming: false
    property string errorText: ""
    property string platform: ""
    property string manager: ""
    property string checkedAt: ""
    property var packages: []
    property string query: ""
    property string expanded: ""
    property string decisionMessage: ""
    property var choices: []
    readonly property var filtered: packages.filter(p => !query || (p.name + " " + p.source).toLowerCase().includes(query.toLowerCase()))
    readonly property bool canUpdate: !checking && !launch.running && !errorText && packages.length > 0

    function dismiss() {
        if (closing) return
        closing = true
        // Keep the last frame opaque: Hyprland fades the entire window and border together.
        Qt.callLater(Qt.quit)
    }
    function check() {
        if (fetch.running || decisionMode) return
        checking = true
        errorText = ""
        fetch.running = true
    }
    function receive(text) {
        try {
            let result = JSON.parse(text)
            errorText = result.error || ""
            if (!errorText) {
                packages = result.packages
                platform = result.distro
                manager = result.manager
                checkedAt = result.checked_at
            }
        } catch (error) { errorText = "Не удалось прочитать список обновлений." }
        checking = false
        if (!search.activeFocus) Qt.callLater(() => updateButton.forceActiveFocus())
    }
    function ask() {
        if (!canUpdate || confirming || decisionMode) return
        confirming = true
        Qt.callLater(() => yesButton.forceActiveFocus())
    }
    function cancelConfirmation() {
        confirming = false
        updateButton.forceActiveFocus()
    }
    function install() {
        if (!confirming || launch.running) return
        confirming = false
        launch.running = true
    }
    function answer(index) {
        if (reply.running) return
        reply.command = ["python3", backend, "--dialog-answer", requestFile, "--index", String(index)]
        reply.running = true
    }
    function enter() {
        if (search.activeFocus || closing) return
        if (decisionMode) { if (choices.length) answer(0) }
        else if (confirming) install()
        else ask()
    }
    onClosing: event => { event.accepted = false; dismiss() }
    Component.onCompleted: {
        Qt.callLater(() => { opened = true; updateButton.forceActiveFocus() })
        if (decisionMode) readDecision.running = true
        else check()
    }
    Shortcut {
        sequence: "Escape"
        onActivated: { if (root.confirming) root.cancelConfirmation(); else root.dismiss() }
    }
    Shortcut {
        sequence: "Ctrl+F"
        enabled: !root.confirming && !root.decisionMode
        onActivated: { search.forceActiveFocus(); search.selectAll() }
    }
    Process {
        id: fetch
        command: ["python3", root.backend, "--json"]
        stdout: StdioCollector { id: result }
        stderr: StdioCollector { id: fetchError }
        onExited: (code, status) => {
            if (result.text.trim()) root.receive(result.text)
            else {
                root.checking = false
                root.errorText = fetchError.text.trim() || "Не удалось запустить проверку обновлений."
            }
        }
    }
    Process {
        id: launch
        command: ["python3", root.backend, "--launch"]
        stderr: StdioCollector { id: launchError }
        onExited: (code, status) => {
            if (code === 0) root.dismiss()
            else root.errorText = launchError.text.trim() || "Не удалось открыть терминал обновления."
        }
    }
    Process {
        id: readDecision
        command: ["python3", root.backend, "--dialog-read", root.requestFile]
        stdout: StdioCollector { id: decisionData }
        onExited: (code, status) => {
            root.checking = false
            try {
                let data = JSON.parse(decisionData.text)
                root.decisionMessage = data.message
                root.choices = data.options
                Qt.callLater(() => { let first = decisionButtons.itemAtIndex(0); if (first) first.forceActiveFocus() })
            } catch (error) { root.errorText = "Не удалось открыть диалог обновления." }
        }
    }
    Process { id: reply; onExited: (code, status) => { if (code === 0) root.dismiss(); else root.errorText = "Не удалось передать ответ." } }
    IpcHandler {
        target: "updates"
        function reveal(): void { root.show(); root.raise(); root.requestActivate() }
        function state(): string {
            return JSON.stringify({checking: root.checking, error: root.errorText, count: root.packages.length,
                filtered: root.filtered.length, confirming: root.confirming, yesFocused: yesButton.activeFocus,
                updateFocused: updateButton.activeFocus, searchFocused: search.activeFocus,
                decision: root.decisionMode, light: systemTheme.light, width: root.width, height: root.height})
        }
    }
    FocusScope {
        anchors.fill: parent
        focus: true
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                if (!event.isAutoRepeat) root.enter()
                event.accepted = true
            }
        }
        Rectangle {
            id: card
            anchors.fill: parent
            radius: 22
            color: systemTheme.surface
            border.color: systemTheme.border
            border.width: 1
            opacity: root.opened ? 1 : 0
            scale: root.opened ? 1 : 0.975
            transform: Translate { y: root.opened ? 0 : 10; Behavior on y { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } } }
            Behavior on opacity { NumberAnimation { duration: 150 } }
            Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 26
                spacing: 18
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    Rectangle {
                        width: 48; height: 48; radius: 15; color: systemTheme.accentSoft
                        Text {
                            anchors.centerIn: parent
                            text: "↻"; color: systemTheme.accent; font.pixelSize: 33
                            RotationAnimator on rotation { from: 0; to: 360; duration: 1200; loops: Animation.Infinite; running: root.checking }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        Text { text: root.decisionMode ? "Обновление системы" : "Обновления"; color: systemTheme.text; font { family: "Roboto"; pixelSize: 24; weight: Font.DemiBold } }
                        Text {
                            text: root.decisionMode ? "Выбери действие" : root.checking ? "Проверяем доступные обновления…"
                                : root.errorText ? "Проверка не завершена" : root.packages.length ? "Пакетов для обновления: " + root.packages.length : "Система обновлена"
                            color: systemTheme.muted; font.pixelSize: 12
                        }
                    }
                    Item { Layout.fillWidth: true }
                    ActionButton {
                        id: updateButton
                        theme: systemTheme; label: root.checking ? "Проверка…" : "Обновить всё  ↵"
                        primary: true; visible: !root.decisionMode; enabled: root.canUpdate && !root.confirming
                        onClicked: root.ask()
                    }
                    ActionButton { theme: systemTheme; label: "×"; compact: true; onClicked: root.dismiss() }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: systemTheme.border }
                RowLayout {
                    visible: !root.decisionMode
                    Layout.fillWidth: true
                    Rectangle {
                        implicitWidth: platformText.implicitWidth + 24; implicitHeight: 28; radius: 9; color: systemTheme.panel
                        Text { id: platformText; anchors.centerIn: parent; text: root.platform || "Linux"; color: systemTheme.text; font.pixelSize: 12 }
                    }
                    Text { text: root.manager; color: systemTheme.muted; font.pixelSize: 12 }
                    Item { Layout.fillWidth: true }
                    Text { text: root.checkedAt && !root.checking ? "Проверено в " + root.checkedAt : ""; color: systemTheme.muted; font.pixelSize: 11 }
                }
                TextField {
                    id: search
                    visible: !root.decisionMode
                    Layout.fillWidth: true; Layout.preferredHeight: 44
                    leftPadding: 14; rightPadding: 14
                    placeholderText: "Найти пакет…                                      Ctrl+F"
                    placeholderTextColor: systemTheme.muted; color: systemTheme.text
                    selectionColor: systemTheme.accentSoft; selectedTextColor: systemTheme.text
                    font.pixelSize: 13
                    onTextChanged: root.query = text.trim()
                    background: Rectangle { radius: 12; color: systemTheme.panel; border.width: 1; border.color: search.activeFocus ? systemTheme.accent : systemTheme.border }
                    Keys.onReturnPressed: event => event.accepted = true
                    Keys.onEnterPressed: event => event.accepted = true
                }
                Rectangle {
                    visible: root.errorText !== ""
                    Layout.fillWidth: true
                    implicitHeight: errorLabel.implicitHeight + 24
                    radius: 12; color: systemTheme.light ? "#fff0ee" : "#402c31"
                    Text { id: errorLabel; anchors.fill: parent; anchors.margins: 12; wrapMode: Text.Wrap; text: root.errorText; color: systemTheme.light ? "#9c3b35" : "#f0b1ae"; font.pixelSize: 12 }
                }
                Item {
                    visible: !root.decisionMode
                    Layout.fillWidth: true; Layout.fillHeight: true
                    ListView {
                        id: packageList
                        anchors.fill: parent
                        clip: true
                        spacing: 5
                        model: root.filtered
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: Item {
                            id: row
                            required property var modelData
                            readonly property bool isExpanded: root.expanded === modelData.name
                            readonly property bool hovered: headerMouse.containsMouse && !packageList.moving
                            property real hoverProgress: hovered ? 1 : 0
                            property real revealProgress: isExpanded ? 1 : 0
                            readonly property real progress: Math.max(0, Math.min(1, revealProgress))
                            readonly property real highlightOpacity: Math.max(0, Math.min(1, Math.max(hoverProgress, progress)))
                            width: packageList.width
                            height: 68 + 44 * progress
                            clip: true

                            // Retarget from the current position and velocity during quick pointer reversals.
                            Behavior on hoverProgress {
                                SmoothedAnimation { duration: 220; velocity: -1; reversingMode: SmoothedAnimation.Eased }
                            }
                            // Height, details and chevron share a single timeline.
                            Behavior on revealProgress {
                                SmoothedAnimation { duration: 240; velocity: -1; reversingMode: SmoothedAnimation.Eased }
                            }
                            Rectangle {
                                anchors.fill: parent
                                radius: 12
                                color: systemTheme.accentSoft
                                opacity: row.highlightOpacity
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.expanded = row.isExpanded ? "" : row.modelData.name
                            }
                            // Keep the hover area above the click handler and at a fixed height.
                            MouseArea {
                                id: headerMouse
                                width: parent.width
                                height: 68
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.expanded = row.isExpanded ? "" : row.modelData.name
                            }
                            Text { x: 16; y: 19; text: "⬡"; color: systemTheme.accent; font.pixelSize: 24 }
                            Column {
                                x: 56; y: 14; width: parent.width - 98; spacing: 5
                                Text { width: parent.width; elide: Text.ElideRight; text: row.modelData.name; color: systemTheme.text; font { pixelSize: 14; weight: Font.DemiBold } }
                                Text { width: parent.width; elide: Text.ElideRight; text: row.modelData.current + "  →  " + row.modelData.available; color: systemTheme.muted; font.pixelSize: 12 }
                            }
                            Text {
                                anchors.right: parent.right; anchors.rightMargin: 16; y: 22
                                text: "›"; color: systemTheme.muted; font.pixelSize: 23
                                rotation: 90 * row.progress
                            }
                            Text {
                                x: 56; y: 72 + 4 * (1 - row.progress); width: parent.width - 76
                                text: "Источник: " + row.modelData.source + " · Обновится вместе с системой"
                                color: systemTheme.muted; font.pixelSize: 11; wrapMode: Text.Wrap
                                opacity: row.progress
                            }
                        }
                    }
                    Column {
                        anchors.centerIn: parent
                        visible: !root.checking && !root.errorText && root.filtered.length === 0
                        spacing: 10
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.packages.length ? "⌕" : "✓"; color: systemTheme.accent; font.pixelSize: 40 }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.packages.length ? "Ничего не найдено" : "Все пакеты актуальны"; color: systemTheme.muted; font.pixelSize: 14 }
                    }
                    Rectangle {
                        visible: root.checking
                        anchors.top: parent.top; width: parent.width; height: 3; radius: 2; color: systemTheme.panel; clip: true
                        Rectangle {
                            width: parent.width * 0.28; height: parent.height; radius: 2; color: systemTheme.accent
                            SequentialAnimation on x { loops: Animation.Infinite; running: root.checking; NumberAnimation { from: -160; to: 670; duration: 1400; easing.type: Easing.InOutCubic } }
                        }
                    }
                }
                ScrollView {
                    visible: root.decisionMode
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    TextArea { readOnly: true; selectByMouse: true; wrapMode: Text.Wrap; text: root.decisionMessage; color: systemTheme.text; font.pixelSize: 14; background: null }
                }
                ListView {
                    id: decisionButtons
                    visible: root.decisionMode
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(root.choices.length * 52, 240)
                    clip: true
                    spacing: 8
                    model: root.choices
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    delegate: ActionButton {
                        required property string modelData
                        required property int index
                        theme: systemTheme; label: modelData; width: decisionButtons.width; height: 44
                        primary: index === 0
                        enabled: !reply.running
                        onClicked: root.answer(index)
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: systemTheme.border }
                RowLayout {
                    visible: !root.decisionMode
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        Text { text: "Установка откроется в терминале"; color: systemTheme.muted; font.pixelSize: 11 }
                        Text { text: "Enter — обновить · Ctrl+F — поиск · Esc — закрыть"; color: systemTheme.muted; font.pixelSize: 10 }
                    }
                    Item { Layout.fillWidth: true }
                    ActionButton { theme: systemTheme; label: root.errorText ? "Повторить проверку" : "Проверить снова"; enabled: !root.checking; onClicked: root.check() }
                }
            }
            // The modal traps focus. A held Enter cannot also confirm the next step.
            Rectangle {
                anchors.fill: parent; radius: card.radius
                visible: opacity > 0
                opacity: root.confirming ? 1 : 0
                color: systemTheme.light ? "#990e1927" : "#b3101720"
                Behavior on opacity { NumberAnimation { duration: 140 } }
                MouseArea { anchors.fill: parent; onClicked: root.cancelConfirmation() }
                Rectangle {
                    id: modalCard
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 48, 460); height: 240; radius: 18
                    color: systemTheme.surface; border.width: 1; border.color: systemTheme.border
                    scale: root.confirming ? 1 : 0.96
                    Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                    MouseArea { id: modal; anchors.fill: parent }
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 24; spacing: 16
                        Text { text: "Обновить все пакеты?"; color: systemTheme.text; font { pixelSize: 21; weight: Font.DemiBold } }
                        Text { Layout.fillWidth: true; text: "Откроется терминал для обновления системы.\nПароль и подтверждения — в терминале."; wrapMode: Text.Wrap; color: systemTheme.muted; font.pixelSize: 13; lineHeight: 1.3 }
                        Item { Layout.fillHeight: true }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 12
                            ActionButton { id: noButton; theme: systemTheme; label: "Нет"; Layout.fillWidth: true; enabled: root.confirming; onClicked: root.cancelConfirmation(); KeyNavigation.right: yesButton; KeyNavigation.tab: yesButton; KeyNavigation.backtab: yesButton }
                            ActionButton { id: yesButton; theme: systemTheme; label: "Да  ↵"; primary: true; Layout.fillWidth: true; enabled: root.confirming; onClicked: root.install(); KeyNavigation.left: noButton; KeyNavigation.tab: noButton; KeyNavigation.backtab: noButton }
                        }
                    }
                }
            }
        }
    }
}
