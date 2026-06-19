# Smart Search CLI Contract

## Entrypoints

- `smart-search` is the primary CLI.
- `smart-search --version`, `smart-search --v`, and `smart-search -v` print the installed version and exit with code `0`.
- `smart-search` should resolve from the user's PATH.
- This bundled skill is maintained with the `smartsearch` repository.
- Private API keys should be saved with `smart-search setup` or `smart-search config set`.
- Environment variables remain supported for CI and advanced users, and override the local config file.
- Do not depend on MCP inline `env` values or committed API-key environment variables for CLI use.
- On Windows with mise, the managed package name is `npm:@konbakuyomu/smart-search`; the executable remains `smart-search`. Diagnose mise managed installs with `mise ls "npm:@konbakuyomu/smart-search"` and `mise which smart-search` (the bare name `smart-search` is the bin, not a mise tool identifier).
- In sandboxed runtimes (Codex CLI, containers, CI) where subprocesses cannot read the user's `~/.config`, set `SMART_SEARCH_CONFIG_DIR` to an absolute writable path. The CLI uses it for both config and logs.

## Commands

- `smart-search search QUERY [--platform NAME] [--model ID] [--extra-sources N] [--validation fast|balanced|strict] [--fallback auto|off] [--providers auto|CSV] [--timeout SECONDS] [--format json|markdown|content] [--output PATH]`
- `smart-search fetch URL [--format json|markdown|content] [--output PATH]`
- `smart-search exa-search QUERY [--num-results N] [--search-type neural|keyword|auto] [--include-text] [--include-highlights] [--start-published-date YYYY-MM-DD] [--include-domains DOMAIN...] [--exclude-domains DOMAIN...] [--category NAME] [--format json|markdown|content] [--output PATH]`
- `smart-search exa-similar URL [--num-results N] [--format json|markdown|content] [--output PATH]`
- `smart-search zhipu-search QUERY [--count N] [--search-engine NAME] [--search-recency-filter VALUE] [--search-domain-filter DOMAIN] [--content-size medium|high] [--format json|markdown|content] [--output PATH]`
- `smart-search context7-library NAME [QUERY] [--format json|markdown|content] [--output PATH]`
- `smart-search context7-docs LIBRARY_ID QUERY [--format json|markdown|content] [--output PATH]`
- `smart-search deep QUERY [--budget quick|standard|deep] [--evidence-dir PATH] [--format json|markdown|content] [--output PATH]`
- `smart-search map URL [--instructions TEXT] [--max-depth N] [--max-breadth N] [--limit N] [--timeout SECONDS] [--format json|markdown|content] [--output PATH]`
- `smart-search doctor [--format json|markdown|content] [--output PATH]`
- `smart-search setup [--lang zh|en] [--advanced] [--non-interactive] [--skip-skills] [--install-skills CSV] [--skills-root PATH] [--xai-api-url URL] [--xai-api-key KEY] [--xai-model ID] [--xai-tools-explicit CSV] [--openai-compatible-api-url URL] [--openai-compatible-api-key KEY] [--openai-compatible-model ID] [--validation-level fast|balanced|strict] [--fallback-mode auto|off] [--minimum-profile standard|off] [--exa-key KEY] [--context7-key KEY] [--zhipu-key KEY] [--zhipu-api-url URL] [--zhipu-search-engine ENGINE] [--tavily-api-url URL] [--tavily-key KEY] [--firecrawl-api-url URL] [--firecrawl-key KEY] [--format json|markdown|content] [--output PATH]`
- `smart-search config path [--format json|markdown|content] [--output PATH]`
- `smart-search config list [--format json|markdown|content] [--output PATH]`
- `smart-search config set KEY VALUE [--format json|markdown|content] [--output PATH]`
- `smart-search config unset KEY [--format json|markdown|content] [--output PATH]`
- `smart-search model set MODEL [--format json|markdown|content] [--output PATH]`
- `smart-search model current [--format json|markdown|content] [--output PATH]`
- `smart-search regression`
- `smart-search smoke [--mode mock|live] [--mock] [--live] [--format json|markdown|content] [--output PATH]`
- `smart-search --version`

## Aliases

Top-level aliases must normalize to the same service behavior as their full command:

