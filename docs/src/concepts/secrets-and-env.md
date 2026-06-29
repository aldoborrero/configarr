# Secrets & Environment

You should never put API keys, passwords, or webhook URLs directly in
`configarr.yml`. configarr substitutes environment variables so the file stays
safe to commit.

## `${VAR}` substitution

Any string value may contain `${VAR}` references. Before configarr does anything
with the config, it expands them against the environment:

```yaml
sonarr:
  instances:
    main:
      base_url: http://localhost:8989
      api_key: ${SONARR_API_KEY}
```

Substitution applies to **all string values**, not just `api_key` — use it for
download-client passwords, indexer keys, provider credentials, Discord webhooks,
and so on.

## Auto-loaded `.env`

A `.env` file in the **same directory as your config** is loaded automatically
before expansion:

```bash
# .env  (next to configarr.yml)
SONARR_API_KEY=abc123
RADARR_API_KEY=def456
QBIT_PASSWORD=hunter2
```

> [!NOTE]
> **Precedence**
>
> Variables already set in the process environment **take precedence** over the
> `.env` file. This lets CI or a systemd unit override a checked-in `.env` without
> editing it.

## Missing variables are left literal

If a referenced variable is not set anywhere, configarr does **not** error at parse
time — it leaves the literal text in place:

```text
api_key: ${SONARR_API_KEY}   # unset → stays the literal string "${SONARR_API_KEY}"
```

> [!WARNING]
> An unset variable surfaces later as an **authentication failure** (the API rejects
> the literal `${...}` string as a key), not as a clear "missing variable" message.
> If a service fails to authenticate, check that its variable is actually set. See
> [Troubleshooting](../troubleshooting.md#literal-var-in-output).

## Recommended layout

```text
my-media-config/
├── configarr.yml      # committed; every secret is a ${VAR}
├── .env               # gitignored; the real values
└── .gitignore         # contains: .env
```

This keeps the full, reviewable configuration in version control while the secrets
live only on the host that runs configarr.

## Passing secrets in containers and CI

- **Docker:** mount the directory so the `.env` is picked up
  (`-v "$PWD:/config"`), or pass variables with `-e SONARR_API_KEY=...` /
  `--env-file .env`.
- **CI:** set the variables as secrets in the job environment; they override any
  committed `.env` automatically because process env wins.
