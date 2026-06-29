# Installation

configarr is distributed two ways: as a [Nix](https://nixos.org) flake and as a
container image on the GitHub Container Registry. Pick whichever fits your setup —
both run the exact same code.

## Run with Nix

The fastest way to try it, with nothing to install permanently:

```bash
nix run github:aldoborrero/configarr -- --config configarr.yml
```

`nix run` builds configarr from the flake and runs it in one step. Everything
after `--` is passed straight to configarr (see the
[Command Line](../reference/cli.md) reference).

To add it to a dev shell or system profile, reference the flake's default package
(`github:aldoborrero/configarr#configarr`).

> [!TIP]
> Pin to a specific commit or tag for reproducibility, e.g.
> `nix run github:aldoborrero/configarr/v0.1.0 -- --config configarr.yml`.

## Run with Docker

A multi-purpose image is published to `ghcr.io/aldoborrero/configarr`. The
container's working directory is `/config`, and configarr defaults to
`./configarr.yml`, so mounting your config there needs no extra arguments:

```bash
docker run --rm \
  -v "$PWD/configarr.yml:/config/configarr.yml" \
  ghcr.io/aldoborrero/configarr:latest
```

If you keep secrets in a `.env` next to the config, mount the whole directory
instead — configarr auto-loads a `.env` from the config's directory:

```bash
docker run --rm \
  -v "$PWD:/config" \
  ghcr.io/aldoborrero/configarr:latest --debug
```

> [!WARNING]
> **Networking from inside a container**
>
> URLs like `http://localhost:8989` resolve to the **container**, not your host. If
> your *arr apps run elsewhere, use their reachable address: a Docker network alias
> (`http://sonarr:8989`), the host gateway
> (`--add-host=host.docker.internal:host-gateway` then
> `http://host.docker.internal:8989`), or a LAN IP.

## Run from source

configarr is a standard Python package (`>=3.12`). With the flake's dev shell:

```bash
nix develop          # provides python313, ruff, mypy, and the docs toolchain
python -m configarr --config configarr.yml
```

## Editing with the Claude skill

This repository ships a [Claude Code](https://claude.com/claude-code) skill,
`configarr-config`, that helps you write and validate `configarr.yml`. It is
backed by the same source-verified reference embedded in this book's
[Configuration Schema](../reference/schema.md) chapter, so Claude uses the exact
keys configarr accepts rather than guessing from the native *arr APIs.

```text
/plugin marketplace add aldoborrero/configarr
/plugin install configarr
```

## Next steps

Head to the [Quick Start](quick-start.md) to write your first config and run it.
