#!/usr/bin/env bash
# Shared interactive installer. Entry points set RICE_ROOT and strict Bash mode.
rice_ui_init() {
    RICE_UI_COLOR=false
    if [[ -t 1 && ${TERM:-dumb} != dumb && -z ${NO_COLOR+x} ]]; then RICE_UI_COLOR=true; fi
    RICE_RESET=$'\033[0m'
    RICE_CYAN=$'\033[1;36m'
    RICE_GREEN=$'\033[1;32m'
    RICE_YELLOW=$'\033[1;33m'
    RICE_RED=$'\033[1;31m'
    RICE_BOLD=$'\033[1m'
    RICE_DIM=$'\033[2m'
}

rice_paint() {
    local style=$1 text=$2
    if [[ ${RICE_UI_COLOR:-false} == true ]]; then
        printf '%s%s%s' "$style" "$text" "$RICE_RESET"
    else
        printf '%s' "$text"
    fi
}

rice_message() {
    local style=$1 label=$2 text=$3
    printf '\n  '; rice_paint "$style" "$label"; printf ' %s\n' "$text"
}
rice_info() { rice_message "$RICE_CYAN" '[i]' "$*"; }
rice_success() { rice_message "$RICE_GREEN" '[OK]' "$*"; }
rice_warn() { rice_message "$RICE_YELLOW" '[!]' "$*"; }
rice_error() { rice_message "$RICE_RED" '[ОШИБКА]' "$*" >&2; }
rice_note() { printf '  '; rice_paint "$RICE_DIM" "$*"; printf '\n'; }
rice_die() { rice_error "$*"; exit 1; }

rice_section() {
    printf '\n'; rice_paint "$RICE_CYAN" "  $1"; printf '\n'
    rice_paint "$RICE_DIM" '  ────────────────────────────────────────────────'; printf '\n'
}

rice_distro_name() {
    if [[ $RICE_DISTRO == arch ]]; then printf 'Arch Linux'; else printf 'Fedora 44'; fi
}

rice_banner() {
    printf '\n'; rice_paint "$RICE_CYAN" '  HYPRLAND RICE'; printf '\n'
    rice_paint "$RICE_BOLD" "  $(rice_distro_name) · Настройка рабочего стола"; printf '\n'
    if [[ $RICE_DRY_RUN == true ]]; then rice_note 'Предварительный просмотр — без изменений в системе.';
    else rice_note 'Сначала выбери настройки, затем подтверди установку.'; fi
    rice_note 'Введи номер варианта. Enter выбирает выделенный вариант.'
}

rice_summary_row() {
    local label=$1 enabled=$2
    printf '  %s: ' "$label"
    if [[ $enabled == true ]]; then rice_paint "$RICE_GREEN" 'да'; else rice_paint "$RICE_DIM" 'нет'; fi
    printf '\n'
}

rice_start_log() {
    # Keep colour in the terminal, but strip SGR escape sequences from the log.
    exec > >(tee >(sed -u $'s/\033\\[[0-9;]*m//g' >> "$1")) 2>&1
}

rice_failure() {
    if [[ -n ${RICE_RECORD:-} ]]; then
        if ! rice_checkpoint failed; then rice_warn 'Не удалось обновить журнал частичной установки.'; fi
    fi
    rice_error "Установка прервана (строка $1)."
    rice_note "Журнал: $RICE_LOG" >&2
    rice_note "Резервная копия, если создана: $RICE_BACKUP" >&2
}

rice_ui_init

