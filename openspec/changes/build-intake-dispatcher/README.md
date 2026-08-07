# build-intake-dispatcher

Deterministic `resolve_route` node for the intake graph -- routes the `compliance_check` intent to its real wrapper target (`spec/check_compliance.py`); `provision`/`inquiry` resolve to unsupported until their workflows exist. No scope/policy/execution-grant integration yet -- none of those exist for real sessions on this branch.
