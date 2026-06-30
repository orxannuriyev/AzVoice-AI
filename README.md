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

|    Day    | Team Member | Tasks                                                                                                                                     |
| :-------: | :---------: | :---------------------------------------------------------------------------------------------------------------------------------------- |
| **Day 1** | **Ulviyye** | Research VAD, STT, LLM, TTS pipeline.                                                                                                     |
|           |   **Esli**  | Create README, create To-Do list, research VAD, STT, LLM, TTS pipeline.                                                                   |
|           |  **Orxan**  | Create GitHub repository, invite team members, brainstorm project ideas, research VAD, STT, LLM, TTS pipeline.                            |
|           | **Ibrahim** | Brainstorm project ideas, research VAD, STT, LLM, TTS pipeline.                                                                           |
| **Day 2** | **Ulviyye** | Test Silero VAD, Whisper Large-v3, Faster-Whisper, Qwen 2.5 7B, llama.cpp, Edge TTS (az-AZ-BanuNeural), Custom Keyword-Overlap Retriever. |
|           |   **Esli**  | Test Silero VAD, Whisper Large-v3, Faster-Whisper, Llama 3.2 3B, llama.cpp, Edge TTS (az-AZ-BabekNeural), Knowledge Base Retrieval.       |
|           |  **Orxan**  | Test Silero VAD, Whisper Medium, Faster-Whisper, Aya 8B, Ollama, Edge TTS (az-AZ-BabekNeural), ChromaDB + Knowledge Base.                 |
|           | **Ibrahim** | Test Silero VAD, Whisper Distil-Large-v3, Faster-Whisper, Ollama, gTTS (fallback), ChromaDB + Knowledge Base.                             |


## Models Table

| Stage                              | Tested Models                                                                                   | Not Yet Tested Models                                                           |
| :--------------------------------- | :---------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------ |
| **Voice Activity Detection (VAD)** | Silero VAD ✅                                                                                    | NVIDIA NeMo VAD, WebRTC VAD, MarbleNet VAD                                      |
| **Speech-to-Text (STT)**           | Whisper Medium ✅<br>Whisper Large-v3 ✅<br>Whisper Distil-Large-v3 ✅                             | NVIDIA Parakeet 1.1, NVIDIA Canary 1B, SenseVoice-Small, Whisper Large-v3 Turbo |
| **STT Backend**                    | Faster-Whisper ✅                                                                                | Whisper.cpp, NVIDIA Riva ASR                                                    |
| **Large Language Model (LLM)**     | Qwen 2.5 7B ✅<br>Llama 3.2 3B ✅<br>Aya 8B ✅                                                     | Qwen3 8B, Qwen3 14B, Gemma 3 12B, Llama 3.1 8B, Mistral Small 3.2, Phi-4        |
| **LLM Inference Engine**           | Ollama ✅<br>llama.cpp ✅                                                                         | vLLM, SGLang, TensorRT-LLM, LM Studio                                           |
| **Text-to-Speech (TTS)**           | Edge TTS – az-AZ-BanuNeural ✅<br>Edge TTS – az-AZ-BabekNeural ✅<br>gTTS (fallback) ✅            | XTTS v2, F5-TTS, Kokoro TTS, MeloTTS, Orpheus TTS                               |
| **Knowledge Retrieval (RAG)**      | Custom Keyword-Overlap Retriever ✅<br>Knowledge Base Retrieval ✅<br>ChromaDB + Knowledge Base ✅ | FAISS + Embeddings, Milvus, Qdrant, pgvector                                    |

