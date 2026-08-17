# Lingarr

configarr manages a [Lingarr](https://github.com/lingarr-translate/lingarr)
instance's **translation** backend and its **arr integration**, keyed under
`lingarr.instances.<name>` (see [Sync Order](../concepts/sync-order.md) for where
Lingarr falls in a run).

Lingarr keeps every setting in one flat `key -> value` store, so both groups write
to the same `POST /api/setting/multiple/set` endpoint. configarr owns only the keys
you set — every other Lingarr setting is left untouched.

> [!NOTE]
> A key outside its group's known set (a typo, or an `integration` key placed under
> `translation`) is warned about and dropped, not written — Lingarr silently ignores
> unknown keys, so this would otherwise no-op without a trace.

## Connect

`AUTH_ENABLED=false` needs no credential, so `api_key` is optional. The settings API
returns `403` until Lingarr's onboarding has run once; configarr surfaces that as a
clear error rather than completing it (a plan stays read-only).

```yaml
lingarr:
  instances:
    main:
      base_url: http://lingarr:9876
      api_key: "" # optional; AUTH_ENABLED=false needs none
```

## Translation

The translation backend: which service, its model/endpoint/key, the prompt, and the
batch/retry knobs. Values are sent as strings, so YAML bools and ints are fine —
`true`/`false` and numbers are coerced on both sides of the diff.

```yaml
translation:
  service_type: localai # the factory id, e.g. localai / openai / gemini / deepseek
  local_ai_endpoint: https://openrouter.ai/api/v1/chat/completions
  local_ai_model: deepseek/deepseek-v4-flash
  local_ai_api_key: ${OPENROUTER_API_KEY} # secret — kept out of the plan
  ai_prompt: "Translate from {sourceLanguage} to {targetLanguage}…"
  use_batch_translation: true
  max_batch_size: 300
```

## Integration

Point Lingarr at one Sonarr and one Radarr (it is single-instance). Optional when
Lingarr is driven by Bazarr's translator provider instead.

```yaml
integration:
  sonarr_url: http://sonarr:8989
  sonarr_api_key: ${SONARR_API_KEY}
  radarr_url: http://radarr:7878
  radarr_api_key: ${RADARR_API_KEY}
```

## Diffing behaviour

Over-current: configarr GETs the keys you declared, diffs them, and writes only what
changed — undeclared settings are never sent. `*_api_key` values are fingerprinted in
the plan, so a changed key still shows as an update while its cleartext never appears
in `--plan`/JSON output.

## Full example

```yaml
lingarr:
  instances:
    main:
      base_url: http://lingarr:9876
      api_key: ""
      translation:
        service_type: localai
        local_ai_endpoint: https://openrouter.ai/api/v1/chat/completions
        local_ai_model: deepseek/deepseek-v4-flash
        local_ai_api_key: ${OPENROUTER_API_KEY}
        use_batch_translation: true
        max_batch_size: 300
      integration:
        sonarr_url: http://sonarr:8989
        sonarr_api_key: ${SONARR_API_KEY}
        radarr_url: http://radarr:7878
        radarr_api_key: ${RADARR_API_KEY}
```
