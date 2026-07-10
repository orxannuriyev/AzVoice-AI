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
| Day 6 | Ulviyye | Conducted general research to improve the overall project.<br>Researched creative ideas and presentation structure for the final project demonstration. |
| | Esli | Researched presentation ideas and prepared content for the final demo.<br>Updated the project README with the latest progress and documentation.<br>Tested different LLM and Speech-to-Text (STT) APIs across the pipeline to evaluate integration options and performance. |
| | Orxan | Continued development and optimization of the complete voice assistant pipeline.<br>Tested the AI assistant through real voice conversations to evaluate functionality, latency, and response quality.<br>Worked on database improvements and contributed to the development of the admin panel.<br>Conducted technical research to improve overall system performance and reliability. |
| | Ibrahim | Continued development and optimization of the complete voice assistant pipeline.<br>Tested the AI assistant through real voice conversations to evaluate functionality, latency, and response quality.<br>Worked on database improvements and contributed to the development of the admin panel.<br>Conducted technical research to improve overall system performance and reliability. |
| Day 7 | Ulviyye | Conducted technical research to improve overall understanding of the project architecture and implementation details.<br>Researched additional LLM and Speech-to-Text (STT) APIs to evaluate alternative integration options.<br>Explored creative ideas to make the final project presentation more engaging and interactive. |
| | Esli | Updated the project README with the latest implementation progress and documentation.<br>Started preparing a comprehensive project documentation describing the overall architecture, workflow, and development process.<br>Researched creative presentation ideas for the final project demonstration. |
| | Orxan | Continued optimization of the complete voice assistant pipeline to improve stability and performance.<br>Started implementing automatic fallback from cloud APIs to local models in case external services become unavailable.<br>Researched avatar animation solutions and began integrating animation into the existing assistant pipeline.<br>Performed pipeline testing and fixed integration-related issues. |
| | Ibrahim | Continued optimization of the complete voice assistant pipeline to improve stability and performance.<br>Started implementing automatic fallback from cloud APIs to local models in case external services become unavailable.<br>Researched avatar animation solutions and began integrating animation into the existing assistant pipeline.<br>Performed pipeline testing and fixed integration-related issues. |
| Day 8 | Ulviyye | Evaluated multiple open-source Text-to-Speech (TTS) models for the hotel voice assistant, comparing quality, latency, multilingual support, and deployment feasibility.<br>Documented findings and compared models for future integration decisions. |
| | Esli | Continued preparing technical documentation describing the overall system architecture and project workflow.<br>Researched presentation tools and platforms suitable for creating professional demo slides.<br>Reviewed different presentation formats for the final demonstration. |
| | Orxan | Continued development of the automatic cloud-to-local fallback mechanism and tested different failure scenarios.<br>Integrated animation components into the assistant workflow and evaluated synchronization between speech and avatar.<br>Optimized backend communication between different pipeline modules.<br>Conducted extensive testing to improve latency and reliability. |
| | Ibrahim | Continued development of the automatic cloud-to-local fallback mechanism and tested different failure scenarios.<br>Integrated animation components into the assistant workflow and evaluated synchronization between speech and avatar.<br>Optimized backend communication between different pipeline modules.<br>Conducted extensive testing to improve latency and reliability. |
| Day 9 | Ulviyye | Compared the performance of evaluated TTS models and analyzed their suitability for hotel assistant deployment.<br>Continued researching presentation improvements and prepared additional ideas for the final demonstration.<br>Shared technical findings with the team to improve overall project knowledge. |
| | Esli | Improved the voice assistant by fixing Speech-to-Text issues, including reducing background noise transcription, improving spoken-word recognition, and enhancing reservation code recognition accuracy.<br>Continued refining project documentation based on recent implementation updates. |
| | Orxan | Refined animation integration and synchronized avatar behavior with generated speech.<br>Further optimized the complete assistant pipeline for lower latency and improved responsiveness.<br>Improved API error handling and overall system robustness.<br>Conducted real-world testing using complete voice conversations and resolved discovered issues. |
| | Ibrahim | Refined animation integration and synchronized avatar behavior with generated speech.<br>Further optimized the complete assistant pipeline for lower latency and improved responsiveness.<br>Improved API error handling and overall system robustness.<br>Conducted real-world testing using complete voice conversations and resolved discovered issues. |
| Day 10 | Ulviyye | Finalized the evaluation of open-source TTS models and documented recommendations for future deployment.<br>Reviewed the overall project and contributed final presentation improvements and technical preparation for the demonstration. |
| | Esli | Generated additional data variations to improve assistant robustness and conducted another round of end-to-end testing.<br>Finalized project documentation and updated the README with the latest development progress.<br>Completed preparation of presentation materials and demonstration content. |
| | Orxan | Finalized optimization of the complete assistant pipeline and validated the automatic cloud-to-local fallback mechanism.<br>Completed animation integration and verified synchronization during live conversations.<br>Performed end-to-end system testing, fixed remaining issues, and prepared the assistant for the final demonstration.<br>Improved overall system stability, reliability, and deployment readiness. |
| | Ibrahim | Finalized optimization of the complete assistant pipeline and validated the automatic cloud-to-local fallback mechanism.<br>Completed animation integration and verified synchronization during live conversations.<br>Performed end-to-end system testing, fixed remaining issues, and prepared the assistant for the final demonstration.<br>Improved overall system stability, reliability, and deployment readiness. |



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

---

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

---

# TODO LIST 

## Project Progress 

| Component | Status | Notes |
|-----------|:------:|-------|
| Voice Activity Detection | ✅ Working | Silero VAD integrated |
| Speech-to-Text | ✅ Working | Faster-Whisper + Whisper |
| Large Language Model | ✅ Working | Gemma 4:e4b via Ollama |
| Retrieval-Augmented Generation (RAG) | ✅ Working | FAISS + hotel knowledge base |
| Text-to-Speech | ✅ Working | Edge TTS (Azerbaijani voices) |
| End-to-End Voice Pipeline | ✅ Working | STT → RAG → LLM → TTS |
| Performance Evaluation | ✅ Working | Latency and response quality benchmarked |
| Docker Deployment | ✅ Working | Development environment configured |
| Tool Calling | ✅ Working | External function integration |
| Hotel Knowledge Base Expansion | 🔧 In Progress | Dataset and JSON improvements |
| Website | ⏳ Planned | User interface and project demonstration |
| Presentation | ⏳ Planned | Final demo slides and project overview |
| Monitoring Dashboard | ⏳ Planned | Conversation analytics and logs |
| Web/Admin Interface | ⏳ Planned | Hotel operator dashboard | 


