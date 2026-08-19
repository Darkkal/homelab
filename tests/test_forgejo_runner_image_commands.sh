#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
registration_task="$repo_root/roles/forgejo_runner/tasks/main.yml"
quadlet_template="$repo_root/roles/forgejo_runner/templates/forgejo-runner.container.j2"
config_template="$repo_root/roles/forgejo_runner/templates/config.yaml.j2"
handler="$repo_root/roles/forgejo_runner/handlers/main.yml"

! rg -q -- 'Register Forgejo runner|forgejo_runner_registration_result' "$registration_task"
rg -q -- '^Exec=forgejo-runner daemon --config /data/config.yaml$' "$quadlet_template"
rg -Fq -- '      uuid: "{{ forgejo_runner_uuid }}"' "$config_template"
rg -Fq -- '      token: "{{ forgejo_runner_token }}"' "$config_template"
rg -q -- '^    daemon_reload: true$' "$handler"
rg -q -- 'name: Reload Forgejo runner user systemd' "$registration_task"