| Full command | Aliases |
| --- | --- |
| `smart-search --version` | `smart-search --v`, `smart-search -v` |
| `search` | `s` |
| `fetch` | `f` |
| `map` | `m` |
| `exa-search` | `exa`, `x` |
| `exa-similar` | `xs` |
| `zhipu-search` | `z`, `zp` |
| `context7-library` | `c7`, `ctx7` |
| `context7-docs` | `c7d`, `c7docs`, `ctx7-docs` |
| `deep` | `dr` |
| `doctor` | `d` |
| `setup` | `init` |
| `config` | `cfg` |
| `model` | `mdl` |
| `smoke` | `sm` |
| `regression` | `reg` |

Nested aliases:

| Full command | Aliases |
| --- | --- |
| `config path` | `cfg p` |
| `config list` | `cfg ls`, `cfg l` |
| `config set` | `cfg s` |
| `config unset` | `cfg rm`, `cfg u` |
| `model current` | `mdl cur`, `mdl c` |
| `model set` | `mdl s` |

## JSON Expectations

Successful search output includes `ok`, `query`, `primary_api_mode`, `content`, `sources`, `sources_count`, `primary_sources`, `primary_sources_count`, `extra_sources`, `extra_sources_count`, `source_warning`, `routing_decision`, `providers_used`, `provider_attempts`, `fallback_used`, `validation_level`, and `elapsed_ms`. Each source should include at least `url` when available.

`--format content` prints only the `content` field when present. JSON output remains parseable and uses readable non-ASCII text when the terminal encoding supports it.

Source provenance fields:

- `primary_sources`: sources explicitly extracted from the primary model/provider answer.
- `extra_sources`: parallel Tavily / Firecrawl candidates from `--extra-sources`; these are not automatic evidence for the generated `content`.
- `sources`: backward-compatible merged list from `primary_sources + extra_sources`, deduped by URL.

Exa domain filters:

- `--include-domains` and `--exclude-domains` accept comma-separated or whitespace-separated domains.
- Both `--include-domains docs.python.org,developer.mozilla.org` and `--include-domains docs.python.org developer.mozilla.org` normalize to the same Exa domain list.
- This normalization is intentional for Windows PowerShell, where an unquoted comma expression can be forwarded through `.ps1` wrappers as a space-separated value.
- `source_warning`: non-empty when extra source candidates were appended.

Fetch output includes `ok`, `url`, `provider`, `content`, and `elapsed_ms`.

Zhipu Web Search API setup:

- `ZHIPU_API_URL` defaults to `https://open.bigmodel.cn/api`.
- `ZHIPU_SEARCH_ENGINE` defaults to `search_std`.
- Official Web Search API service values include `search_std`, `search_pro`, `search_pro_sogou`, and `search_pro_quark`.
- `smart-search setup --zhipu-api-url URL --zhipu-search-engine ENGINE` saves these values in non-interactive mode.
- Interactive setup asks for Zhipu API key, API URL, and search service when optional `web_search` reinforcement selects Zhipu.
- `config set ZHIPU_SEARCH_ENGINE VALUE` must remain free-form so newly added official services do not require a CLI release.
- `zhipu-search` corresponds to Zhipu Web Search API, not Zhipu Chat Completions `tools=[web_search]`, not Search Agent, and not the MCP Server.
- `TAVILY_API_URL` only affects Tavily and does not proxy Zhipu.

Exa search output includes `ok`, `query`, `search_type`, `results`, `total`, and `elapsed_ms` when successful.

Exa HTTP `400` or `422` failures are returned as `ok=false` with `error_type=parameter_error`; use this to distinguish bad CLI/domain/date/category arguments from upstream network failures.

Exa similar output includes `ok`, `url`, `results`, `total`, and `elapsed_ms` when successful.

Zhipu search output includes `ok`, `query`, `provider`, `search_engine`, `results`, `total`, and `elapsed_ms` when successful.

Context7 library output includes `ok`, `query`, `provider`, `results`, `total`, and `elapsed_ms` when successful. Context7 docs output includes `ok`, `library_id`, `query`, `provider`, `results`, `total`, `content`, and `elapsed_ms` when successful.

Map output includes `ok`, `base_url`, `results`, `response_time`, `url`, and `elapsed_ms` when successful.

