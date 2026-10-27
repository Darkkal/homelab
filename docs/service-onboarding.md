# Service onboarding checklist

Use this checklist when adding a service and retain each decision, repository change, verification and exception in its issue or pull request. Existing [configuration](configuration.md), [architecture](architecture.md) and [lifecycle](system-service-lifecycle.md) references contain the detailed conventions. A source review does not establish live deployment acceptance.

## Placement, state and lifecycle

- [ ] Select the host group and service in `playbooks/site.yml` and the Quadlet role's task selection. Choose stable container, Quadlet and systemd unit names. Record upstream dependencies and startup ordering.
- [ ] Identify persistent directories in `roles/base/tasks/main.yml`, configuration ownership, rootless UID/GID and SELinux mount labels. Keep secrets in protected sources; do not commit recipient lists, credentials or production inventory. Decide which data and identity must be backed up together before migrations.
- [ ] Define startup, readiness and shutdown bounds, health checks and failure behaviour. A running container or an unhealthy status alone does not prove readiness or enforce a deadline. Document the image version, update policy, dependencies and any override required for safe updates.
- [ ] Document initial configuration and credential provisioning, including application public URL, allowed origins, cookie security and trusted proxy settings where applicable. Never print protected configuration, credentials, headers or complete environment values during verification.

## Discovery, naming and access

- [ ] Select Homepage discovery or record why it is omitted. For a discovered UI, set the group, name, icon, description and link in its Quadlet. Follow [Homepage labels and quoting](configuration.md#adding-new-services-to-the-homepage-dashboard); add a matching layout group in `roles/quadlets/templates/homepage.settings.yaml.j2` when needed.
- [ ] Select a LAN name such as `<service>.{{ lan_domain }}`; the default suffix is `home`. Check the [LAN hostname reference](configuration.md#lan-hostname-suffix), DNS wildcard behaviour, Caddy upstream default and Caddyfile route. Local HTTPS clients need the appropriate Caddy CA trust. Avoid hard-coding `.home` in generated names.
- [ ] Record the container port and protocol, host bind address, host-published port if any, and the variable/default that owns each choice. Compare source allocations and bindings, including TCP versus UDP. Actual listener conflicts require separately authorised host evidence. Caddy can reach a container port on `homelab.network` without publishing that backend port on the host.
- [ ] Where direct host access is intentionally provided, update the mapping in `roles/quadlets/templates/homepage.custom.js.j2` and document its port and protocol. IP-based rewriting assumes Homepage and the target are on the same host; check split-host deployments separately. Direct HTTP does not inherit Caddy's HTTPS protection.
- [ ] For a private or headless service, record explicit reasons for omitted UI labels, LAN route and host publication. Example: `<backend>` has no user interface, listens only on its container port, and is reached by an authorised peer on the shared network; decide its availability monitoring separately. Shared rootless networks are not an access-control boundary.

## Availability and telemetry

- [ ] Choose an availability check and service identity, or record why no check is appropriate. Map HTTP targets and pipelines in `roles/quadlets/templates/otel-collector.yaml.j2`; the existing service-health dashboard and down monitor group availability by `http_url`, not application service identity. A private service may still need a check.
- [ ] For native OTLP and Prometheus, record upstream capability evidence, endpoint and protocol, application identity, protected credential references, and receiver, pipeline and exporter wiring. The existing OTLP receiver alone does not instrument an application. Label signals unsupported only when evidence establishes that; otherwise record them as unconfigured or unverified. Record reasons for each omitted signal. Preserve certificate verification and do not copy TLS bypasses.
- [ ] Select or add relevant dashboard and monitor definitions in `roles/quadlets/files/dashboards/`, provisioned by `roles/quadlets/tasks/uptrace-dashboards.yml` and `roles/quadlets/filter_plugins/uptrace_monitors.py`. Existing monitor notifications are UI-only. See [Uptrace observability](architecture.md#uptrace-observability).

## Source checks and authorised operations

- [ ] Review the changed templates, references, links, port allocation and dependency graph. Run relevant existing offline checks and `git diff --check`; distinguish these from host validation.
- [ ] In the separately authorised deployment workflow, validate protected configuration without displaying values, verify connectivity, readiness and telemetry, and check a repeat apply for unwanted changes. Verify backup and restoration requirements before data migrations. Document stop/backout and the limits of a source revert: it does not automatically restore persistent data or undo schema changes.

## Worked file map: SillyTavern

This map describes repository configuration, not a claim that a live deployment or every checklist item is verified.

| Decision | Repository source |
| --- | --- |
| Placement and state | `playbooks/site.yml` selects `sillytavern`; `roles/base/tasks/main.yml` creates its state directories. `roles/quadlets/tasks/sillytavern.yml` manages configuration and restart handling. |
| Unit, mounts and direct port | `roles/quadlets/templates/sillytavern.container.j2` defines the image, persistent mounts, Homepage labels and `PublishPort` from `sillytavern_port` to container TCP port `8000`. `inventory/group_vars/service_hosts.yml` supplies the default `8000`. |
| Name and proxy | The Quadlet label uses `sillytavern.{{ lan_domain }}`. `roles/caddy/defaults/main.yml` selects `sillytavern:8000`; `roles/caddy/templates/Caddyfile.j2` routes the LAN name. `inventory/group_vars/all/vars.yml` supplies `lan_domain`. |
| Homepage | The label group is `Web Services`; `roles/quadlets/templates/homepage.settings.yaml.j2` contains the layout and `roles/quadlets/templates/homepage.custom.js.j2` maps direct access to `sillytavern_port`. |
| Availability | `roles/quadlets/templates/otel-collector.yaml.j2` checks `http://sillytavern:8000/`. `roles/quadlets/files/dashboards/homelab-service-health.yml` uses `http_url`; dashboard and monitor provisioning uses the task and filter named above. |
| Native telemetry and acceptance | The mapped collector check establishes configured availability only. Application OTLP/Prometheus support, instrumentation, live readiness and deployment acceptance are unverified here; record decisions and evidence before treating those items as complete. |

Web Gallery is present in the route and Homepage labels but absent from the current direct-link rewrite map and collector HTTP-check targets. Track those omissions separately rather than assuming discovery implies either integration.
