# AzVoice AI
# ASTANA

> **An end-to-end Azerbaijani voice assistant pipeline powered by Speech-to-Text, Large Language Models, and Text-to-Speech technologies for natural spoken conversations.** 

## 🚀 Developed by Team **ASTANA**

### Team Members

- **Orkhan Nuriyev → System Architecture, Voice Assistant Pipeline Development, Backend Integration
- **Ibrahim Suleymanov → LLM Integration, Prompt Engineering, Speech Processing
- **Esli Ehmedova → Demo Development, Web Interface, Frontend Integration
- **Ulviyye Eliyeva → Data Collection & Preprocessing, Pipeline Testing & Evaluation, Documentation

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
| **Day 1** | **Ulviyye** | Research VAD, STT, LLM, and TTS pipeline. |
|  | **Esli** | Create README, create To-Do list, and research VAD, STT, LLM, and TTS pipeline. |
|  | **Orxan** | Create GitHub repository, invite team members, brainstorm project ideas, and research VAD, STT, LLM, and TTS pipeline. |
|  | **Ibrahim** | Brainstorm project ideas and research VAD, STT, LLM, and TTS pipeline. |
| **Day 2** | **Ulviyye** | Test Silero VAD, Whisper Large-v3, Faster-Whisper, Qwen 2.5 7B, llama.cpp, Edge TTS (az-AZ-BanuNeural), and Custom Keyword-Overlap Retriever. |
|  | **Esli** | Test Silero VAD, Whisper Large-v3, Faster-Whisper, Llama 3.2 3B, llama.cpp, Edge TTS (az-AZ-BabekNeural), and Knowledge Base Retrieval. |
|  | **Orxan** | Test Silero VAD, Whisper Medium, Faster-Whisper, Aya 8B, Ollama, Edge TTS (az-AZ-BabekNeural), and ChromaDB + Knowledge Base. |
|  | **Ibrahim** | Test Silero VAD, Whisper Distil-Large-v3, Faster-Whisper, Ollama, gTTS (fallback), and ChromaDB + Knowledge Base. |
| **Day 3** | **Ulviyye** | Updated the README; searched for and evaluated four different local STT models. |
|  | **Esli** | Updated the README; searched for and evaluated four different local STT models; compared three RAG embedding models (Qwen3-Embedding-0.6B, BGE-M3, and intfloat/multilingual-e5-large-instruct); and compared four LLMs (Qwen2.5:14B, Qwen2.5:7B, Gemma2:9B, and Aya:8B). |
|  | **Orxan** | Researched LLM improvements, evaluated Gemma 4-E 4B, and worked on RAG optimization. |
|  | **Ibrahim** | Researched the entire pipeline, evaluated Gemma 4B and E2B, and worked on RAG optimization. |
| **Day 4** | **Ulviyye** | Searched for and evaluated four different local STT models.<br>Created scripts for evaluating the models. |
|  | **Esli** | Updated the README and took notes.<br>Compared Gemma 4:e4b and Qwen 7B models, evaluating response quality, performance, and inference speed.<br>Compared Ollama and llama.cpp runtimes, analyzing performance, response quality, and latency. |
|  | **Orxan** | Implemented significant improvements to LLM performance and optimized the overall inference pipeline.<br>Evaluated the Gemma model using a diverse set of prompts to assess response quality and consistency.<br>Measured the voice assistant's average latency and standard deviation (STD) across multiple test cases.<br>Optimized the end-to-end pipeline to improve responsiveness, efficiency, and overall performance. |
|  | **Ibrahim** | Conducted in-depth research on Speech-to-Text (STT) technologies, architectures, and optimization techniques.<br>Researched LLM fine-tuning methods, including parameter-efficient approaches and best practices.<br>Conducted in-depth research on Text-to-Speech (TTS) technologies, models, and performance optimization.<br>Optimized the end-to-end voice assistant pipeline.<br>Evaluated the complete pipeline using diverse user queries, analyzing response quality, latency, and overall performance. |
| Day 5 | Ulviyye | Researched Text-to-Speech (TTS) fine-tuning techniques and evaluated multiple open-source TTS models for the hotel voice assistant.<br>Reviewed the generated hotel dataset to identify and correct inappropriate or incorrectly translated words, improving dataset quality. |
| | Esli | Updated the README with project progress and documentation.<br>Created and maintained the project To-Do list, documenting completed tasks for each team member.<br>Generated a synthetic hotel dataset for training and evaluation.<br>Researched TTS fine-tuning techniques and prepared a technical document summarizing suitable approaches and models. |
| | Orxan | Set up and configured the project database.<br>Set up the Docker environment for the project.<br>Integrated tool calling functionality into the LLM, enabling the model to interact with external tools and services. |
| | Ibrahim | Created a comprehensive OVERVIEW.md documenting the hotel voice assistant, including the project architecture, folder structure, and detailed explanations of each component.<br>Prepared a project Q&A knowledge base by converting the documentation into JSON format for use by the demo chatbot during judging.<br>Created the hotel knowledge JSON dataset and researched document chunking strategies for RAG.<br>Researched ChromaDB and FAISS to determine the most suitable vector database based on project requirements and available hardware. |