Deep planner output includes `ok`, `mode`, `query_mode`, `question`, `trigger_source`, `difficulty`, `intent_signals`, `decomposition`, `capability_plan`, `evidence_policy`, `preflight`, `steps`, `gap_check`, `final_answer_policy`, `usage_boundary`, `allowed_tools`, `evidence_dir`, and `elapsed_ms`. `smart-search deep` is offline by default: `preflight.executed_by_deep_command=false`, no provider calls are made, and live research only happens when an AI agent or user executes `steps[].command`.

Diagnostic output masks keys, reports `config_file` / `config_sources` / `primary_api_mode` / `primary_api_mode_source` / `capability_status` / `minimum_profile_ok`, and includes `main_search_connection_tests` plus connection test objects for Exa, Tavily, Zhipu, Context7, and Firecrawl. `primary_connection_test` remains as a backward-compatible alias for the first configured main-search provider check. OpenAI-compatible provider health must be validated through `/chat/completions`; `/models` is supplementary metadata and must not be the health gate. Firecrawl currently reports whether `FIRECRAWL_API_KEY` is configured; it is not a live Firecrawl request.

Smoke output includes `ok`, `mode`, `failed_cases`, `cases`, `provider_attempts`, and `elapsed_ms`. Live smoke may include `degraded_cases` when a provider fails but a same-capability fallback remains available.

## Deep Research Skill Contract

Deep Research is an optional capability orchestration workflow for prompts such as `深度搜索`, `深度调研`, `深入搜索`, `deep search`, `deep research`, multi-source verification, cross-checking, serious review, and selection/comparison research. `smart-search deep` is the public offline planner command for this workflow. It must not change default `smart-search search` behavior and must not execute live providers by default. The AI agent reads the generated plan, composes existing CLI commands, and lets the CLI perform execution and write JSON/Markdown evidence.

Deep Research must not require fixed topic recipe ids such as `current_market_research`, `product_comparison_research`, `technical_docs_research`, `news_or_policy_research`, `claim_verification_research`, or `url_first_research`. Those phrases may appear as prompt examples, but they are not schema modes or routing enums.

Before execution, the skill should call `smart-search deep "question" --format json` to create a `research_plan` JSON artifact. Required fields are:

- `mode`: always `deep_research`.
- `query_mode`: always `deep`.
- `question`: the user's research question.
- `trigger_source`: usually `explicit_cli`.
- `difficulty`: `standard` or `high`.
- `intent_signals`: dimensional signals such as `recency_requirement`, `docs_api_intent`, `locale_domain_scope`, `known_url`, `source_authority_need`, `claim_risk`, `cross_validation_need`, and `breadth_depth_budget`.
- `decomposition`: subquestions for complex research, each with `id`, `question`, `reason`, and `required_capabilities`.
- `capability_plan`: the selected capability needs and the CLI tools chosen for each need.
- `evidence_policy`: default `fetch_before_claim`.
- `preflight`: `doctor` guidance. `deep` does not execute this by default.
- `steps`: ordered CLI command steps.
- `gap_check`: how the agent verifies that key claims have fetched evidence or downgrades unsupported claims to unverified candidates.
- `final_answer_policy`: how to cite fetched evidence and list unverified candidates.
- `usage_boundary`: user-facing distinction between fast live `search`, offline `deep` planning, and later step execution.

