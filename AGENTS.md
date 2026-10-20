# platformInfra

Read selected [baseRules](https://raw.githubusercontent.com/serrja/baseRules/730418d3cc480b4f05b88b4c8275296c4845a75a/docs/engineering.md), then [Pokerlost norms](https://raw.githubusercontent.com/pokerlost/projectRules/4785546cffa58f7ae1c22b6d6b8846a0141793eb/docs/project.md) before the local contract below.
These full-SHA links are reading sources, not automatic loaders or grants. Review
the source diff, update the explicit pin and run docs checks for a rules refresh.
Local overrides apply only to this repository's stated ownership boundary.

Compose and Helm own application composition. Keep only declarative infrastructure, one artifact compatibility manifest, a small non-executing values adapter and verification code. No runtime administration service, Docker socket in workloads, arbitrary command dispatch or duplicated source-checkout inventory. Use exact project roots and preserve secrets, live data, existing Git metadata and storage. Kubernetes execution is restricted to task-owned disposable local Kind; no remote cluster, merge, release or production deploy is authorized.
