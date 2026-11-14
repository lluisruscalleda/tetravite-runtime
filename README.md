# TETRAVITE Runtime v0.1.0

**Reference runtime for the proposed [TETRAVITE specification](../tetravite-spec/README.md) (`tetravite.dev/v1alpha1`).**

A **Tetravite** is a versioned, contract-driven capability package. **TETRA** stands for four engineering pillars: **Contract**, **Execution**, **Trust**, **Composition**. A Tetravite is **not an AI model**, a prompt, or an autonomous agent: it defines a verifiable operational interface around code, API calls, or AI-powered capabilities. The runtime is the *executor*, not the capability itself.

## What this runtime does

1. Reads `tetravite.yaml` from a local package or a ZIP.
2. Checks supported manifest fields and the four TETRA declarations.
3. Validates JSON input against the package input schema.
4. Executes the declared Python `module:function` entrypoint in a subprocess using JSON stdin/stdout.
5. Applies a wall-clock timeout and validates the returned JSON against the output schema.
6. Returns a JSON envelope with the result or a structured error.

## What it does NOT do

- **NOT a security sandbox**: subprocess execution has the permissions and network access of the invoking OS user. `security.networkAccess` is descriptive and is **not enforced**.
- **NOT safe for untrusted ZIPs or third-party code**: `--allow-execution` confirms trust, not isolation. ZIP extraction blocks common traversal and symlink entries but cannot make code safe.
- **NOT a full AI orchestrator**: no scheduling, routing, multi-step workflows, LLM, distributed execution, or container isolation.
- **NOT a dependency installer**: install the Tetravite's Python dependencies into a dedicated environment yourself before execution.
- Does not enforce CPU/memory limits or guarantee bounded stdout/stderr memory usage. Do not use this alpha runtime for hostile workloads.

## Quick start

```bash
python -m pip install -e .
python -m unittest discover -s tests -v

# From the sibling SEO auditor package, after installing its dependencies:
tetravite inspect ../seo-technical-auditor-1.0.0
printf '{"url":"https://example.com"}' | tetravite run ../seo-technical-auditor-1.0.0 --allow-execution
```

To run the ZIP directly (with the dependencies installed):

```bash
printf '{"url":"https://example.com"}' | tetravite run ../seo-technical-auditor-1.0.0.zip --allow-execution
```

The live SEO example requires network access. Tests use a local fixture without network access.

## Integration

```text
External orchestrator
    -> select Tetravite
    -> tetravite run <trusted-package> --input input.json --allow-execution
    -> validated JSON result
    -> orchestrator composes next step
```

For production, run packages in isolated containers/VMs with restricted filesystem, network egress, resource quotas, and signed artifact verification. See `docs/security.md`.

**Status:** experimental proof of concept, not a certified standard or production-ready security boundary. MIT licensed.
