# AI Providers

Project Akiha uses one provider-neutral chat contract. Chat, memory extraction,
conversation summaries, and voice output do not depend directly on a vendor.
Changing providers in Settings applies immediately and does not require a
restart.

## Available Providers

| Setting | Connection | API key |
| --- | --- | --- |
| `mock` | Deterministic local development response | No |
| `ollama` | Native local Ollama chat API | No |
| `gemini` | Google Gemini OpenAI-compatible endpoint | Yes |
| `openai` | OpenAI Chat Completions endpoint | Yes |
| `openrouter` | OpenRouter Chat Completions endpoint | Yes |
| `kimi` | Moonshot/Kimi Chat Completions endpoint | Yes |
| `openai-compatible` | User-supplied compatible endpoint, including local servers | Optional |

The compatibility adapter intentionally covers the common text-chat and
streaming subset. Provider-specific tools, image input, web grounding, prompt
caching, and proprietary reasoning controls are not enabled by this adapter.
A direct Anthropic adapter is not implemented yet; Claude models can be reached
through a compatible gateway such as OpenRouter when the user has suitable API
access.

## Settings

Open `Settings -> AI`, select a provider, then configure the fields enabled for
that provider.

Ollama uses:

- `Ollama URL`
- `Ollama model`

Hosted and compatible providers use:

- `Hosted API URL`
- `Hosted model`
- `API key`

The API key field is write-only. Leave it blank to retain the saved key. Use
`Clear key` to delete the selected provider's saved key.

The preset URL and model are filled when a hosted provider is selected. Both
remain editable because provider model catalogs and compatible gateways change
over time.

## Credential Storage

API keys are never added to `user_config.toml`.

Keys entered in Settings are encrypted with Windows Data Protection API
(DPAPI), scoped to the current Windows account, and saved as ciphertext at:

```text
%LOCALAPPDATA%\Akiha\state\credentials.json
```

The encrypted file is not portable to another Windows account. Technical logs,
events, chat history, memory records, and transcript exports do not receive the
API key.

Environment variables can be used instead of the Settings field:

| Provider | Environment variable |
| --- | --- |
| Gemini | `GEMINI_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Kimi | `MOONSHOT_API_KEY` |
| Custom compatible | `AKIHA_AI_API_KEY` |

A securely saved Settings key takes precedence over an environment variable.

## Local Fallback

No cloud fallback happens automatically. This prevents a conversation from
being sent to a different provider without an explicit user choice.

To run without subscriptions or API credits:

1. Start Ollama.
2. Download or select a local chat model.
3. Choose `ollama` in `Settings -> AI`.
4. Enter the local URL and model, then save.

`mock` remains available when neither cloud access nor a local model is
available.

## Privacy Boundary

Selecting a hosted provider sends the assembled request to the configured
endpoint. Depending on the active feature, that request can contain:

- the companion system prompt;
- recent conversation messages;
- retrieved memory context;
- conversation-summary context;
- memory extraction or summarization instructions.

VOICEVOX audio and raw microphone recordings are not sent through the AI
provider. Recognized speech becomes ordinary chat text only after the user
submits it.
