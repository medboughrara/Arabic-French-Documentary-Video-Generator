# Roadmap: Building a Tunisian Derja (تونسي / `aeb`) Understanding & Speaking AI Model

A long-term R&D blueprint for building an AI system capable of **understanding spoken & written Tunisian Arabic (Derja)**—including French/English code-switching and Arabizi—and **speaking naturally with an authentic Tunisian accent**.

---

## 1. Core Linguistic Challenges

1. **Dual Scripts**: Everyday Tunisian is written in both **Arabic script** (using Maghrebi letters `ڨ` = `/g/`, `ڤ` = `/v/`, `پ` = `/p/`) and **Arabizi** (`3`, `7`, `9`, `5`, `2`, e.g., `3aslema chnowa a7welek`).
2. **Code-Switching**: Natural speech shifts mid-sentence between Derja, **French**, and **English**.
3. **Lack of Vowel Diacritics**: Standard TTS models struggle with unvoweled Derja and Maghrebi short-vowel reductions.
4. **Scarcity of Studio TTS Audio**: Spoken Tunisian corpora exist mostly for noisy ASR rather than clean mono-speaker speech synthesis.

---

## 2. Recommended Architecture: Cascaded First → Native Multimodal Later

Start with a modular 3-stage pipeline (**Ears → Brain → Voice**) before unifying into end-to-end speech models:

| Component | Recommended Initial Stack | Future Upgrade |
| :--- | :--- | :--- |
| **1. Ears (ASR)** | `openai/whisper-large-v3-turbo` fine-tuned with LoRA | Unified audio encoder |
| **2. Brain (LLM)** | `Qwen2.5-7B/14B` or `Llama-3.1-8B` / `Jais` fine-tuned via `Unsloth` QLoRA | Tool calling + domain RAG |
| **3. Voice (TTS)** | `F5-TTS` (e.g., adapting `Arabic-F5-TTS-v2`), `Fish Speech`, or `CosyVoice 2` | Expressive streaming voice |
| **4. Real-Time Loop** | `LiveKit` (WebRTC) + `Pipecat` + `Silero VAD` | **Qwen2.5-Omni** Speech-to-Speech |

---

## 3. Existing Open-Source Tunisian Datasets & Checkpoints

- **Speech Recognition (ASR / SLU)**:
  - [`tunis-ai/TunSwitch`](https://huggingface.co/datasets/tunis-ai/TunSwitch) (`TunSwitch-TO` read speech + `TunSwitch-CS` French/English code-switched podcasts/radio)
  - [`TuniSpeech-AI/TuniSpeech-21h`](https://huggingface.co/datasets/TuniSpeech-AI/TuniSpeech-21h) (~21h spontaneous broadcast/social-media audio)
  - `TARIC` / `TARIC-SLU` (Tunisian Railway conversational dialogue corpus)
- **NLP, Text & Arabizi**:
  - [`linagora/Tunisian_Derja_Dataset`](https://huggingface.co/datasets/linagora/Tunisian_Derja_Dataset) (1.2M+ lines for continual pre-training)
  - [`hamzabouajila/tunisian-derja-unified-raw-corpus`](https://huggingface.co/datasets/hamzabouajila/tunisian-derja-unified-raw-corpus) (~802k deduplicated lines)
  - [`arbml/TUNIZI`](https://huggingface.co/datasets/arbml/TUNIZI) (Tunisian Arabizi benchmark) & `TounsiBench` (instruction benchmark)
- **Text-to-Speech (TTS)**:
  - [`elyadata/TunArTTS`](https://github.com/elyadata/TunArTTS) (~3+ hours mono-speaker Tunisian male voice + preprocessing pipeline)

---

## 4. Phased Implementation Plan

1. **Phase 1 — Script Normalization**: Standardize `ڨ / ڤ / پ`, keep French/English words in Latin script, and optionally train a lightweight Arabizi → Derja normalizer (`ByT5`/`mT5`).
2. **Phase 2 — Tunisian Code-Switched ASR**: Fine-tune `whisper-large-v3-turbo` with PEFT/LoRA on `TunSwitch`, `TuniSpeech-21h`, and `TARIC`; measure WER/CER separately on Derja-only vs. code-switched utterances.
3. **Phase 3 — Derja LLM**: Run continual pre-training + supervised conversational SFT using `Unsloth` + `TRL` (`SFTTrainer`), then evaluate on `TounsiBench`.
4. **Phase 4 — Studio-Grade Tunisian TTS**: Curate 3–15h of clean single-speaker Derja + French audio (`Demucs` + `Silero VAD`), fine-tune `F5-TTS`, `Fish Speech`, or `CosyVoice 2`, and run MOS listening evaluations.
5. **Phase 5 — Real-Time Voice Agent**: Connect streaming `faster-whisper` → `vLLM` → streaming TTS inside `Pipecat` + `LiveKit`, and eventually migrate to end-to-end speech models like `Qwen2.5-Omni`.