## Models Table

| Stage                              | Tested Models                                                                                   | Not Yet Tested Models                                                           |
| :--------------------------------- | :---------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------ |
| **Voice Activity Detection (VAD)** | Silero VAD ✅                                                                                    | NVIDIA NeMo VAD, WebRTC VAD, MarbleNet VAD                                      |
| **Speech-to-Text (STT)**           | Whisper Medium ✅<br>Whisper Large-v3 ✅<br>Whisper Distil-Large-v3 ✅                             | NVIDIA Parakeet 1.1, NVIDIA Canary 1B, SenseVoice-Small, Whisper Large-v3 Turbo |
| **STT Backend**                    | Faster-Whisper ✅                                                                                | Whisper.cpp, NVIDIA Riva ASR                                                    |
| **Large Language Model (LLM)**     | Qwen 2.5 7B ✅<br>Llama 3.2 3B ✅<br>Aya 8B ✅                                                     | Qwen3 8B, Gemma 3 12B, Llama 3.1 8B, Mistral Small 3.2, Phi-4        |
| **LLM Inference Engine**           | Ollama ✅<br>llama.cpp ✅ <br>Qwen3 14B ✅                                                                        | vLLM, SGLang, TensorRT-LLM, LM Studio                                           |
| **Text-to-Speech (TTS)**           | Edge TTS – az-AZ-BanuNeural ✅<br>Edge TTS – az-AZ-BabekNeural ✅<br>gTTS (fallback) ✅            | XTTS v2, F5-TTS, Kokoro TTS, MeloTTS, Orpheus TTS                               |
| **Knowledge Retrieval (RAG)**      | Custom Keyword-Overlap Retriever ✅<br>Knowledge Base Retrieval ✅<br>ChromaDB + Knowledge Base ✅ | FAISS + Embeddings, Milvus, Qdrant, pgvector                                    |

| **Pipeline Stage** | **Model / Technology** | **Reason (Why it was not selected / Why another model was preferred)** |
|--------------------|------------------------|-------------------------------------------------------------------------|
| Voice Activity Detection (VAD) | Silero VAD | + |
| Speech-to-Text (STT) | Whisper Medium | Insufficient Azerbaijani speech recognition accuracy. |
| | Whisper Large-v3 | Insufficient Azerbaijani speech recognition accuracy. |
| | Whisper Distil-Large-v3 | Insufficient Azerbaijani speech recognition accuracy. |
| | Faster-Whisper (CTranslate2 backend) | + |
| STT Backend | Faster-Whisper | + |
| Large Language Model (LLM) | Qwen 2.5 7B | High inference latency; often generated incorrect answers or failed to answer user queries. |
| | Llama 3.2 3B | High inference latency; often generated incorrect answers or failed to answer user queries. |
| | Aya 8B | High inference latency; often generated incorrect answers or failed to answer user queries. |
| | Gemma4:e4b | + |
| | Qwen3 14B | High inference latency on our hardware; occasionally produced hallucinations and unexpected responses in Chinese. |
| LLM Inference Engine | Ollama | + |
| | llama.cpp | -- |
| Text-to-Speech (TTS) | Edge TTS – az-AZ-BanuNeural | Babek  |
| | Edge TTS – az-AZ-BabekNeural |  |
| | gTTS (fallback) | Lower speech quality and less natural Azerbaijani pronunciation than the selected TTS solution. |
| | edge-tts | Not selected because another TTS configuration provided better overall performance for the project requirements. |
| Embedding Model | BAAI/bge-m3 (sentence-transformers) | + |
| Retrieval (RAG) | Custom Keyword-Overlap Retriever | We chose FAISS (IndexFlatIP) + BM25 (rank-bm25) over the other retrieval methods because they provided faster search performance. |
| | Knowledge Base Retrieval | We chose FAISS (IndexFlatIP) + BM25 (rank-bm25) over the other retrieval methods because they provided faster search performance. |
| | ChromaDB + Knowledge Base | We chose FAISS (IndexFlatIP) + BM25 (rank-bm25) over the other retrieval methods because they provided faster search performance. |
| | FAISS (IndexFlatIP) | + |
| | BM25 (rank-bm25) | + | 

