# Component Compatibility

| Release lane | Core | Plugin | Bootstrap | Scout | Review Pack | Python |
|---|---:|---:|---:|---:|---:|---|
| v0.3.3 | 0.3.3 | 1.2.1 | 1.7.1 | 5.5.0 | v4 | 3.11–3.13 |
| v0.3.2 | 0.3.2 | 1.2.1 | 1.7.0 | 5.5.0 | v4 | 3.11–3.13 |
| v0.3.1 | 0.3.1 | 1.2.0 | 1.7.0 | 5.5.0 | v4 | 3.11–3.13 |
| v0.3.0 | 0.3.0 | 1.1.0 | 1.6.0 | 5.5.0 | v4 | 3.11–3.13 |
| Historical rollback | 0.2.0 | n/a | n/a | n/a | n/a | See tag |

The Python wheel/sdist contain Core only. Plugin, Bootstrap, and Scout ship in the portable bundle. A row is publishable only when
the release manifest, package metadata, Plugin manifest, Skill contracts, archive names, and installed-runtime smoke agree.
`requires-python >=3.11` expresses install eligibility; the table records the versions actually supported and tested. A newer Python
version is not claimed supported until it enters this matrix, even if its installer accepts the package metadata.
