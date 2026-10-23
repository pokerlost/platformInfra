# platformInfra

Read selected [baseRules](https://raw.githubusercontent.com/serrja/baseRules/bafcb63ed94b9769a0ca098e5db4b33c55dbc1b9/docs/engineering.md), then [Pokerlost norms](https://raw.githubusercontent.com/pokerlost/projectRules/904c65a3daab88802fb5e414cdaccc7ad2b555a8/docs/project.md) before the local contract below.
These full-SHA links are reading sources, not automatic loaders or grants. Review
the source diff, update the explicit pin and run docs checks for a rules refresh.
Local overrides apply only to this repository's stated ownership boundary.

Compose and Helm own application composition. Keep only declarative infrastructure, one artifact compatibility manifest, a small non-executing values adapter and verification code. No runtime administration service, Docker socket in workloads, arbitrary command dispatch or duplicated source-checkout inventory. Use exact project roots and preserve secrets, live data, existing Git metadata and storage. Kubernetes execution is restricted to task-owned disposable local Kind; no remote cluster, merge, release or production deploy is authorized.

Daily work uses `dev` and lint only. `main` and `test` stay unchanged until an
explicit promotion. Full acceptance, template render/update checks, builds and
releases are manual; a dev snapshot is not a verified release.