Each `steps[]` item must include `id`, `subquestion_id`, `tool`, `purpose`, `command`, and `output_path`. Allowed `tool` values are `search`, `exa-search`, `exa-similar`, `zhipu-search`, `context7-library`, `context7-docs`, `fetch`, and `map`; these map to existing CLI commands only. `doctor` is a `preflight` action, not a `steps[]` item. Use `C:\tmp\smart-search-evidence\<timestamp>-<slug>\` or an equivalent absolute evidence directory for `output_path` values.

Capability boundaries:

- `search`: broad discovery and synthesis through `main_search`; use returned `routing_decision`, `provider_attempts`, `fallback_used`, and `source_warning` as orchestration signals, not as claim proof.
- `exa-search`: low-noise source discovery for official docs, APIs, papers, product pages, known domains, trusted pages, and recency-filtered source search.
- `exa-similar`: adjacent-source discovery when a known reliable URL is available.
- `zhipu-search`: Chinese, domestic, current, or domain-filtered source discovery.
- `context7-library` and `context7-docs`: library, SDK, API, framework, and documentation intent only.
- `fetch`: page-content evidence. Key claims require fetched page text under `fetch_before_claim`.
- `map`: site structure exploration before many fetches from one site; not claim evidence by itself.

Default Deep Research orchestration:

1. Run `smart-search doctor --format json` as preflight when configuration is uncertain.
2. Call `smart-search deep "question" --format json` to generate `intent_signals`, `decomposition`, and `capability_plan` instead of selecting a fixed topic recipe.
3. Use planned `smart-search search ... --validation balanced --extra-sources 1..3` steps for broad discovery.
4. Add planned `exa-search`, `exa-similar`, `zhipu-search`, `context7-library`, `context7-docs`, or `map` only when the capability boundary matches the intent.
5. Use `fetch` for key URLs before making claim-level statements.
6. Run `gap_check`: fetch missing evidence for key claims or downgrade them to unverified candidates.

`fetch_before_claim` means key claims must be backed by fetched page content. `primary_sources` and `extra_sources` are discovery candidates until fetched. Final answers should include fetched evidence, unverified candidate sources, and key commands used.

Planner closeout lessons:

- Budget limits must not break evidence policy. Even `--budget quick` plans must retain at least one `fetch` step when claim-level conclusions are expected, and retained steps must keep valid `subquestion_id` links.
- `steps[].command` and `steps[].output_path` are one contract. The `--output` path embedded in the executable command must match `output_path`; otherwise the AI agent cannot reliably find saved evidence.
- Prefer PowerShell-safe quoted commands in generated plans because Windows users often copy planned steps directly from Markdown or JSON output.

Deep Research smoke coverage is mock-full plus live-limited. Mock-full coverage should cover trigger phrases, normal search requests that should not trigger Deep Research, required `research_plan` fields, allowed tool whitelist, `fetch_before_claim`, evidence paths, capability boundaries, `intent_signals`, `capability_plan`, `gap_check`, simple current prompts such as `深度搜索一下最近的比特币行情`, docs/API prompts, claim-verification prompts, user-provided URL fetch-first flows, missing-provider failure guidance, and the rule that fixed topic recipe ids are not required schema. Live-limited coverage should run `doctor`, one broad `search`, one `exa-search`, and one `fetch` when real keys are available and live checks are expected. If a smoke issue is found, fix the affected docs/code/tests and rerun the affected smoke until it passes or is proven to be an external provider blocker.

Setup and config output should include `ok` and `config_file`. Saved API keys must be masked in command output.

Interactive setup behavior:

- Default `smart-search setup` shows a Smart Search ASCII banner, asks for `zh`
  or `en`, offers project-local `smart-search-cli` skill installation, then
  shows a grouped provider wizard.
- The grouped wizard should use an arrow-key / Space / Enter selector when the
  packaged TUI dependencies are available, with a text fallback for non-TTY
  and tests.
- Skill installation installs the bundled `smart-search-cli` skill into
  selected AI-tool skill directories and must not run `trellis init`, create
  hooks, create agents, create commands, or modify other skills. Most targets
  are project-local; Hermes Agent installs to the current user's
  `~/.hermes/skills/` by convention.
- Skill targets are `codex`, `claude`, `cursor`, `opencode`, `copilot`,
  `gemini`, `kiro`, `qoder`, `codebuddy`, `droid`, `pi`, `kilo`,
  `antigravity`, `windsurf`, and `hermes`. `--skip-skills` disables skill
  installation. `--install-skills codex,claude,cursor,hermes` selects targets
  explicitly, and `--skills-root PATH` overrides the project root used for
  project-local targets.
- Required groups are `main_search`, `docs_search`, and `web_fetch`; `web_search` is optional reinforcement.
- `--lang zh|en` skips the language question.
- `--advanced` shows low-level config keys one by one for compatibility with older setup behavior and does not show the skill prompt unless `--install-skills` is explicit.
- `--non-interactive` keeps script behavior and only saves values passed as flags.
- Unchecking a configured provider must not delete existing config values; use
  `smart-search config unset KEY` for deletion.
- Interactive output should summarize `minimum_profile_ok`, missing required capabilities, and next-step commands.
- Beginner filling examples for official-service and relay/pooled-endpoint
  minimum profiles must appear in the grouped wizard on stderr, not stdout.
  They must cover `main_search`, `docs_search`, and `web_fetch` so a first-time
  user can satisfy the minimum profile without understanding provider internals.

Provider endpoint setup:

- `TAVILY_API_URL` defaults to `https://api.tavily.com`.
- Tavily Hikari / pooled endpoints must use the REST facade base
  `https://<host>/api/tavily`; `/mcp` is not a REST provider base.