# TODO LIST 

---

## 1. Conversation Memory 

Improve the assistant's ability to maintain context throughout a conversation. 

### Tasks

- [ ] Implement short-term conversation memory (last 5–10 conversation turns).
- [ ] Resolve references such as **it**, **they**, **those**, **the previous one**, etc.
- [ ] Track the current conversation topic across multiple turns.
- [ ] Handle follow-up questions without requiring the user to repeat context.

### Example

**User:** Tell me about your services.

**Assistant:** *Provides information about the available services.*

**User:** Which of them is the most popular?

The assistant should understand that **"them"** refers to **services**.

---

## 2. FAQ Knowledge Base

Improve the robustness of the knowledge base by covering different ways users ask the same question.

### Tasks

- [ ] Add multiple paraphrases for every FAQ question.
- [ ] Include synonyms and common user expressions.
- [ ] Add common spelling mistakes and informal wording.
- [ ] Cover short follow-up questions related to each topic.

### Example

**Original Question**

> How can I enroll in a course?

**Alternative Questions**

- How do I register?
- How do I sign up?
- I want to join a course.
- How can I enroll?
- How do I start?

---

## 3. Retrieval-Augmented Generation (RAG)

Improve knowledge retrieval quality.

### Tasks

- [ ] Retrieve only the most relevant documents.
- [ ] Eliminate duplicate or irrelevant context.
- [ ] Improve retrieval accuracy using better embeddings or ranking strategies.

---

## 4. Hallucination Prevention

Ensure that responses remain factual.

### Tasks

- [ ] Generate answers only from the knowledge base.
- [ ] Respond with *"I don't have information about that."* when information is unavailable.
- [ ] Prevent fabricated or unsupported responses.

---

## 5. Prompt Engineering

Improve the quality and consistency of LLM responses.

### Tasks

- [ ] Refine the system prompt.
- [ ] Ensure responses are always in Azerbaijani.
- [ ] Keep responses concise and natural.
- [ ] Avoid unnecessary introductions and filler phrases.

---

## 6. Context Management

Provide the model with sufficient context for accurate responses.

### Tasks

- [ ] Send conversation history together with retrieved knowledge.
- [ ] Preserve context during long conversations.
- [ ] Reset context appropriately after a complete topic change.

---

## 7. User Personalization

Create a more natural conversational experience.

### Tasks

- [ ] Remember the user's name during the conversation.
- [ ] Personalize responses using available user information.
- [ ] Maintain session-specific preferences.

---

## 8. Voice Pipeline Optimization

Improve overall responsiveness.

### Tasks

- [ ] Reduce end-to-end latency.
- [ ] Improve speech recognition accuracy.
- [ ] Optimize Voice Activity Detection (VAD).
- [ ] Improve Text-to-Speech pronunciation and quality.

---

## 9. Error Handling

Handle recognition failures gracefully.

### Tasks

- [ ] Detect unclear speech.
- [ ] Ask for clarification instead of making assumptions.
- [ ] Handle interrupted or incomplete sentences.

---

## 10. Testing

Evaluate the assistant under realistic scenarios.

### Tasks

- [ ] Test multi-turn conversations.
- [ ] Test reference resolution (e.g., *it*, *they*, *those*).
- [ ] Test ambiguous and incomplete questions.
- [ ] Test topic switching and returning to previous topics.
- [ ] Test multiple variations of the same question.

---

# Future Improvements

- [ ] Long-term memory across sessions.
- [ ] Function Calling / API integrations.
- [ ] Streaming LLM responses.
- [ ] Emotion detection.
- [ ] Multilingual support.
- [ ] Prompt injection protection for RAG.
- [ ] Conversation analytics and logging.
