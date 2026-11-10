import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    id: root
    property var th: bridge.theme
    property int cur: 0
    color: th.panel
    radius: 12
    border.color: th.border

    Column {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 4

        Row {
            spacing: 4
            Repeater {
                model: bridge.model
                delegate: Rectangle {
                    width: tabText.implicitWidth + 24
                    height: 24
                    radius: 12
                    color: root.cur === index ? th.accent : (tabMa.containsMouse ? th.hover : "transparent")
                    Text {
                        id: tabText
                        anchors.centerIn: parent
                        text: modelData.title
                        font.family: "Segoe UI"; font.pixelSize: 13; font.bold: true
                        color: root.cur === index ? "white" : th.fg
                    }
                    MouseArea { id: tabMa; anchors.fill: parent; hoverEnabled: true; onClicked: root.cur = index }
                }
            }
        }

        Row {
            height: parent.height - 28
            spacing: 0
            Repeater {
                model: bridge.model[root.cur].groups
                delegate: Row {
                    height: parent.height
                    spacing: 8
                    leftPadding: index > 0 ? 8 : 0
                    Rectangle {
                        visible: index > 0
                        width: 1; height: parent.height - 4
                        color: th.border
                    }
                    Column {
                        spacing: 2
                        Row {
                            spacing: 2
                            Repeater {
                                model: modelData.items
                                delegate: Item {
                                    id: cell
                                    property bool isSlider: !!modelData.slider
                                    width: isSlider ? 170 : Math.max(54, lbl.implicitWidth + 14)
                                    height: 58

                                    // --- bouton ---
                                    Rectangle {
                                        id: btn
                                        visible: !cell.isSlider
                                        anchors.fill: parent
                                        property bool on: cell.isSlider ? false : bridge.checked(modelData.id, bridge.rev)
                                        property bool ok: cell.isSlider ? true : bridge.enabled(modelData.id, bridge.rev)
                                        radius: 8
                                        opacity: ok ? 1 : 0.35
                                        color: on ? th.active : (ma.containsMouse && ok ? th.hover : "transparent")
                                        Image {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            y: 6
                                            width: 28; height: 28
                                            sourceSize: Qt.size(56, 56)
                                            smooth: true
                                            source: cell.isSlider ? "" : "image://ribbon/" + modelData.id + "?" + bridge.rev
                                        }
                                        Text {
                                            id: lbl
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            y: 38
                                            text: cell.isSlider ? "" : modelData.label
                                            font.family: "Segoe UI"; font.pixelSize: 12
                                            color: btn.on ? th.accent : th.fg
                                        }
                                        MouseArea {
                                            id: ma
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            enabled: btn.ok && !cell.isSlider
                                            onClicked: bridge.trigger(modelData.id)
                                        }
                                        ToolTip.visible: ma.containsMouse
                                        ToolTip.delay: 600
                                        ToolTip.text: cell.isSlider ? "" : bridge.tip(modelData.id, bridge.rev)
                                    }

                                    // --- slider ---
                                    Column {
                                        id: sl
                                        visible: cell.isSlider
                                        property bool ok: cell.isSlider ? bridge.enabled(modelData.id, bridge.rev) : true
                                        opacity: ok ? 1 : 0.35
                                        property int val: cell.isSlider ? bridge.value(modelData.id, bridge.rev) : 0
                                        property int lo: cell.isSlider ? modelData.min : 0
                                        property int hi: cell.isSlider ? modelData.max : 1
                                        y: 4
                                        Text {
                                            text: cell.isSlider ? modelData.label : ""
                                            font.family: "Segoe UI"; font.pixelSize: 11
                                            color: th.dim
                                        }
                                        Row {
                                            spacing: 8
                                            Item {
                                                id: track
                                                width: 116; height: 22
                                                Rectangle {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    width: parent.width; height: 4; radius: 2
                                                    color: th.border
                                                    Rectangle { width: handle.x + 7; height: 4; radius: 2; color: th.accent }
                                                }
                                                Rectangle {
                                                    id: handle
                                                    width: 14; height: 14; radius: 7
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    x: (track.width - 14) * (sl.val - sl.lo) / (sl.hi - sl.lo)
                                                    color: th.accent
                                                }
                                                MouseArea {
                                                    anchors.fill: parent
                                                    enabled: sl.ok
                                                    function setFrom(mx) {
                                                        var f = Math.max(0, Math.min(1, (mx - 7) / (track.width - 14)))
                                                        bridge.setValue(modelData.id, Math.round(sl.lo + f * (sl.hi - sl.lo)))
                                                    }
                                                    onPressed: (m) => setFrom(m.x)
                                                    onPositionChanged: (m) => { if (pressed) setFrom(m.x) }
                                                }
                                            }
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: sl.val + " %"
                                                font.family: "Segoe UI"; font.pixelSize: 11
                                                color: th.fg
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.title.toUpperCase()
                            font.family: "Segoe UI"; font.pixelSize: 10
                            color: th.dim
                        }
                    }
                }
            }
        }
    }
}
