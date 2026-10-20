#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1
RICE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$RICE_ROOT/installer/common.sh"
dry_run=false
case ${1:-} in
    --dry-run) dry_run=true ;;
    --help|-h)
        printf 'Использование: bash uninstall.sh [--dry-run]\nБез --dry-run: интерактивное удаление с архивом и восстановлением настроек.\n'
        exit 0 ;;
    '') ;;
    *) rice_die 'Неизвестный параметр. Используй --help.' ;;
esac
(( $# <= 1 )) || rice_die 'Слишком много параметров.'
command -v python3 >/dev/null || rice_die 'Для восстановления нужен Python 3.'
printf '\n'; rice_paint "$RICE_CYAN" '  HYPRLAND RICE · Удаление'; printf '\n'
mapfile -t installations < <(python3 "$RICE_ROOT/installer/uninstall.py" --list)
if (( ${#installations[@]} == 0 )); then
    python3 "$RICE_ROOT/installer/uninstall.py" --dry-run
    exit 0
fi
rice_note 'Будут отменены выбранная установка и все более поздние.'
rice_choose 'До какой установки вернуть систему?' 1 "${installations[@]}"
selected=${installations[RICE_CHOICE-1]%% ·*}
rice_bool packages 'Удалить также пакеты, добавленные rice?' 2
args=(--from-id "$selected")
[[ $packages != true ]] || args+=(--packages)
rice_section 'План удаления'
python3 "$RICE_ROOT/installer/uninstall.py" "${args[@]}" --dry-run
if [[ $dry_run == true ]]; then
    rice_success 'Предварительный просмотр завершён. Изменений нет.'
    exit 0
fi
rice_warn 'Перед удалением выйди из графической сессии и открой TTY (Ctrl+Alt+F3).'
rice_bool confirmed 'Начать удаление по этому плану?' 2
[[ $confirmed == true ]] || { rice_info 'Удаление отменено.'; exit 0; }
python3 "$RICE_ROOT/installer/uninstall.py" "${args[@]}" --apply
