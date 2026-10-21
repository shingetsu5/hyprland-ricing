#!/usr/bin/env python3
"""Resolve upgrades strictly; ask before excluding an installed package."""
import codecs
import datetime
import errno
import fcntl
import os
import pty
import select
import shutil
from pathlib import Path
import re
import subprocess
import sys
import termios

STOP = "Остановить обновление"
RETRY = "Повторить попытку"
ENV = dict(os.environ, LC_ALL="C")


def dialog(options, message):
    from updates_run import request_dialog
    return request_dialog(options, message)


def notify(message):
    subprocess.run(["notify-send", "Обновление Fedora", message], check=False)


def problem_packages(output, installed, excluded):
    # Prefer the installed packages whose latest update DNF explicitly rejected.
    preferred = re.findall(r"cannot install the best update candidate for package (\S+)", output)
    tokens = preferred or re.findall(r"[A-Za-z0-9_+.:-]+", output)
    found = set()
    for token in tokens:
        parts = token.rsplit("-", 2)
        if len(parts) != 3 or "." not in parts[2]:
            continue
        name = parts[0]
        arch = parts[2].rsplit(".", 1)[1]
        spec = name + "." + arch
        if spec in installed and spec not in excluded:
            found.add(spec)
    return sorted(found)


def summary(output):
    # Keep repeated curl diagnostics and long URLs in the terminal/log only.
    # A bounded message keeps the action list visible on small screens.
    if "Failed to resolve the transaction" in output or "Problem:" in output:
        reason = "Конфликт зависимостей пакетов."
    elif "Curl error (28)" in output or "Проверка превысила" in output:
        reason = "Истекло время ожидания репозитория."
    elif "Curl error" in output or "Failed to download" in output:
        reason = "Не удалось загрузить данные репозитория."
    else:
        reason = "DNF завершился с ошибкой."
    return reason + "\nПодробности — в терминале и журнале."


def run_logged(command, log):
    # DNF suppresses repository progress when stdout is a pipe. Keep stdout
    # on a PTY, while stdin still reads confirmations from the real terminal.
    master, slave = pty.openpty()
    try:
        size = shutil.get_terminal_size(fallback=(100, 24))
        termios.tcsetwinsize(slave, (size.lines, size.columns))
        with subprocess.Popen(command, env=ENV, stdout=slave,
                              stderr=subprocess.STDOUT) as process:
            os.close(slave)
            slave = None
            chunks = []
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            while True:
                if not select.select([master], [], [], 20)[0]:
                    message = "\nDNF продолжает работу; ожидаем ответ. Ctrl+C — прервать.\n"
                    print(message, end="", flush=True)
                    log.write(message)
                    log.flush()
                    continue
                try:
                    data = os.read(master, 4096)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    break  # Linux PTYs report EIO after the last writer closes.
                if not data:
                    break
                chunk = decoder.decode(data)
                print(chunk, end="", flush=True)
                log.write(chunk)
                log.flush()
                chunks.append(chunk)
            tail = decoder.decode(b"", final=True)
            if tail:
                print(tail, end="", flush=True)
                log.write(tail)
                chunks.append(tail)
            log.flush()
            output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", "".join(chunks))
            return process.wait(), output.replace("\r\n", "\n").replace("\r", "\n")
    finally:
        os.close(master)
        if slave is not None:
            os.close(slave)


def preflight_ok(code, output):
    if "Failed to resolve the transaction" in output:
        return False
    # --assumeno intentionally exits with an error after showing a valid plan.
    return code == 0 or (
        code == 1 and "Transaction Summary:" in output
        and "Operation aborted by the user." in output
    )