- Setup normalizes a Hikari root host or `/mcp` URL to
  `https://<host>/api/tavily`; an existing `/api/tavily` base and official
  `https://api.tavily.com` remain unchanged.
- `FIRECRAWL_API_URL` defaults to `https://api.firecrawl.dev/v2`; custom REST
  bases are saved with scheme normalization and no trailing slash.

Search timeout output uses `ok=false`, `error_type=network_error`, includes the timeout seconds in `error`, keeps `query`, `content`, `sources`, `sources_count`, `primary_sources`, `primary_sources_count`, `extra_sources`, and `extra_sources_count`, and exits with code `4`.

## Provider Routing

- `search` builds `main_search` from peer providers only: `XAI_API_KEY` registers official xAI Responses, while `OPENAI_COMPATIBLE_API_URL` + `OPENAI_COMPATIBLE_API_KEY` registers OpenAI-compatible Chat Completions.
- Official xAI calls use the Responses API `/responses` route through `XAI_*`. Compatible relays/gateways use Chat Completions `/chat/completions` through `OPENAI_COMPATIBLE_*`.
- Legacy `SMART_SEARCH_API_URL`, `SMART_SEARCH_API_KEY`, `SMART_SEARCH_API_MODE`, `SMART_SEARCH_MODEL`, and `SMART_SEARCH_XAI_TOOLS` are unsupported config keys. `config set` / `config unset` must return a parameter error for them.
- `XAI_TOOLS` applies only to xAI Responses mode and supports only `web_search` and `x_search`.
- Chat Completions mode must not send xAI `web_search` / `x_search` tools or legacy `search_parameters`; xAI Chat Completions Live Search is deprecated.
- Standard minimum profile requires `main_search`, `docs_search`, and fetch capability. Missing required capabilities produce a configuration error.
- Same-capability fallback is allowed; cross-capability fallback is not. Context7 is not used for unrelated broad web queries, and page extraction providers are not used as docs search providers.
- `main_search`: xAI Responses first for Grok/xAI, then OpenAI-compatible answer fallback when that peer provider is separately configured and `--fallback auto` is active.
- `web_search`: Zhipu first when routed in, then Tavily / Firecrawl source search when configured.
- `docs_search`: Exa first, then Context7.
- Fetch capability: Tavily first, then Firecrawl.
- `search` calls Tavily and/or Firecrawl only when `--extra-sources` is greater than 0.
- If both Tavily and Firecrawl are configured, `search --extra-sources N` gives about 60% of extra source slots to Tavily and the remainder to Firecrawl.
- `extra_sources` are retrieved in parallel and are not automatically used by the primary model to verify its answer.
- `fetch` tries Tavily first, then Firecrawl as fallback when Tavily returns no content.
- `map` uses Tavily only.
- `exa-search` and `exa-similar` use Exa only.
- `zhipu-search` uses Zhipu only.
- `context7-library` and `context7-docs` use Context7 only.
- Runtime config priority is environment variables first, then local config file, then defaults.
- `setup` and `config` read/write the local Smart Search config file and do not call providers.
- `model current` reports explicit provider model settings. `model set` is retained only as a parameter-error migration guard; use `config set XAI_MODEL ...` or `config set OPENAI_COMPATIBLE_MODEL ...` to change models.

## Routing Heuristics

- Use `exa-search --include-domains` when official documentation domains are known.
- Use `context7-library` / `context7-docs` for docs/API/SDK/library/framework intent when Context7 is configured.
- Use `zhipu-search` for Chinese, domestic, current, or domain-filtered source discovery when Zhipu is configured.
- Use `exa-search --start-published-date` for recency-constrained source discovery.
- Use `exa-similar` when a known good page is available and adjacent sources are needed.
- Use `search --format content` when a human wants only the generated answer body.
- Use `fetch --format markdown` or `fetch --format content` for user-supplied URLs or when exact page text matters.
- Use `map` before fetching many pages from a documentation site.
- Keep `search --extra-sources` small (`1` to `3`) unless broad coverage is requested.
- For current news or high-risk claims, prefer source discovery plus `fetch`; do not treat broad `search.content` plus `extra_sources` as claim-level verification.

