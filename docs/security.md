# Security model

The alpha runtime **does not sandbox Python code**. A subprocess can read accessible files, access the network, spawn children, and execute arbitrary code. The timeout terminates the immediate process only; it is not a process-tree guarantee. Declared capabilities and network policies are not enforced. Python `-I` only isolates interpreter environment configuration, not operating-system privileges. Do not run untrusted packages.

For production: use a hardened container/VM per execution, non-root identity, no host mounts or secrets, egress allowlists enforced outside the process, CPU/memory/PID limits, process-tree termination, dependency provenance, signature verification, and auditing. Validate archive provenance and inspect dependencies before allowing execution. Input/output JSON Schema validation does not make an operation safe.
