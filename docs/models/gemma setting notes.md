# SillyTavern Configuration

SillyTavern needs to be tuned to handle Gemma 4's logic-heavy nature.

## API Settings

- API: Text Completion (or Chat Completion if using the /v1/chat/completions endpoint).
- Model Type: Select Gemma 4 from the instruction template dropdown. If it's not there, you must create a custom template.

## Instruction Template (Crucial)

Gemma 4 uses a specific header. If you want it to "think" before responding (Chain of Thought), use this structure:

- System Prompt Prefix: `<|turn|>system\n`
- Input/User Prefix: `<|turn|>user\n`
- Output Prefix: `<|turn|>model\n<|think|>\n`
- Assistant Prefix: `<|turn|>model\n<|channel>thought\n`
- Pro-Tip: Putting `<|think|>\n` at the end of the Output Prefix forces the model to enter its reasoning mode for every response. This makes characters much smarter and more observant of your persona's traits.

## Sampler Settings (Google Recommended)

Gemma 4 performs best with very specific "flat" samplers. Don't over-process the output with heavy penalties.

- Temperature: `1.0` (Start here; lower to 0.8 only if it gets too "creative/weird").
- Top P: `0.95`
- Top K: `64`
- Min-P: `0.1` (Excellent for filtering out low-probability "garbage" tokens).
- Repetition Penalty: `1.05` (Keep this low; Gemma 4 is much better at not repeating itself than its predecessors).

## Ideal Roleplay Configuration

Because Gemma 4 handles System Prompts natively now, you can be much more descriptive in your "Global Summary" or "Author's Note."

- Pacing: Gemma 4 tends to be "beat-by-beat." If it moves too fast, add Write in a slow, descriptive pace, focusing on internal monologue to your System Prompt.
- Formatting: If the "Thinking" blocks are cluttering your UI, go to SillyTavern Settings > User Settings > Appearance and ensure you have a "Thought Pattern" regex or CSS enabled to hide the text between `<|think|>` and `</|think|>`.

## Troubleshooting Loop/Garbage

If you see the model repeating symbols like }}}}}} or switching languages:

- Disable DRY: Turn off the "DRY" (Don't Repeat Yourself) sampler; it sometimes conflicts with Gemma 4's internal logic.
- Check EOS Token: Ensure the "End of Sentence" token is correctly mapped in Koboldcpp (it should be `<|file_separator|>` or `<|end_of_turn|>`).

## The Ideal Model File (GGUF)

For 16GB VRAM, you want a UD (Uncertainty-Dampened) or standard GGUF quant.

- Best Choice: Gemma-4-26B-A4B-it-Q3_K_M.gguf (~12.5GB)
- Why: This leaves ~3.5GB of VRAM for your 32K Context Window and overhead. If you go to Q4, you will run out of VRAM the moment the conversation gets long, forcing the model to offload to your slower system RAM.

## SillyTavern Vision

In SillyTavern, go to Extensions > Multimodal.Ensure the "Visual Token Budget" is set to at least *1024* (Gemma 4 is very sensitive to image compression; low token budgets make it "blind" to small details).
