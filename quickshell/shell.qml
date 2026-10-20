import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Widgets
import Quickshell.Io

ApplicationWindow {
    id: launcher
    SystemTheme { id: systemTheme }
    WallpaperSettings { id: wallpaperSettings }
    visible: systemTheme.ready
    width: 860
    height: 640
    color: "transparent"//"#2e271e"

    // Fixed glass palette: independent of the system's light/dark preference.
    QtObject {
        id: glass
        readonly property color background: "#a6212e39"
        readonly property color rim: "#45c5d4dd"
        readonly property color surface: "#08ffffff"
        readonly property color panel: "#12ffffff"
        readonly property color field: "#16202d37"
        readonly property color border: "#24c5d4dd"
        readonly property color hover: "#1cbed2df"
        readonly property color selected: "#385e7e93"
        readonly property color selectedRim: "#809eb9ca"
        readonly property color text: "#e6edf2"
        readonly property color muted: "#aebdc7"
        readonly property color selectedText: "#f1f5f8"
        readonly property color iconBackground: "#12ffffff"
        readonly property color knob: "#d6e0e6"
        readonly property color knobRim: "#70c2d1db"
        readonly property color thumbnail: "#35202d37"
    }

    property string currentTab: "Apps"
    property string searchText: ""
    property string selectedWallpaper: ""
    property int selectedAppIndex: -1
    readonly property bool lightTheme: systemTheme.light
    property var sortedApps: []
    readonly property string normalizedSearch: searchText.trim().toLowerCase()

    function appMatches(entry) {
        if (!entry) {
            return false
        }

        if (normalizedSearch === "") {
            return !entry.noDisplay
        }

        var haystack = [
            entry.name || "",
            entry.genericName || "",
            entry.comment || "",
            entry.id || ""
        ]

        if (entry.keywords) {
            haystack = haystack.concat(entry.keywords)
        }

        return !entry.noDisplay
            && haystack.join(" ").toLowerCase().indexOf(normalizedSearch) !== -1
    }

    function iconSource(iconName) {
        if (!iconName || iconName === "") {
            return "image://icon/application-x-executable"
        }

        return "image://icon/" + iconName
    }

    function scrollView(view, wheel) {
        view.scrollWheel(wheel.angleDelta.y, wheel.pixelDelta.y)
        wheel.accepted = true
    }

    function focusSearch() {
        searchField.forceActiveFocus()
        searchField.selectAll()
    }

    function rebuildSortedApps() {
        var entries = DesktopEntries.applications.values || []
        var nextApps = entries.slice()

        nextApps.sort(function(a, b) {
            var left = (a && (a.name || a.id) || "").toLowerCase()
            var right = (b && (b.name || b.id) || "").toLowerCase()

            if (left < right) {
                return -1
            }

            if (left > right) {
                return 1
            }

            return 0
        })

        sortedApps = nextApps
    }

    function firstMatchedAppIndex() {
        var entries = sortedApps

        for (var i = 0; i < entries.length; ++i) {
            if (appMatches(entries[i])) {
                return i
            }
        }

        return -1
    }

    function stepMatchedAppIndex(step) {
        var entries = sortedApps

        if (!entries || entries.length === 0) {
            return -1
        }

        var index = selectedAppIndex

        if (index < 0 || index >= entries.length || !appMatches(entries[index])) {
            index = firstMatchedAppIndex()
        }

        if (index < 0) {
            return -1
        }

        for (var i = index + step; i >= 0 && i < entries.length; i += step) {
            if (appMatches(entries[i])) {
                return i
            }
        }

        return index
    }

    function syncSelectedApp() {
        selectedAppIndex = firstMatchedAppIndex()

        if (currentTab === "Apps" && appsLoader.item && selectedAppIndex >= 0) {
            appsLoader.item.stopSmoothScroll()
            appsLoader.item.positionViewAtIndex(selectedAppIndex, ListView.Contain)
        }
    }

    function moveSelectedApp(step) {
        var nextIndex = stepMatchedAppIndex(step)

        if (nextIndex < 0) {
            return
        }

        selectedAppIndex = nextIndex

        if (currentTab === "Apps" && appsLoader.item) {
            appsLoader.item.stopSmoothScroll()
            appsLoader.item.positionViewAtIndex(selectedAppIndex, ListView.Contain)
        }
    }

    function activateSelectedApp() {
        var entries = sortedApps

        if (!entries || selectedAppIndex < 0 || selectedAppIndex >= entries.length) {
            return
        }

        var entry = entries[selectedAppIndex]

        if (!appMatches(entry)) {
            return
        }

        entry.execute()
        Qt.quit()
    }

    Connections {
        target: DesktopEntries.applications

        function onValuesChanged() {
            rebuildSortedApps()
            syncSelectedApp()
        }
    }

    FolderListModel {
        id: wallpapersModel
        folder: "file://" + wallpaperSettings.directory
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        showDirs: false
        showDotAndDotDot: false
        sortField: FolderListModel.Name
    }

    Rectangle {
        anchors.fill: parent
        radius: 26
        color: glass.background
        border.width: 1
        border.color: glass.rim
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Rectangle {
                Layout.preferredWidth: 260
                Layout.preferredHeight: 52
                radius: 18
                color: glass.panel

                property int tabWidth: 120
                property int tabHeight: 40
                property int tabSpacing: 8
                property int sidePadding: 6

                Rectangle {
                    id: activeTabBg
                    y: 6
                    width: parent.tabWidth
                    height: parent.tabHeight
                    radius: 14
                    color: glass.selected
                    border.width: 1
                    border.color: glass.selectedRim

                    x: currentTab === "Apps"
                    ? parent.sidePadding
                    : parent.sidePadding + parent.tabWidth + parent.tabSpacing

                    Behavior on x {
                        NumberAnimation {
                            duration: 220
                            easing.type: Easing.InOutCubic
                        }
                    }
                }

                Row {
                    anchors.centerIn: parent
                    spacing: parent.tabSpacing

                    Rectangle {
                        width: parent.parent.tabWidth
                        height: parent.parent.tabHeight
                        radius: 14
                        color: "transparent"

                        Text {
                            anchors.centerIn: parent
                            text: "Apps"
                            color: currentTab === "Apps" ? glass.selectedText : glass.muted
                            font.pixelSize: 16
                            font.weight: Font.Medium

                            Behavior on color {
                                ColorAnimation { duration: 180 }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: currentTab = "Apps"
                        }
                    }

                    Rectangle {
                        width: parent.parent.tabWidth
                        height: parent.parent.tabHeight
                        radius: 14
                        color: "transparent"

                        Text {
                            anchors.centerIn: parent
                            text: "Walls"
                            color: currentTab === "Walls" ? glass.selectedText : glass.muted
                            font.pixelSize: 16
                            font.weight: Font.Medium

                            Behavior on color {
                                ColorAnimation { duration: 180 }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: currentTab = "Walls"
                        }
                    }
                }
            }

            Item {
                Layout.fillWidth: true
            }

            Rectangle {
                Layout.preferredWidth: 86
                Layout.preferredHeight: 52
                Layout.alignment: Qt.AlignRight
                radius: 18
                color: glass.panel

                Rectangle {
                    id: themeTrack
                    Accessible.role: Accessible.CheckBox
                    Accessible.checked: launcher.lightTheme
                    Accessible.name: launcher.lightTheme ? "Системная тема: светлая" : "Системная тема: тёмная"
                    anchors.centerIn: parent
                    width: 70
                    height: 34
                    radius: 17
                    color: lightTheme ? "#244d6576" : "#24202c37"
                    border.width: 1
                    border.color: lightTheme ? "#7090a5b2" : "#507f94a1"

                    Behavior on color {
                        ColorAnimation { duration: 220 }
                    }

                    Behavior on border.color {
                        ColorAnimation { duration: 220 }
                    }

                    Rectangle {
                        id: themeKnob
                        y: 2
                        width: 30
                        height: 30
                        radius: 15
                        color: lightTheme ? "#c7d2d9" : "#526775"
                        border.width: 1
                        border.color: lightTheme ? "#70c2d1db" : "#6094a8b5"

                        x: lightTheme ? parent.width - width - 2 : 2

                        Text {
                            anchors.centerIn: parent
                            text: "☀"
                            font.family: "DejaVu Sans"
                            font.pixelSize: 17
                            color: "#506775"
                            opacity: launcher.lightTheme ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 180 } }
                        }
                        Text {
                            anchors.centerIn: parent
                            text: "☾"
                            font.family: "DejaVu Sans"
                            font.pixelSize: 19
                            color: "#d0dce4"
                            opacity: launcher.lightTheme ? 0 : 1
                            Behavior on opacity { NumberAnimation { duration: 180 } }
                        }

                        Behavior on x {
                            NumberAnimation {
                                duration: 240
                                easing.type: Easing.InOutCubic
                            }
                        }

                        Behavior on color {
                            ColorAnimation { duration: 220 }
                        }

                        Behavior on border.color {
                            ColorAnimation { duration: 220 }
                        }

                        scale: themeSwitchArea.pressed ? 0.92 : 1.0

                        Behavior on scale {
                            NumberAnimation {
                                duration: 140
                                easing.type: Easing.InOutCubic
                            }
                        }
                    }

                    MouseArea {
                        id: themeSwitchArea
                        anchors.fill: parent
                        enabled: systemTheme.ready && !systemTheme.busy
                        cursorShape: Qt.PointingHandCursor
                        onClicked: systemTheme.setLight(!lightTheme)
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 54
            radius: 16
            color: glass.field
            border.width: 1
            border.color: glass.border

            TextField {
                id: searchField
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                color: glass.text
                placeholderText: currentTab === "Walls" ? "Search wallpapers..." : "Search apps..."
                placeholderTextColor: glass.muted
                selectionColor: glass.selected
                selectedTextColor: glass.selectedText
                font.pixelSize: 17
                background: null
                selectByMouse: true
                focus: currentTab === "Apps"

                onTextChanged: {
                    searchText = text
                    syncSelectedApp()
                }

                Keys.onPressed: event => {
                    if (currentTab !== "Apps") {
                        return
                    }

                    if (event.key === Qt.Key_Down) {
                        moveSelectedApp(1)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Up) {
                        moveSelectedApp(-1)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        activateSelectedApp()
                        event.accepted = true
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // Keep both views alive so tab changes only switch visibility.
            Loader {
                id: appsLoader
                anchors.fill: parent
                visible: currentTab === "Apps"
                sourceComponent: appsComponent

                onLoaded: {
                    syncSelectedApp()
                    if (currentTab === "Apps") {
                        focusSearch()
                    }
                }
            }

            Loader {
                id: wallsLoader
                anchors.fill: parent
                visible: currentTab === "Walls"
                asynchronous: true
                sourceComponent: wallsComponent
            }
        }
    }

    IpcHandler {
        target: "appearance"
        function setLight(value: bool): void { systemTheme.setLight(value) }
        function state(): string {
            let view = launcher.currentTab === "Apps" ? appsLoader.item : wallsLoader.item
            return JSON.stringify({glassBackground: glass.background.toString(), glassText: glass.text.toString(),
                glassSelection: glass.selected.toString(), tab: launcher.currentTab, light: launcher.lightTheme, ready: systemTheme.ready, busy: systemTheme.busy,
                scrollY: view ? view.contentY : 0, scrollTarget: view ? view.scrollDestination : 0,
                scrolling: view ? view.scrollAnimating : false,
                scrollMin: view ? view.originY : 0,
                scrollMax: view ? view.originY + Math.max(0, view.contentHeight - view.height) : 0})
        }
    }

    onCurrentTabChanged: {
        if (currentTab === "Apps") {
            syncSelectedApp()
            focusSearch()
        }
    }

    Component.onCompleted: {
        rebuildSortedApps()
        syncSelectedApp()
        focusSearch()
    }

    Component {
        id: appsComponent

        ListView {
            id: appsList
            readonly property bool scrollAnimating: scrollMotion.running
            readonly property real scrollDestination: scrollMotion.destination
            function scrollWheel(angle, pixels) { scrollMotion.scroll(angle, pixels) }
            function stopSmoothScroll() { scrollMotion.cancel() }
            SmoothScroll { id: scrollMotion; view: appsList }
            anchors.fill: parent
            clip: true
            spacing: 10
            boundsBehavior: Flickable.StopAtBounds
            model: sortedApps

            WheelHandler {
                target: null
                blocking: true
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: (wheel) => scrollView(appsList, wheel)
            }

            delegate: Rectangle {
                required property var modelData
                required property int index

                property var entry: modelData
                property bool matched: appMatches(entry)
                property bool selected: matched && index === selectedAppIndex

                width: appsList.width
                height: matched ? 68 : 0
                radius: 18
                color: selected ? glass.selected : (hovered ? glass.hover : glass.surface)
                border.width: matched ? 1 : 0
                border.color: selected ? glass.selectedRim : (hovered ? glass.selectedRim : glass.border)
                visible: height > 0
                opacity: matched ? 1 : 0

                Behavior on height {
                    NumberAnimation {
                        duration: 140
                    }
                }

                Behavior on opacity {
                    NumberAnimation {
                        duration: 120
                    }
                }

                property bool hovered: false

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    anchors.topMargin: 12
                    anchors.bottomMargin: 12
                    spacing: 14

                    Rectangle {
                        Layout.preferredWidth: 42
                        Layout.preferredHeight: 42
                        radius: 12
                        color: glass.iconBackground
                        border.width: 1
                        border.color: glass.border

                        IconImage {
                            anchors.centerIn: parent
                            implicitSize: 24
                            width: 24
                            height: 24
                            source: iconSource(entry.icon)
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            Layout.fillWidth: true
                            text: entry.name || entry.id || "Unknown app"
                            color: selected ? glass.selectedText : glass.text
                            font.pixelSize: 16
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: entry.genericName || entry.comment || entry.id || ""
                            color: selected ? glass.muted : glass.muted
                            font.pixelSize: 12
                            elide: Text.ElideRight
                            visible: text.length > 0
                        }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    scrollGestureEnabled: false

                    onEntered: parent.hovered = true
                    onExited: parent.hovered = false
                    onClicked: {
                        selectedAppIndex = index
                        activateSelectedApp()
                    }
                }
            }

            ScrollBar.vertical: ScrollBar {
                id: appsScrollBar
                policy: ScrollBar.AsNeeded
                implicitWidth: 8
                padding: 2
                minimumSize: 0.08
                onPressedChanged: if (pressed) appsList.stopSmoothScroll()
                background: Item {}
                contentItem: Rectangle {
                    implicitWidth: 4
                    implicitHeight: 40
                    radius: 2
                    color: glass.muted
                    opacity: appsScrollBar.pressed ? 0.9 : appsScrollBar.active ? 0.65 : 0.3
                    Behavior on opacity { NumberAnimation { duration: 140 } }
                }
            }
        }
    }

    Component {
        id: wallsComponent

        GridView {
            id: wallsGrid
            readonly property bool scrollAnimating: scrollMotion.running
            readonly property real scrollDestination: scrollMotion.destination
            function scrollWheel(angle, pixels) { scrollMotion.scroll(angle, pixels) }
            function stopSmoothScroll() { scrollMotion.cancel() }
            SmoothScroll { id: scrollMotion; view: wallsGrid }
            anchors.fill: parent
            cellWidth: 180
            cellHeight: 150
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            model: wallpapersModel

            WheelHandler {
                target: null
                blocking: true
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: (wheel) => scrollView(wallsGrid, wheel)
            }

            delegate: Item {
                width: wallsGrid.cellWidth
                height: wallsGrid.cellHeight

                property string wallUrl: fileUrl
                property string wallPath: decodeURIComponent(fileUrl.toString().replace("file://", ""))
                property string wallName: fileName
                property bool matched: searchText === ""
                                       || wallName.toLowerCase().indexOf(searchText.toLowerCase()) !== -1

                visible: matched

                Rectangle {
                    id: card
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 8
                    height: 132
                    radius: 18
                    color: hovered ? glass.hover : glass.surface
                    border.width: selectedWallpaper === wallPath ? 2 : 1
                    border.color: selectedWallpaper === wallPath ? glass.selectedRim : glass.border

                    property bool hovered: false

                    scale: hovered ? 1.03 : 1.0

                    Behavior on scale {
                        NumberAnimation {
                            duration: 120
                        }
                    }

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        anchors.topMargin: 10
                        height: 90
                        radius: 12
                        clip: true
                        color: glass.thumbnail

                        Image {
                            anchors.fill: parent
                            source: wallUrl
                            asynchronous: true
                            // Decode a thumbnail instead of the full wallpaper.
                            sourceSize.width: 288
                            sourceSize.height: 180
                            fillMode: Image.PreserveAspectCrop
                        }
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        anchors.bottomMargin: 10
                        text: wallName
                        color: selectedWallpaper === wallPath ? glass.selectedText : glass.text
                        font.pixelSize: 13
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignHCenter
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        scrollGestureEnabled: false

                        onEntered: card.hovered = true
                        onExited: card.hovered = false

                        onClicked: {
                            selectedWallpaper = wallPath
                            console.log("Set wallpaper:", wallPath)

                            Quickshell.execDetached([
                                Quickshell.env("HOME") + "/.config/hypr/wallpaper.sh",
                                "set",
                                wallPath
                            ])
                        }
                    }
                }
            }
        }
    }
}
