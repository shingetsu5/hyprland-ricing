-- Hyprland 0.57+ configuration. Monitor and cursor settings are separate modules.
require("monitors")
require("cursor")

local terminal = "kitty"
local fileManager = "thunar"
local menu = "~/.config/waybar/scripts/toggle-launcher.sh"
local mainMod = "SUPER"

hl.env("QT_QPA_PLATFORMTHEME", "xdgdesktopportal")

hl.on("hyprland.start", function()
    hl.exec_cmd("nm-applet")
    hl.exec_cmd("~/.config/appearance/start-session-theme.sh && ~/.config/waybar/launch.sh")
    hl.exec_cmd("~/.config/hypr/wallpaper.sh start")
    hl.exec_cmd("systemctl --user start hyprpolkitagent.service")
    hl.exec_cmd("swaync")
    hl.exec_cmd("~/.config/hypr/volume-osd.py")
end)

hl.on("hyprland.shutdown", function()
    hl.exec_cmd("systemctl --user stop quickshell-desktop-session.target")
end)

hl.config({
    general = {
        gaps_in = 5,
        gaps_out = 10,
        border_size = 2,
        col = {
            active_border = { colors = { "rgba(33ccffee)", "rgba(00ff99ee)" }, angle = 45 },
            inactive_border = "rgba(595959aa)",
        },
        resize_on_border = false,
        allow_tearing = false,
        layout = "dwindle",
    },
    decoration = {
        rounding = 10,
        rounding_power = 2,
        active_opacity = 1.0,
        inactive_opacity = 1.0,
        shadow = { enabled = true, range = 4, render_power = 3, color = 0xee1a1a1a },
        blur = { enabled = true, size = 5, passes = 1, vibrancy = 0.1696 },
    },
    animations = { enabled = true },
    xwayland = { force_zero_scaling = true },
    dwindle = { preserve_split = true },
    master = { new_status = "master" },
    misc = { force_default_wallpaper = 0, disable_hyprland_logo = true },
    input = {
        kb_layout = "us,ru",
        kb_variant = "",
        kb_model = "",
        kb_options = "grp:alt_shift_toggle",
        kb_rules = "",
        follow_mouse = 1,
        sensitivity = 0,
        touchpad = { natural_scroll = false, clickfinger_behavior = true },
    },
    gestures = { workspace_swipe_distance = 480, workspace_swipe_min_speed_to_force = 0 },
})

hl.gesture({ fingers = 3, direction = "horizontal", scale = 0.7, action = "workspace" })

hl.curve("wind", { type = "bezier", points = { { 0.05, 0.9 }, { 0.1, 1.05 } } })
hl.curve("winIn", { type = "bezier", points = { { 0.1, 1.1 }, { 0.1, 1.1 } } })
hl.curve("winOut", { type = "bezier", points = { { 0.3, -0.3 }, { 0, 1 } } })
hl.curve("liner", { type = "bezier", points = { { 1, 1 }, { 1, 1 } } })
hl.curve("workspaceSmooth", { type = "bezier", points = { { 0.22, 1 }, { 0.36, 1 } } })
for _, spec in ipairs({
    { "windows", 6, "wind", "slide" },
    { "windowsIn", 6, "winIn", "slide" },
    { "windowsOut", 5, "winOut", "slide" },
    { "windowsMove", 5, "wind", "slide" },
    { "border", 1, "liner" },
    { "borderangle", 30, "liner", "loop" },
    { "fade", 10, "default" },
    { "workspaces", 7, "workspaceSmooth", "slide" },
}) do
    hl.animation({ leaf = spec[1], enabled = true, speed = spec[2], bezier = spec[3], style = spec[4] })
end

