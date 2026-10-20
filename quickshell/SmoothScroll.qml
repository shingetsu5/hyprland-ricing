import QtQuick
import Quickshell

Scope {
    id: controller
    required property var view
    property real destination: 0
    readonly property bool running: motion.running

    function clamp(y) {
        let minimum = view.originY
        let maximum = minimum + Math.max(0, view.contentHeight - view.height)
        return Math.max(minimum, Math.min(maximum, y))
    }
    function cancel() {
        motion.stop()
        destination = view.contentY
    }
    function scroll(angle, pixels) {
        view.cancelFlick()
        if (pixels !== 0) {
            // Touchpads already deliver smooth pixel motion: keep it responsive.
            cancel()
            destination = clamp(view.contentY - pixels)
            view.contentY = destination
            return
        }
        if (angle === 0) return
        let delta = -angle / 120 * 110
        // Accumulate wheel ticks; a direction change immediately follows the hand.
        let base = motion.running && (destination - view.contentY) * delta > 0
            ? destination : view.contentY
        motion.stop()
        destination = clamp(base + delta)
        if (Math.abs(destination - view.contentY) < 0.1) return
        motion.from = view.contentY
        motion.to = destination
        motion.start()
    }
    function checkBounds() {
        if (motion.running && clamp(destination) !== destination) {
            motion.stop()
            destination = clamp(destination)
            motion.from = view.contentY
            motion.to = destination
            motion.start()
        }
    }
    NumberAnimation {
        id: motion
        target: controller.view
        property: "contentY"
        duration: 190
        easing.type: Easing.OutCubic
    }
    Connections {
        target: controller.view
        function onDraggingChanged() { if (controller.view.dragging) controller.cancel() }
        function onVisibleChanged() { if (!controller.view.visible) controller.cancel() }
        function onContentHeightChanged() { controller.checkBounds() }
        function onHeightChanged() { controller.checkBounds() }
    }
}
