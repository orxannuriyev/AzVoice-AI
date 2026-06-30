# AzVoice AI
# ASTANA

> **An end-to-end Azerbaijani voice assistant pipeline powered by Speech-to-Text, Large Language Models, and Text-to-Speech technologies for natural spoken conversations.** 

## 🚀 Developed by Team **ASTANA**

### Team Members

- **Orkhan Nuriyev** → Database Design & Pipeline Development, Web Development
- **Ibrahim Suleymanov** → Machine Learning Modelling, Statistical Analysis
- **Esli Ehmedova** → Demo & Web Development
- **Ulviyye Eliyeva** → Exploratory Data Analysis (EDA)

---

## 🌐 Live Website 

Experience our Azerbaijani AI Voice Assistant in action!  
👉 **[Try the Demo]()**

The system features:
- **Speech-to-Text (STT):** Converts Azerbaijani speech into text.
- **AI-Powered Responses:** Generates context-aware responses using an LLM.
- **Text-to-Speech (TTS):** Produces natural-sounding Azerbaijani speech.
- **Real-Time Conversations:** Low-latency end-to-end voice interaction. 

---

## 📌 Problem Statement
How can we build a fast and accurate Azerbaijani voice assistant capable of understanding spoken language, generating intelligent responses, and delivering natural speech in real time? This project integrates Speech-to-Text (STT), Large Language Models (LLMs), and Text-to-Speech (TTS) into a unified end-to-end conversational AI pipeline.

## 💡 Why It Matters
High-quality voice assistants for the Azerbaijani language are still limited. This project aims to improve accessibility and human-computer interaction by enabling natural, low-latency voice conversations in Azerbaijani, providing a foundation for applications such as customer support, virtual assistants, and other voice-enabled services. 

## 🏗️ Pipeline Architecture



---

## 🎯 Target Definition
* **Objective:** Build an end-to-end Azerbaijani voice assistant capable of understanding speech, generating intelligent responses, and synthesizing natural speech.
* **Metric of Success:** Achieve high transcription accuracy, low response latency, and natural conversation quality.
* **Scope:** Real-time voice interaction in the Azerbaijani language.

## 📊 Project Scope
* **Language:** Azerbaijani
* **Input:** Live microphone audio.
* **Pipeline:** Voice Activity Detection (VAD) → Speech-to-Text (STT) → Large Language Model (LLM) → Text-to-Speech (TTS).
* **Core Features:**
  * Real-time speech recognition
  * Context-aware AI responses
  * Natural Azerbaijani speech synthesis
  * Modular architecture for easy model replacement and future improvements 

## 📋 Core Components

| # | Component | Purpose |
| :---: | :--- | :--- |
| 1 | **Voice Activity Detection (VAD)** | Detects when the user starts and stops speaking. |
| 2 | **Speech-to-Text (STT)** | Transcribes Azerbaijani speech into text. |
| 3 | **Large Language Model (LLM)** | Understands user queries and generates intelligent responses. |
| 4 | **Text-to-Speech (TTS)** | Converts generated text into natural Azerbaijani speech. |
| 5 | **Conversation Manager** | Maintains dialogue context and manages conversation flow. |
| 6 | **Prompt & System Instructions** | Defines the assistant's behavior and response style. |
| 7 | **Model Inference Engine** | Executes AI models efficiently for low-latency responses. |
| 8 | **Audio Input Pipeline** | Captures and preprocesses microphone audio. |
| 9 | **Audio Output Pipeline** | Plays synthesized speech to the user. |
| 10 | **Logging & Monitoring** | Records interactions, errors, and performance metrics. | 


## 📖 Key Definitions
* **DuckDB:** An embedded, high-performance analytical database used locally to rapidly query and transform our large weather datasets.
* **Medallion Architecture:** Our DuckDB schema is designed with structured layers—**Raw** (direct ingest), **Staging** (cleaned and validated), and **Analytics** (feature-engineered) to ensure strict data quality.
* **Open-Meteo API:** A free, open-source weather API providing access to both our historical archive endpoint and the forecasting endpoint without requiring API keys.


## 📅 Project Roadmap & Daily Activities 

Below is the execution timeline of our two-week sprint, detailing completed and planned milestones. 

| Day | Team Member | Tasks |
| :---: | :---: | :--- |
| **Day 1** | **Person 1** | Create GitHub repository, initialize project structure, create README, invite team members. |
|  | **Person 2** | Create To-Do list, create GitHub Project Board, define milestones, create GitHub Issues. |
|  | **Person 3** | Brainstorm project ideas, research idea feasibility, collect reference resources. |
|  | **Person 4** | Research VAD, STT, LLM, TTS pipeline, begin model comparison. |
| **Day 2** | **Person 1** | ... |
|  | **Person 2** | ... |
|  | **Person 3** | ... |
|  | **Person 4** | ... | 

## Models Table

| Stage                              | Tested Models                                  | Not Yet Tested Models                                                                                     | Current Recommendation           | Notes                                                          |
| :--------------------------------- | :--------------------------------------------- | :-------------------------------------------------------------------------------------------------------- | :------------------------------- | :------------------------------------------------------------- |
| **Voice Activity Detection (VAD)** | Silero VAD ✅                                   | NVIDIA NeMo VAD, WebRTC VAD, MarbleNet VAD                                                                | Silero VAD                       | Fast, lightweight, and reliable for real-time voice detection. |
| **Speech-to-Text (STT)**           | Whisper Large-v3 ✅<br>Whisper Large-v3 Turbo ✅ | Faster-Whisper (distil-large-v3), NVIDIA Parakeet 1.1, NVIDIA Canary 1B, SenseVoice-Small, Whisper Medium | Faster-Whisper (distil-large-v3) | Better latency and suitable for streaming applications.        |
| **Large Language Model (LLM)**     | Llama 3.2 3B ✅<br>Qwen 2.5 7B ✅                | Qwen3 8B, Qwen3 14B, Gemma 3 12B, Mistral Small 3.2, Llama 3.1 8B, Phi-4                                  | Qwen3 14B                        | Strong performance for real-time conversational agents.        |
| **LLM Inference Engine**           | Ollama ✅                                       | vLLM, SGLang, TensorRT-LLM, llama.cpp, LM Studio                                                          | vLLM                             | Higher throughput and lower first-token latency.               |
| **Text-to-Speech (TTS)**           | Az-AZ-BanuNeural (Edge TTS) ✅                  | XTTS v2, F5-TTS, Kokoro TTS, MeloTTS, Orpheus TTS                                                         | XTTS v2                          | One of the most mature open-source multilingual TTS solutions. |
| **Streaming TTS Framework**        | —                                              | XTTS Streaming, F5-TTS Streaming, Kokoro Streaming, MeloTTS Streaming                                     | XTTS Streaming                   | Designed for low-latency streaming speech synthesis.           |

