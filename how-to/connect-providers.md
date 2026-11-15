# Connect a Server with the `OpenAI` Protocol

Use these steps to connect `LM Studio`, `llama.cpp`, `vLLM`, `OpenRouter`, `OpenAI`, `Groq`, or another compatible endpoint.

1. Click **Settings** at the bottom of the left sidebar.
2. In the **Models** tab, select a provider from **Provider**, or click **New Provider** to add an endpoint.
3. If you clicked **New Provider**:
   - Type a name in **Provider Name**.
   - Select `OpenAI-Compatible API` in **API Protocol**.
   - Type the endpoint URL in **Base URL**, such as `http://127.0.0.1:1234/v1`.
   - Click **Save Provider**.
4. Type or select the model identifier in **Model**.
5. If the server needs an `API` key, type it in **API Key**. Thea saves the key in your operating system keychain.
6. Click **Test Connection** to check that the endpoint answers and lists models.
7. Click **Save Settings**.