## Maintenance Guardrails

- Provider architecture changes must be verified as distributable CLI behavior, not as behavior that only works because one developer machine has a specific wrapper, shell profile, or local config file.
- Register providers by capability first, then route by intent. Fallback is allowed only within the same capability.
- Keep xAI Responses and OpenAI-compatible as peer `main_search` providers. A failed xAI Responses request may fall back to OpenAI-compatible only when `OPENAI_COMPATIBLE_API_URL` and `OPENAI_COMPATIBLE_API_KEY` are separately configured.
- Do not use Context7 for broad news or generic web facts; do not use Tavily or Firecrawl as documentation semantic-search replacements.
- Standard installs must fail closed unless `main_search`, `docs_search`, and fetch capability each have at least one configured provider.
- After provider-routing changes, run source-checkout regression plus `smart-search smoke --mock --format json`. If live keys were used, run a targeted secret scan for exact key substrings before committing.

## Exit Codes

- `0`: success
- `2`: parameter error
- `3`: configuration error
- `4`: network or upstream error
- `4`: also used for strict insufficient-evidence search failures
- `5`: runtime or parse error

## Regression

Run `smart-search regression` before considering CLI or skill changes complete.

- In a source checkout, it runs offline pytest coverage for CLI, service, smoke, provider, and skill contract behavior.
- In npm / mise packaged installs, repository test files are not bundled; since v0.1.8 it falls back to built-in mock smoke regression so users can still verify installed CLI health.
- For release validation, use a source checkout for full pytest-backed regression and use packaged-install regression only as an install-health check.

## Release Lanes

- Stable releases are pushed as `vX.Y.Z` Git tags and publish npm `X.Y.Z` with dist-tag `latest`.
- Test releases are pushed from `main` and publish `<package.json version>-beta.N` with dist-tag `next`. The beta counter resets per base version, so `0.1.9-beta.1` and `0.1.10-beta.1` are separate sequences.
- Stable bump commits must use `chore(release): bump version to X.Y.Z`; the branch push is skipped by the npm workflow so the matching `vX.Y.Z` tag is the only publisher for npm `latest`.
- Historical test builds can be backfilled through GitHub Actions `workflow_dispatch` by supplying an explicit `target_ref`, exact `version`, and a non-`latest` npm tag such as `backfill`.
- npm versions are immutable. Old `*-dev.*` packages cannot be renamed in place; publish replacement `*-beta.N` packages and optionally deprecate the old names when npm owner credentials are available.

### Release Closeout Lessons

- Always read back npm before and after publishing with `npm view @konbakuyomu/smart-search versions --json` and `npm view @konbakuyomu/smart-search dist-tags --json`. A test release must leave `latest` on the stable version and move only `next` or the explicitly supplied non-`latest` tag.
- Backfill jobs can publish npm successfully even if GitHub release creation fails because the workflow token cannot access the release API. In that case, leave npm intact and create the missing GitHub prerelease with authenticated local `gh release create ... --prerelease --latest=false`.
- If concurrent backfill jobs hit npm `E409`, re-dispatch only the affected versions serially after checking whether the version already appeared in the registry.
- Finish with a diff-style gap check: expected beta version list minus npm versions equals empty, and expected `vX.Y.Z-beta.N` list minus GitHub prereleases equals empty.
- Local verification after a test release must use an exact install target, such as `mise use -g "npm:@konbakuyomu/smart-search@0.1.10-beta.3" -y --pin`, followed by `mise reshim`, `where.exe smart-search`, `smart-search --version`, packaged `smart-search regression`, and `smart-search smoke --mock --format json`. Also pipe a non-ASCII JSON command such as `smart-search deep "深度搜索一下最近的比特币行情" --format json | ConvertFrom-Json` to verify the Windows npm/mise wrapper is emitting UTF-8 JSON, not locale-encoded bytes.

## Tool Policy

Web research through this skill should use `smart-search` CLI. If the CLI is unavailable, report the blocker and recovery steps instead of silently falling back to another web-search route.