def update(targets, installed, log):
    excluded = set()
    # Let DNF refresh expired metadata, without forcing every repo online.
    refresh = False
    while True:
        command = ["sudo", "env", "LC_ALL=C", "dnf5", "--color=never", "--best",
                   "--setopt=skip_broken=False", "--setopt=skip_unavailable=False",
                   "--setopt=assumeyes=False", "--setopt=assumeno=False",
                   "--setopt=timeout=15", "--setopt=*.timeout=15",
                   "--setopt=skip_if_unavailable=False",
                   "--setopt=*.skip_if_unavailable=False", "upgrade"]
        if excluded:
            command.append("--exclude=" + ",".join(sorted(excluded)))
        if refresh:
            command.append("--refresh")
        command.extend(targets)
        print("\nПроверка зависимостей перед установкой…", flush=True)
        # Only the dry run has a time limit: never time out an RPM transaction.
        preflight = command.copy()
        preflight[3:3] = ["timeout", "--foreground", "--signal=INT",
                          "--kill-after=5s", "180s"]
        code, output = run_logged(preflight + ["--assumeno"], log)
        if code in (124, 137):
            message = "Проверка превысила 3 минуты. Репозиторий не отвечает или сеть слишком медленная."
            print(message, flush=True)
            log.write("\n" + message + "\n")
            output += "\n" + message
        if not preflight_ok(code, output):
            conflict = "Failed to resolve the transaction" in output
            packages = problem_packages(output, installed, excluded) if conflict else []
            choices = {}
            for package in packages:
                choices["Пропустить " + package] = package
            message = "Установка ещё не началась.\n" + summary(output)
            if choices:
                message += "\nПропуск — только на этот запуск."
            choice = dialog([STOP, *choices, RETRY], message)
            if choice in choices:
                package = choices[choice]
                excluded.add(package)
                log.write("\nUSER EXCLUDED: " + package + "\n")
                if targets and all(target in excluded for target in targets):
                    notify("Выбранный пакет пропущен. Больше нечего обновлять.")
                    return 0
                refresh = False
                continue
            if choice == RETRY:
                refresh = True
                continue
            notify("Обновление остановлено до установки пакетов.")
            return 1
        if "Nothing to do." in output:
            notify("Нет доступных обновлений для оставшихся пакетов.")
            return 0
        # Keep DNF's normal interactive transaction confirmation in the terminal.
        # The same strict flags and exclusions apply to the real transaction.
        real_command = [arg for arg in command if arg != "--refresh"]
        # Reuse the metadata just checked, while allowing RPM downloads.
        real_command.append("--setopt=cacheonly=metadata")
        code, output = run_logged(real_command, log)
        if code == 0:
            suffix = " Пропущены: " + ", ".join(sorted(excluded)) if excluded else ""
            notify("Обновление завершено." + suffix)
            return 0
        if "Operation aborted by the user." in output:
            notify("Обновление отменено.")
            return 1
        # Never exclude a package after RPM may have started changing the system.
        if dialog([STOP, RETRY], "Обновление завершилось с ошибкой.\n"
                  "Повтор запустит новую проверку.\n"
                  + summary(output)) != RETRY:
            notify("Обновление остановлено после ошибки. Подробности сохранены в журнале.")
            return 1
        refresh = True


def main():
    targets = []  # Always upgrade the full system; never offer partial Arch-style updates.
    if any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", target) for target in targets):
        raise ValueError("Invalid package name")
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "waybar-updates"
    state.mkdir(parents=True, exist_ok=True)
    with (state / "update.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            notify("Обновление уже запущено.")
            return 1
        if subprocess.run(["sudo", "-v"]).returncode:
            return 1
        installed_result = subprocess.run(["rpm", "-qa", "--qf", "%{NAME}.%{ARCH}\n"],
                                          capture_output=True, text=True, check=True)
        installed = set(installed_result.stdout.splitlines())
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = state / (stamp + ".log")
        print("Журнал обновления:", log_path, flush=True)
        with log_path.open("w") as log:
            return update(targets, installed, log)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nОбновление прервано.", flush=True)
        sys.exit(130)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print("Ошибка обновления:", error, file=sys.stderr)
        sys.exit(1)
