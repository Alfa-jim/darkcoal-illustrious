# Published worker

Runtime source commit: `a484b4fdf4a9c85f40c39431625f6085b06bee23`.

Verified public image:

```text
ghcr.io/alfa-jim/darkcoal-illustrious@sha256:806451660bbc014160da9a39d8708668160840abfb0bad0d1e2c21b7faa74b7e
```

The OCI index above selects Linux AMD64 manifest `sha256:56960ed95ed595fd812ff3049689d6fdfd37735be77d72387457f9c02a5a4436`. Anonymous manifest/config retrieval, SHA256 and platform checks passed for both `latest` and the runtime commit tag. This verifies public registry access; it does not claim a full local Docker pull or a RunPod GPU generation.

[Build and CPU smoke evidence](https://github.com/Alfa-jim/darkcoal-illustrious/actions/runs/38263560405). The actual ComfyUI registry includes checkpoint, LoRA, sampler and pinned IPAdapter reference nodes. The model directory contains only 156 KB of placeholders/configuration; model weights are loaded from the attached volume.

Compressed layers total **14,468,560,441 bytes (14.47 GB)**. The existing worker's dependencies make this a large image despite having no baked model weights. Allow time for a first pull and provision **50 GB container disk**, independently of the shared network-volume quota.

Later assets-only commits update the separately served playground, installer and documentation, run tests, and retain this runtime image. GPU quality, reference adherence and memory behavior are still acceptance checks on the user's endpoint.
