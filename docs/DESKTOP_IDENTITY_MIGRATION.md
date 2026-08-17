# Desktop identity migration

The desktop identity is `ImperaOS` with bundle identifier `com.imperaos.operatorpanel`. Older AegisOS application-data locations and renderer settings are migration inputs only. Installation must not destructively uninstall or delete the legacy application data. The renderer copies non-secret settings to `imperaos.operator.settings.v2`; raw credential fields are discarded and the old key is removed only after valid parsing.
