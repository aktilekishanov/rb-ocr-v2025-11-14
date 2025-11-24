# RB-OCR prompts

This directory contains versioned prompt templates used by the LLM-based
processors in the RB-OCR pipeline.

## Structure

- `dtc/`
  - `v1.prompt.txt` – prompt for the document-type checker processor.
- `extractor/`
  - `v1.prompt.txt` – prompt for the data extractor processor.

Each subdirectory corresponds to a logical prompt family. Files are
named by semantic version (for now `v1`, `v2`, ...).

## How prompts are loaded

Processors use small helpers to resolve prompt paths:

- Document type checker: `prompts/dtc/{version}.prompt.txt`.
- Extractor: `prompts/extractor/{version}.prompt.txt`.

The `version` argument defaults to `'v1'` in both processors. New
versions should be added as additional files (for example
`v2.prompt.txt`) without modifying or deleting older versions that might
still be referenced by running code.

## Placeholder conventions

Current processors expect the prompt template to contain a single
placeholder for a JSON representation of OCR pages:

- The code uses `template.replace("{}", pages_json_str, 1)`.
- The first occurrence of `'{}'` is replaced by the serialized pages
  object.

When updating prompts:

- Keep the `'{}'` placeholder exactly once where the pages JSON must be
  injected.
- Avoid adding extra curly braces that could be confused with this
  placeholder.

## Stability and backward compatibility

- Treat existing prompt files as part of the external contract for a
  given version.
- When changing instructions or output schemas in a non-trivial way,
  introduce a new `vN.prompt.txt` rather than editing an existing file
  in-place.
- Coordinate processor changes (parsing, DTOs) with prompt changes so
  that each version remains self-consistent.