rice_choose() {
    local question=$1 default=$2 answer index
    shift 2
    local -a options=("$@")
    printf '\n'; rice_paint "$RICE_BOLD" "  $question"; printf '\n\n'
    index=1
    for answer in "${options[@]}"; do
        if (( index == default )); then
            rice_paint "$RICE_GREEN" "  > [$index] $answer"; printf '  '
            rice_paint "$RICE_DIM" 'по умолчанию'
        else
            rice_paint "$RICE_CYAN" "    [$index]"; printf ' %s' "$answer"
        fi
        printf '\n'
        index=$((index + 1))
    done
    printf '\n'
    while true; do
        rice_paint "$RICE_CYAN" "  Выбор [$default] > "
        read -r answer || rice_die 'Ввод завершён. Установка отменена.'
        printf '\n'
        answer=${answer:-$default}
        case "$answer" in
            ''|*[!0-9]*) ;;
            *) if (( ${#answer} <= 2 )) && (( 10#$answer >= 1 && 10#$answer <= ${#options[@]} )); then
                   RICE_CHOICE=$((10#$answer))
                   printf '  '; rice_paint "$RICE_GREEN" "Выбрано: ${options[RICE_CHOICE-1]}"; printf '\n'
                   return 0
               fi ;;
        esac
        rice_warn "Выбери номер от 1 до ${#options[@]}."
    done
}

rice_bool() {
    local variable=$1 prompt=$2 default=${3:-2}
    rice_choose "$prompt" "$default" 'Да' 'Нет'
    if [[ $RICE_CHOICE == 1 ]]; then printf -v "$variable" true; else printf -v "$variable" false; fi
}

rice_detect_monitors() {
    local output connector modes
    if command -v hyprctl >/dev/null && command -v python3 >/dev/null; then
        if output=$(hyprctl -j monitors 2>/dev/null) && [[ -n $output ]]; then
            python3 "$RICE_ROOT/installer/configure.py" inventory <<< "$output"
            return
        fi
    fi
    for connector in /sys/class/drm/card*-*; do
        [[ -f $connector/status && $(cat "$connector/status") == connected ]] || continue
        output=${connector##*/}
        modes=$(sed 's/$/@unknown/' "$connector/modes" 2>/dev/null | paste -sd ';' -) || modes=
        printf '%s\t%s\n' "${output#*-}" "$modes"
    done
}

rice_monitor_options() {
    local name=$1 modes=${2:-} resolution refresh scale default_scale
    local -a resolutions=(preferred 1920x1080 2560x1440 3072x1920 3840x2160)
    local -a rates=(60 75 90 120 144 165 240)
    local -a scales=(1 1.5 2)
    while true; do
        rice_choose "Разрешение: ${name:-все экраны (правило по умолчанию)}" 1 \
            'Автоматически (режим, рекомендованный монитором)' \
            '1080p — 1920×1080' '1440p / 2K — 2560×1440' '3K — 3072×1920' '4K — 3840×2160'
        resolution=${resolutions[RICE_CHOICE-1]}
        refresh=auto
        if [[ $resolution != preferred ]]; then
            rice_choose 'Частота обновления' 1 '60 Гц (по умолчанию)' '75 Гц' '90 Гц' '120 Гц' '144 Гц' '165 Гц' '240 Гц'
            refresh=${rates[RICE_CHOICE-1]}
        fi
        if [[ -n $modes && $resolution != preferred ]]; then
            if [[ ";$modes;" != *";$resolution@"* ]]; then
                rice_warn 'Монитор не сообщил о поддержке выбранного режима. Выбери другой или автоматический.'
                continue
            fi
            if [[ $modes == *'@unknown'* ]]; then
                rice_warn 'Разрешение найдено в списке экрана; частоту вне сессии Hyprland проверить нельзя.'
            elif command -v python3 >/dev/null && ! python3 "$RICE_ROOT/installer/configure.py" supported "$modes" "$resolution" "$refresh"; then
                rice_warn 'Монитор не сообщил о поддержке выбранного режима. Выбери другой или автоматический.'
                continue
            fi
        fi
        break
    done
    default_scale=1
    [[ $resolution != 3840x2160 ]] || default_scale=2
    [[ $resolution != 3072x1920 ]] || default_scale=3
    rice_choose 'Масштаб интерфейса' "$default_scale" '100%' '150%' '200%'
    scale=${scales[RICE_CHOICE-1]}
    RICE_MONITOR_RULES+=("$name|$resolution|$refresh|$scale")
}

rice_collect_options() {
    local name modes battery_default=2
    local -a screens=()
    RICE_MONITOR_RULES=()
    for name in /sys/class/power_supply/*/type; do
        [[ -f $name && $(cat "$name") == Battery ]] && battery_default=1
    done
    rice_section '[1/5] Панель и батарея'
    rice_bool RICE_BATTERY 'Добавить батарею в Waybar?' "$battery_default"
    rice_section '[2/5] Настройка экранов'
    mapfile -t screens < <(rice_detect_monitors)
    if (( ${#screens[@]} )); then
        for name in "${screens[@]}"; do
            IFS=$'\t' read -r name modes <<< "$name"
            rice_monitor_options "$name" "${modes:-}"
        done
    else
        rice_warn 'Подключённые мониторы не определены. Настроим общее правило для экранов.'
        rice_monitor_options ''
    fi
    rice_section '[3/5] Обои и курсор'
    rice_bool RICE_WALLPAPERS 'Скопировать обои из репозитория? Одноимённые файлы останутся прежними.' 1
    rice_bool RICE_CURSOR 'Заменить текущий курсор на Bibata Modern Ice?' 1
    rice_section '[4/5] Дополнительные компоненты'
    rice_bool RICE_SDDM 'Установить SDDM и выбрать его менеджером входа? Нет — сохранить текущий.' 2
    rice_bool RICE_ZSH 'Установить Zsh и Oh My Zsh, сделать Zsh основной оболочкой?' 1
    RICE_COPR=false
    if [[ $RICE_DISTRO == fedora ]]; then
        rice_bool RICE_COPR 'Подключить COPR sdegler/hyprland для компонентов Hyprland? Нужен на чистой Fedora 44.' 1
    fi
}

rice_summary() {
    local rule screen resolution refresh scale percent
    rice_section '[5/5] Проверь выбранные настройки'
    printf '  Система: '; rice_paint "$RICE_BOLD" "$(rice_distro_name)"; printf '\n\n'
    rice_summary_row 'Батарея' "$RICE_BATTERY"
    rice_summary_row 'Обои из репозитория' "$RICE_WALLPAPERS"
    rice_summary_row 'Курсор Bibata' "$RICE_CURSOR"
    rice_summary_row 'Установить SDDM' "$RICE_SDDM"
    rice_summary_row 'Установить Oh My Zsh' "$RICE_ZSH"
    [[ $RICE_DISTRO != fedora ]] || rice_summary_row 'Подключить COPR sdegler/hyprland' "$RICE_COPR"
    printf '\n'
    for rule in "${RICE_MONITOR_RULES[@]}"; do
        IFS='|' read -r screen resolution refresh scale <<< "$rule"
        case $scale in 1) percent=100% ;; 1.5) percent=150% ;; 2) percent=200% ;; esac
        [[ $resolution != preferred ]] || resolution='автоматически'
        [[ $refresh != auto ]] || refresh='автоматически'
        printf '  '; rice_paint "$RICE_CYAN" "Монитор ${screen:-по умолчанию}"
        printf ': %s, частота %s, масштаб %s\n' "$resolution" "$refresh" "$percent"
    done
    rice_warn 'Конфиги будут заменены с резервной копией.'
    if [[ $RICE_ZSH == true ]]; then
        rice_note 'Zsh станет основной оболочкой со следующего входа. .bashrc сохранится.'
    else
        rice_note '.bashrc и текущая оболочка сохранятся.'
    fi
    if [[ $RICE_DISTRO == fedora ]]; then
        rice_note 'Оформление и символы Nerd Fonts: архивы GitHub с проверкой SHA-256.'
    else
        rice_note 'Оформление и wlogout: AUR через yay.'
    fi
}

rice_read_packages() {
    local line
    RICE_PACKAGES=()
    while IFS= read -r line || [[ -n $line ]]; do
        [[ -z $line || $line == \#* ]] || RICE_PACKAGES+=("$line")
    done < "$1"
    (( ${#RICE_PACKAGES[@]} > 0 )) || rice_die "Пустой список пакетов: $1"
}

rice_package_inventory() {
    if [[ $RICE_DISTRO == arch ]]; then pacman -Qq; else rpm -qa --qf '%{NAME}.%{ARCH}\n' | sed '/^gpg-pubkey\.(none)$/d'; fi
}

rice_capture_before() {
    local raw unit manager key relative
    raw="$RICE_RECORD/raw"
    (umask 077; mkdir -p "$raw/home")
    printf '%s\n%s\n%s\n' "$RICE_DISTRO" "$HOME" "$(id -un)" > "$raw/metadata"
    rice_package_inventory > "$raw/packages-before"
    [[ -s $raw/packages-before ]] || rice_die 'Не удалось сохранить список установленных пакетов.'
    cp "$raw/packages-before" "$raw/packages-baseline"
    getent passwd "$(id -un)" | cut -d: -f7 > "$raw/shell"
    systemctl get-default > "$raw/default-target" 2>/dev/null || true
    manager=$(readlink /etc/systemd/system/display-manager.service || true)
    printf '%s\n' "${manager##*/}" > "$raw/display-manager"
    : > "$raw/services"
    for unit in bluetooth.service NetworkManager.service power-profiles-daemon.service tuned.service tuned-ppd.service sddm.service "${manager##*/}"; do
        [[ -n $unit ]] || continue
        key=$(systemctl is-enabled "$unit" 2>/dev/null || true)
        printf '%s\t%s\n' "$unit" "$key" >> "$raw/services"
    done
    for key in gtk-theme icon-theme cursor-theme color-scheme; do
        gsettings get org.gnome.desktop.interface "$key" > "$raw/gsettings-$key" 2>/dev/null || true
    done
    for relative in .config/gtk-3.0/settings.ini .config/gtk-4.0/settings.ini .zshrc; do
        if [[ -e $HOME/$relative || -L $HOME/$relative ]]; then
            mkdir -p "$raw/home/$(dirname -- "$relative")"
            cp -a -- "$HOME/$relative" "$raw/home/$relative"
        fi
    done
    if [[ -e $HOME/.oh-my-zsh || -L $HOME/.oh-my-zsh ]]; then printf true; else printf false; fi > "$raw/oh-my-zsh-existed"
    if [[ -f /etc/yum.repos.d/_copr:copr.fedorainfracloud.org:sdegler:hyprland.repo ]]; then
        cp /etc/yum.repos.d/_copr:copr.fedorainfracloud.org:sdegler:hyprland.repo "$raw/copr.repo"
    fi
    printf 'sddm\t%s\nzsh\t%s\ncopr\t%s\n' "$RICE_SDDM" "$RICE_ZSH" "$RICE_COPR" > "$raw/options"
}

rice_checkpoint() {
    [[ -n ${RICE_RECORD:-} ]] || return 0
    if command -v python3 >/dev/null; then
        python3 "$RICE_ROOT/installer/state.py" --record "$RICE_RECORD" --backup "$RICE_BACKUP" --phase "$1"
    fi
}

rice_install_packages() {
    local -a packages aur
    if [[ $RICE_DISTRO == arch ]]; then
        rice_read_packages "$RICE_ROOT/pkglist_pacman.txt"; packages=("${RICE_PACKAGES[@]}")
        [[ $RICE_SDDM != true ]] || packages+=(sddm)
        [[ $RICE_ZSH != true ]] || packages+=(zsh)
        # Upgrades belong to the OS, not to the removable rice package set.
        printf upgrade > "$RICE_RECORD/raw/package-mode"
        sudo pacman -Syu
        rice_package_inventory > "$RICE_RECORD/raw/packages-baseline.new"
        mv "$RICE_RECORD/raw/packages-baseline.new" "$RICE_RECORD/raw/packages-baseline"
        printf rice > "$RICE_RECORD/raw/package-mode"
        rice_checkpoint upgraded
        sudo pacman -S --needed "${packages[@]}"
        rice_checkpoint packages
        if ! command -v yay >/dev/null; then
            git clone https://aur.archlinux.org/yay.git "$RICE_TEMP/yay"
            (cd "$RICE_TEMP/yay" && makepkg -si)
        fi
        rice_read_packages "$RICE_ROOT/pkglist_aur.txt"; aur=("${RICE_PACKAGES[@]}")
        [[ $RICE_CURSOR != true ]] || aur+=(bibata-cursor-theme)
        yay -S --needed "${aur[@]}"
        rice_checkpoint packages
        RICE_POWER_SERVICE=power-profiles-daemon
    else
        if [[ $RICE_COPR == true ]]; then
            sudo dnf5 install dnf5-plugins
            sudo dnf5 copr enable sdegler/hyprland
            rice_checkpoint packages
        fi
        rice_read_packages "$RICE_ROOT/pkglist_fedora.txt"; packages=("${RICE_PACKAGES[@]}")
        [[ $RICE_SDDM != true ]] || packages+=(sddm)
        [[ $RICE_ZSH != true ]] || packages+=(zsh)
        if rpm -q power-profiles-daemon >/dev/null 2>&1; then
            RICE_POWER_SERVICE=power-profiles-daemon
        else
            packages+=(tuned-ppd); RICE_POWER_SERVICE=tuned
        fi
        sudo dnf5 --best --setopt=skip_unavailable=False --setopt=skip_broken=False install "${packages[@]}"
        rice_checkpoint packages
        python3 "$RICE_ROOT/installer/assets.py" --output "$RICE_TEMP/assets" --cursor "$RICE_CURSOR"
    fi
}

rice_prepare_and_install() {
    local -a args=()
    local rule
    for rule in "${RICE_MONITOR_RULES[@]}"; do args+=(--monitor "$rule"); done
    python3 "$RICE_ROOT/installer/configure.py" prepare --root "$RICE_ROOT" \
        --stage "$RICE_TEMP/home" --target-home "$HOME" --battery "$RICE_BATTERY" \
        --cursor "$RICE_CURSOR" --wallpapers "$RICE_WALLPAPERS" "${args[@]}"
    if [[ $RICE_DISTRO == fedora ]]; then cp -a "$RICE_TEMP/assets/." "$RICE_TEMP/home/"; fi
    python3 "$RICE_ROOT/installer/configure.py" check-themes --stage "$RICE_TEMP/home" --cursor "$RICE_CURSOR"
    bash "$RICE_TEMP/home/.config/waybar/scripts/build-clock-hover.sh"
    mkdir -p "$RICE_TEMP/runtime"; chmod 700 "$RICE_TEMP/runtime"
    if ! env HOME="$RICE_TEMP/home" XDG_CONFIG_HOME="$RICE_TEMP/home/.config" \
        XDG_RUNTIME_DIR="$RICE_TEMP/runtime" Hyprland --verify-config \
        --config "$RICE_TEMP/home/.config/hypr/hyprland.conf" > "$RICE_TEMP/hyprland-check.log" 2>&1; then
        cat "$RICE_TEMP/hyprland-check.log"; rice_die 'Hyprland отклонил конфиг. Текущие конфиги не заменены.'
    fi
    python3 "$RICE_ROOT/installer/configure.py" deploy --stage "$RICE_TEMP/home" \
        --target-home "$HOME" --backup "$RICE_BACKUP"
    rice_checkpoint configured
    fc-cache -f
}

rice_enable_services() {
    local current
    sudo systemctl enable bluetooth NetworkManager "$RICE_POWER_SERVICE"
    if [[ $RICE_POWER_SERVICE == tuned ]]; then sudo systemctl enable tuned-ppd; fi
    if [[ $RICE_SDDM == true ]]; then
        current=$(readlink /etc/systemd/system/display-manager.service || true)
        if [[ -n $current && ${current##*/} != sddm.service ]]; then sudo systemctl disable "${current##*/}"; fi
        sudo systemctl enable sddm
        sudo systemctl set-default graphical.target
    fi
    if ! systemctl --user daemon-reload; then
        rice_warn 'Пользовательская сессия systemd недоступна. Служба будет прочитана при следующем входе.'
    fi
}

rice_install_zsh() {
    [[ $RICE_ZSH == true ]] || return 0
    local zsh_path user account current_shell
    if [[ ! -d $HOME/.oh-my-zsh ]]; then
        curl --fail --location --retry 3 --connect-timeout 20 \
            https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -o "$RICE_TEMP/oh-my-zsh.sh"
        [[ -s $RICE_TEMP/oh-my-zsh.sh ]] || rice_die 'Получен пустой установщик Oh My Zsh.'
        RUNZSH=no CHSH=no KEEP_ZSHRC=yes sh "$RICE_TEMP/oh-my-zsh.sh"
    fi
    zsh_path=$(command -v zsh) || rice_die 'Zsh не найден после установки.'
    command -v chsh >/dev/null || rice_die 'Не найден chsh для смены основной оболочки.'
    user=$(id -un)
    account=$(getent passwd "$user") || rice_die 'Не удалось определить текущую оболочку пользователя.'
    current_shell=${account##*:}
    if [[ $(readlink -f -- "$current_shell") != $(readlink -f -- "$zsh_path") ]]; then
        sudo chsh -s "$zsh_path" "$user"
        account=$(getent passwd "$user") || rice_die 'Не удалось проверить смену оболочки.'
        current_shell=${account##*:}
        [[ $(readlink -f -- "$current_shell") == $(readlink -f -- "$zsh_path") ]] || \
            rice_die 'Основная оболочка не изменилась. Проверь настройки учётной записи.'
    fi
    rice_success 'Zsh настроен как основная оболочка.'
    rice_note 'Изменение вступит в силу после выхода из учётной записи и повторного входа.'
}

rice_preflight() {
    local distro version file
    [[ $RICE_DRY_RUN == true || $(id -u) != 0 ]] || rice_die 'Запускай от обычного пользователя, не от root.'
    [[ ! -e /run/ostree-booted ]] || rice_die 'Fedora Atomic не поддерживается этим установщиком.'
    distro=$(. /etc/os-release; printf '%s' "$ID")
    version=$(. /etc/os-release; printf '%s' "${VERSION_ID:-}")
    if [[ $RICE_DRY_RUN != true ]]; then
        [[ $distro == "$RICE_DISTRO" ]] || rice_die "Этот установщик рассчитан на $RICE_DISTRO; обнаружена $distro."
        [[ $RICE_DISTRO != fedora || $version == 44 ]] || rice_die 'Установщик Fedora проверен для Fedora 44.'
        command -v sudo >/dev/null || rice_die 'Нужен sudo.'
        if [[ $RICE_DISTRO == arch ]]; then command -v pacman >/dev/null || rice_die 'Не найден pacman.'
        else command -v dnf5 >/dev/null || rice_die 'Не найден dnf5.'; fi
    fi
    for file in installer/configure.py installer/state.py installer/assets.py installer/assets.json pkglist_pacman.txt pkglist_aur.txt pkglist_fedora.txt hypr/hyprland.conf; do
        [[ -s $RICE_ROOT/$file ]] || rice_die "Не найден обязательный файл: $file"
    done
}

rice_main() {
    RICE_DISTRO=$1; shift
    rice_ui_init
    RICE_DRY_RUN=false
    while (( $# )); do
        case "$1" in
            --dry-run) RICE_DRY_RUN=true ;;
            --help|-h) printf 'Использование: %s [--dry-run]\nИнтерактивный выбор готовых настроек. --dry-run показывает план без установки и записи файлов.\nNO_COLOR=1 отключает цветное оформление.\n' "$0"; return 0 ;;
            *) rice_die "Неизвестный параметр: $1" ;;
        esac
        shift
    done
    rice_banner
    rice_preflight
    rice_collect_options
    rice_summary
    if [[ $RICE_DRY_RUN == true ]]; then rice_success 'Предварительный просмотр завершён. Изменений нет.'; return 0; fi
    rice_bool RICE_CONFIRMED 'Применить этот план?' 2
    [[ $RICE_CONFIRMED == true ]] || { rice_info 'Установка отменена.'; return 0; }
    local stamp state_dir
    stamp=$(date +%Y%m%d-%H%M%S)-$$
    state_dir=${XDG_STATE_HOME:-$HOME/.local/state}/arch-hyprland-ricing
    RICE_BACKUP="$state_dir/backups/$stamp"
    RICE_RECORD="$state_dir/installations/$stamp"
    mkdir -p "$state_dir/logs"
    RICE_LOG="$state_dir/logs/$stamp.log"
    rice_start_log "$RICE_LOG"
    RICE_TEMP=$(mktemp -d)
    trap 'rm -rf -- "$RICE_TEMP"' EXIT
    trap 'rice_failure "$LINENO"' ERR
    trap 'rice_checkpoint interrupted || true; exit 130' INT
    trap 'rice_checkpoint interrupted || true; exit 143' TERM HUP
    sudo -v
    rice_capture_before
    rice_section 'Установка · 1/4 — Пакеты и оформление'
    rice_install_packages
    rice_success 'Пакеты и оформление подготовлены.'
    rice_section 'Установка · 2/4 — Проверка и перенос конфигов'
    rice_prepare_and_install
    rice_success 'Конфиги проверены и установлены.'
    rice_section 'Установка · 3/4 — Системные службы'
    rice_enable_services
    rice_section 'Установка · 4/4 — Завершение'
    rice_install_zsh
    rice_checkpoint complete
    rice_success 'Установка завершена.'
    rice_note "Резервные копии: $RICE_BACKUP"
    rice_note "Журнал: $RICE_LOG"
    rice_bool RICE_REBOOT 'Перезагрузить компьютер сейчас?' 2
    [[ $RICE_REBOOT != true ]] || sudo systemctl reboot
    return 0
}
