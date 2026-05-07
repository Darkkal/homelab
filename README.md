# My Homelab

This repository is a collection of container files and configuration scripts for my homelab setup.

The `root` folder represents the root of the linux host that the files are deployed to.

## Services

Most services are defined as container templates that are injected with environment variables and secrets by the deploy script.

Services prefixed with [root] are deployed to /etc/systemd/system.
Otherwise, services are deployed to ~/.config/containers/systemd.

### Network

There is a user-level network `homelab.network` that is used by the applcation services.

- [root] avahi: provides mDNS service discovery.
- caddy: reverse proxy for the different application services.

### Applications

- koboldcpp: ai model serving
- piclaw: isolated pi coding agent
- sillytavern: ai chat focused on roleplay

## Deployment

`deploy.sh` is used to deploy the services to the linux host.

The sequence is as follows:

1. Copy all the files from the root folder to the appropriate locations on the host.
2. Use `envsubst` to substitute environment variables in the container templates.
3. Install avahi tools and set up the avahi service.
4. Apply the aliases for the container endpoints.
5. Setup privileged port for caddy and setup caddy which depends on the application services.
