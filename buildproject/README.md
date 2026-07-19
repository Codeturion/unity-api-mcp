# buildproject

Minimal Unity project used by CI to populate `Library/PackageCache` with the
package sources the ingest pipeline parses (Input System, Addressables,
uGUI/TMP, AI Navigation, Netcode). Opened once in batchmode by
`.github/workflows/build-db.yml`; not a game project.

Note: on Unity 6, TextMeshPro is merged into `com.unity.ugui` 2.x and
ResourceManager ships inside Addressables 3.x — they have no separate entries.
