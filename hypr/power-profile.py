#!/usr/bin/env python3
"""Control power-profiles-daemon or Fedora tuned-ppd through their shared D-Bus API."""
import argparse
import re
import subprocess
import sys

PROVIDERS = (
    ('org.freedesktop.UPower.PowerProfiles', '/org/freedesktop/UPower/PowerProfiles'),
    ('net.hadess.PowerProfiles', '/net/hadess/PowerProfiles'),
)


def control(action, profile=None):
    errors = []
    for service, path in PROVIDERS:
        result = subprocess.run(['busctl', '--system', 'get-property', service, path,
                                 service, 'ActiveProfile'], capture_output=True, text=True, timeout=10)
        match = re.fullmatch(r's "([a-z-]+)"\s*', result.stdout)
        if result.returncode or not match:
            errors.append(result.stderr.strip())
            continue
        if action == 'get':
            print(match[1])
            return 0
        result = subprocess.run(['busctl', '--system', '--allow-interactive-authorization=yes',
                                 'set-property', service, path, service, 'ActiveProfile', 's', profile],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            print(result.stderr.strip() or 'Не удалось сменить профиль питания', file=sys.stderr)
        return result.returncode
    print('Служба профилей питания недоступна. ' + '; '.join(filter(None, errors)), file=sys.stderr)
    return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('get', 'set'))
    parser.add_argument('profile', nargs='?', choices=('power-saver', 'balanced', 'performance'))
    args = parser.parse_args()
    if args.action == 'set' and args.profile is None:
        parser.error('set requires a profile')
    try:
        sys.exit(control(args.action, args.profile))
    except (OSError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