hl.bind(mainMod .. " + Q", hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + D", hl.dsp.window.close())
hl.bind(mainMod .. " + M", hl.dsp.exec_cmd("command -v hyprshutdown >/dev/null 2>&1 && hyprshutdown || hyprctl dispatch 'hl.dsp.exit()'"))
hl.bind(mainMod .. " + E", hl.dsp.exec_cmd(fileManager))
hl.bind(mainMod .. " + V", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + R", hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + SPACE", hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + P", hl.dsp.window.pseudo())
hl.bind(mainMod .. " + J", hl.dsp.layout("togglesplit"))
hl.bind(mainMod .. " + SHIFT + B", hl.dsp.exec_cmd("~/.config/waybar/launch.sh"))
hl.bind("Print", hl.dsp.exec_cmd("~/.config/hypr/screenshot.sh"))
hl.bind(mainMod .. " + L", hl.dsp.exec_cmd("~/.config/hypr/lock-screen.sh"))
hl.bind(mainMod .. " + N", hl.dsp.exec_cmd("swaync-client -t"))

for _, direction in ipairs({ "left", "right", "up", "down" }) do
    hl.bind(mainMod .. " + " .. direction, hl.dsp.focus({ direction = direction }))
end
for workspace = 1, 10 do
    local key = workspace % 10
    hl.bind(mainMod .. " + " .. key, hl.dsp.focus({ workspace = workspace }))
    hl.bind(mainMod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = workspace }))
end
hl.bind(mainMod .. " + SHIFT + S", hl.dsp.window.move({ workspace = "special:magic" }))
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up", hl.dsp.focus({ workspace = "e-1" }))
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

for key, command in pairs({
    XF86AudioRaiseVolume = "wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+",
    XF86AudioLowerVolume = "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
    XF86AudioMute = "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
    XF86AudioMicMute = "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle",
    XF86MonBrightnessUp = "brightnessctl -e4 -n2 set 5%+",
    XF86MonBrightnessDown = "brightnessctl -e4 -n2 set 5%-",
}) do
    hl.bind(key, hl.dsp.exec_cmd(command), { locked = true, repeating = true })
end
for key, command in pairs({
    XF86AudioNext = "playerctl next",
    XF86AudioPause = "playerctl play-pause",
    XF86AudioPlay = "playerctl play-pause",
    XF86AudioPrev = "playerctl previous",
}) do
    hl.bind(key, hl.dsp.exec_cmd(command), { locked = true })
end

-- Gaming mode keeps the same F12 shortcut to enter and leave the submap.
hl.bind(mainMod .. " + F12", function()
    hl.exec_cmd('touch /tmp/hypr_gaming_mode && notify-send "Gaming Mode" "ON"')
    hl.dispatch(hl.dsp.submap("gaming"))
end)
hl.define_submap("gaming", function()
    hl.bind(mainMod .. " + F12", function()
        hl.exec_cmd('rm -f /tmp/hypr_gaming_mode && notify-send "Gaming Mode" "OFF"')
        hl.dispatch(hl.dsp.submap("reset"))
    end)
end)

hl.window_rule({ name = "suppress-maximize-events", match = { class = ".*" }, suppress_event = "maximize" })
hl.window_rule({
    name = "fix-xwayland-drags",
    match = { class = "^$", title = "^$", xwayland = true, float = true, fullscreen = false, pin = false },
    no_focus = true,
})
hl.window_rule({ name = "move-hyprland-run", match = { class = "hyprland-run" }, move = "20 monitor_h-120", float = true })
hl.window_rule({
    name = "quickshell-rule", match = { class = "^(org.quickshell)$" },
    rounding = 26, rounding_power = 2, opacity = "1.0 1.0",
    border_color = "rgba(9cb3c166) rgba(7f95a144)", float = true, center = true, size = "600 600",
})
hl.window_rule({
    name = "filemanager_rule", match = { class = "thunar" },
    opacity = "0.9 0.9", float = true, size = "800 500", center = true,
})
hl.window_rule({
    name = "swaync-settings-floating", match = { class = "^(Nm-connection-editor|Blueman-manager|gnome-control-center)$" },
    float = true, size = "900 600", center = true,
})
hl.layer_rule({ name = "quickshell-power-menu-animation", match = { namespace = "^(quickshell-power-menu)$" }, no_anim = true })
hl.window_rule({
    name = "rice-updates-dialog", match = { class = "^(org.quickshell)$", title = "^(Rice Updates)$" },
    float = true, center = true, size = "740 690", animation = "popin 100%",
})
