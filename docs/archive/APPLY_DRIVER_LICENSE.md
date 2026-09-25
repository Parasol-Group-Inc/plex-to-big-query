# Applying the DataDirect OEM SDK Client license to the Plex ODBC driver

## Why

The driver has been running **unlicensed** this whole time. `Dockerfile` just
copies raw driver files (`COPY driver/ /usr/oaodbc81/`) — it never runs the
vendor's installer, so no license file is ever generated. This matches the
cosmetic warning already documented in `TECHNICAL_REFERENCE.md`:

```
[DataDirect][ODBC OpenAccess SDK driver] You are not licensed to use this
Progress Software product under the license you have purchased...
```

We now have a real company license (from `zipfiles/64 bit License and
serial.txt`):

```
Version 8.1.X
Serial #  004193623
Key       35057920
Product   64-bit OEM SDK Client
```

Applying it may also resolve the 2026-07-19/20 production outage (`ODBC
error 2404 "Session refused by service"`) if that hard failure is a stricter,
license-gated enforcement on production vs. test — unconfirmed, but worth
ruling out before pursuing it purely as a Plex Support ticket.

## How the license actually gets applied

Traced from `zipfiles/extracted_64_tar/unixpi.ksh` (the vendor's official
installer, matches the Dockerfile's `ksh` comment — it was never actually
run):

1. The installer prompts, in order: **User Name → Company Name → Serial
   Number → IPE Key** (their term for the "Key" field above).
2. It then calls `makelic64` (bundled ELF binary) with those values plus the
   target directory and machine type, which writes a license file named
   **`OAODBC64.LIC`** into the driver's install directory.
3. There is **no silent/scripted install mode** — this is an interactive
   installer with no batch flag. Do this once, by hand, in a real Linux
   environment (a throwaway Docker container is the easiest one you have).

## Steps

**1. Build a throwaway installer container** (matches the real Dockerfile's
base + system deps, but doesn't touch the actual pipeline image):

```bash
cd "f:/Desktop/Parasol/plex-to-big-query/zipfiles/extracted_64_tar"
MSYS_NO_PATHCONV=1 docker run -it --rm -v "$(pwd):/install" -w //install \
  --platform linux/amd64 debian:bookworm-slim bash
```

> **Git Bash (MINGW64) note:** without `MSYS_NO_PATHCONV=1` and the
> double-slash in `-w //install`, MSYS rewrites `/install` into a Windows
> path before Docker ever sees it (e.g. `the working directory
> 'C:/Program Files/Git/install' is invalid`). Both the env var and the
> double slash are belt-and-suspenders for the same MSYS path-mangling
> issue — keep both.

**2. Inside the container**, install what the installer needs and run it:

```bash
dpkg --add-architecture i386 && apt-get update && \
  apt-get install -y --no-install-recommends ksh libc6:i386 libncurses6:i386 libstdc++6:i386

export DEFDIR=/usr/oaodbc81
ksh unixpi.ksh
```

**3. Answer the prompts** as they appear:
   - Language: default/English
   - Machine type: it should auto-detect Linux x86_64; if asked to pick from
     a list, choose the Linux entry
   - Product selection: only one client for Linux — should auto-select
   - "Continue installation?" → **Y**
   - Install directory → `/usr/oaodbc81` (or accept the `$DEFDIR` default)
   - **User Name** → your name or a service identifier (e.g. `Emilio Dominguez`)
   - **Company Name** → `Parasol Group Inc` (match whatever the license was
     issued to)
   - **Serial Number** → `004193623`
   - **IPE Key** → `35057920`

   If it rejects the key (`LIC_WrongIPEKEY` or similar), stop and contact
   Plex/DataDirect — don't retry blindly, a bad license file can behave
   worse than no license file.

**4. Verify the license file was created:**

```bash
ls -la /usr/oaodbc81/OAODBC64.LIC
```

**5. Copy the now-licensed install directory back out** to a new location,
   then diff it against the repo's `driver/` folder — copy over whatever is
   new (primarily `OAODBC64.LIC`; check if any `.so` files were also
   refreshed by the installer):

```bash
# from a second terminal on the host, while the container is still running:
docker cp <container_id>:/usr/oaodbc81 ./licensed_driver_output
```

**6. Replace/update `driver/`** in the repo with the licensed output (the
   `OAODBC64.LIC` file at minimum), then rebuild and redeploy:

```bash
gcloud builds submit --config deploy/cloudbuild.yaml --project=voxdatalake \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD)
```

**7. Check the next test AND prod run.** If the license was the cause of the
   production failure, the "session refused" error should be gone and the
   cosmetic license warning should disappear from the logs. If production
   still fails with error 2404 after this, the license was not the cause —
   send `PLEX_SUPPORT_FOLLOWUP_PROD_SESSION.md` to Plex Support next.

## Outcome (2026-07-20)

Completed steps 1-7 end to end: ran the real installer (User Name `Emilio
Dominguez`, Company `Vox Nutrition`, Serial `004193623`, Key `35057920`),
generated a valid `OAODBC64.LIC`, uploaded it to
`gs://voxdatalake-build-assets/plex-odbc-driver/` (the bucket Cloud Build's
`fetch-driver` step actually reads — the local gitignored `driver/` folder
never reaches Cloud Build's source upload), rebuilt, redeployed, and
re-tested production.

**Result: the identical `2404 Session refused by service` error persisted,
even on retry.** This rules out client-side driver licensing as the cause of
the production outage. The license is correctly applied and should stay
applied (it's a real license the company owns), but it did not fix the
"session refused" error — that is a Plex-side account/session authorization
issue on production. See `PLEX_SUPPORT_FOLLOWUP_PROD_SESSION.md`.

## Note on the 32-bit package

`zipfiles/` also contains a 32-bit driver/license pair. Our container is
64-bit (`Plex_ODBC_v8_1_64_bit_linux.zip` / `ivoa27.so` 64-bit build in
`driver/lib64/`) — the 32-bit files aren't needed unless the deployment
target changes.
