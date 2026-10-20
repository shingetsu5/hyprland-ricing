#!/usr/bin/env bash
set -euo pipefail
read -r _ u n s i w q f t _ < /proc/stat
before_idle=$((i+w)); before_total=$((u+n+s+i+w+q+f+t))
sleep 0.25
read -r _ u n s i w q f t _ < /proc/stat
delta=$((u+n+s+i+w+q+f+t-before_total))
usage=0
if ((delta > 0)); then usage=$((100 * (delta - (i+w-before_idle)) / delta)); fi
temp=$(sensors 2>/dev/null | awk '/Package id 0:/ {gsub(/[+°C]/,"",$4); print $4; exit}' || true)
freq=$(awk '{sum+=$1; n++} END{if(n) printf "%.0f",sum/n/1000; else print "n/a"}' /sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq 2>/dev/null || true)
load=$(awk '{print $1" "$2" "$3}' /proc/loadavg)
class=ok; temp_num=${temp%%.*}; temp_num=${temp_num:-0}
if ((temp_num >= 85 || usage >= 90)); then class=crit; elif ((temp_num >= 75 || usage >= 70)); then class=warn; fi
jq -cn --arg text "$usage" --arg tooltip "CPU: ${temp:-n/a} °C"$'\n'"Frequency: ${freq:-n/a} MHz"$'\n'"Load: $load" --arg class "$class" '{text:$text,tooltip:$tooltip,class:$class}'
