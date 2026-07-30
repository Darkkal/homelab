# Ideal Configuration for Qwen 3.6

Qwen 3.6 has a "Thinking" habit similar to Gemma but uses different tokens.

- Instruction Template: Use the *Qwen2* template in SillyTavern.
- Thinking Mode: Qwen 3.6 often uses `<thought>` tags.
- Vision Tip: Qwen 3.6 is stricter with video/images. If you send it multiple images, ensure your "Context Size" in Koboldcpp is at least *16,384* to account for the large visual embeddings.
