---
phase: 05-optional-enhancements
status: issues_found
depth: standard
files_reviewed: 43
findings:
  critical: 30
  warning: 16
  info: 0
  total: 46
---

# Phase 05: Code Review Report

## Shadow/Thesis

### BLOCKER 1: Every governed Thesis resolution receives an extra forbidden `thesis_id` and degrades to an error check

**Evidence:**
- `backend/app/theses/repository.py:227-232 adds `thesis_id` to the condition mapping returned by `get_condition``
- `backend/app/theses/service.py:93-100 passes that complete mapping to the evidence resolver`
- `backend/app/theses/evidence.py:198-203 removes `instrument`, `id`, `version_id`, and `copied_from_condition_id`, but not `thesis_id`, before `ThesisCondition.model_validate``
- `backend/app/theses/schemas.py:42-45 configures every Thesis model with `extra="forbid"``

**Impact:** Normal due checks cannot reach a governed reader; validation fails, the resolver returns `invalid_resolution_request`, and the service persists an error outcome. Pending confirmation re-resolution has the same defect because `get_pending` constructs the same augmented condition at repository.py:585-590.

**Fix:** Remove all repository metadata including `thesis_id` before model validation, or construct an explicit allowlisted `ThesisCondition` payload at the service boundary.

### BLOCKER 2: Candidate idempotency key aliases materially different distillation requests

**Evidence:**
- `backend/app/shadow/distillation.py:153-160 validates feature set, depth, leaf support, and exit/holding assumptions; lines 223-265 make those values part of the immutable candidate`
- `backend/app/shadow/repository.py:407-417 searches for an existing candidate using only evidence set, distiller version, rule schema version, and seed; lines 418-452 return that row`

**Impact:** A second request with the same seed but different features, tree parameters, assumptions, rules, or rule fingerprint silently receives the first immutable candidate. The persisted fact no longer represents the caller's request.

**Fix:** Key idempotency on a canonical digest of every identity-defining input/output (at least features, parameters, assumptions, and rule fingerprint), and return 409 on same logical key with divergent content.

### BLOCKER 3: Interrupted evaluation reservations are neither discoverable nor retryable

**Evidence:**
- `backend/app/shadow/repository.py:557-578 records only a `shadow_candidate_runs` row and returns an evaluation ID before execution`
- `backend/app/shadow/repository.py:636-660 implements get/list exclusively by joining from `shadow_candidate_evaluations`, which does not exist until completion`
- `backend/app/shadow/evaluation.py:133-138 requires `get_evaluation` to find a retryable terminal evaluation`

**Impact:** A process death after reservation and before `complete_evaluation` leaves truthful-looking `interrupted` run evidence that no API can retrieve or retry; the evaluation ID exists only inside the run manifest.

**Fix:** Persist a queryable evaluation-attempt identity atomically with the run (or query attempts by manifest/normalized columns), expose interrupted attempts, and make completion/retry idempotent by attempt ID.

### BLOCKER 4: Two-split evaluation is not atomic or restart-idempotent

**Evidence:**
- `backend/app/shadow/evaluation.py:110-131 executes and persists in-sample before starting out-of-sample`
- `backend/app/shadow/evaluation.py:205-222 appends and completes each attempt independently`
- `backend/app/shadow/evaluation.py:244-260 can raise while freezing the later split`

**Impact:** If out-of-sample freezing/persistence fails after in-sample completed, the request returns no result while leaving an orphaned immutable IS evaluation. Retrying the same POST creates another IS attempt rather than resuming the missing split.

**Fix:** Reserve a pair/operation record for both splits before execution, use an idempotency key, and resume/return the canonical per-split attempts after partial failure.

### BLOCKER 5: Retention idempotency silently substitutes a prior reviewer and rationale

**Evidence:**
- `backend/app/shadow/service.py:112-143 treats reviewer principal and rationale as part of the requested immutable retention fact`
- `backend/app/shadow/repository.py:704-729 deduplicates solely by candidate and evaluation IDs and returns the existing event without comparing principal or rationale`

**Impact:** A different reviewer—or the same reviewer with corrected rationale—gets success but their attributable decision is not recorded. This breaks audit immutability and can misrepresent authorization provenance.

**Fix:** Return the existing event only for an exact canonical payload replay; otherwise reject the conflicting decision with 409.

### BLOCKER 6: `same_content_as` leaks another principal's batch identifier

**Evidence:**
- `backend/app/shadow/repository.py:199-212 searches all prior batches with the same checksum and does not constrain `principal``
- `backend/app/shadow/projections.py:68-94 exposes `same_content_as` in the API batch projection`

**Impact:** Uploading content already imported by another principal discloses that principal's opaque batch ID and the fact that identical content exists, violating object authorization boundaries.

**Fix:** Include `principal = ?` in the duplicate lookup (or omit this relation from public projections).

### BLOCKER 7: The actionable pending endpoint includes stale, unreviewable conclusions from superseded versions

**Evidence:**
- `backend/app/theses/service.py:72-82 finds the current version but calls `list_pending` for the whole thesis`
- `backend/app/theses/repository.py:545-552 returns every pending conclusion for the thesis without version or review filtering`
- `backend/app/theses/service.py:191-201 later refuses old-version pending conclusions`

**Impact:** `GET /pending` labels old records as pending/actionable even though confirm/reject must return conflict. Ordering newer records first does not remove stale entries.

**Fix:** Query only the current version's unreviewed pending conclusions for the actionable endpoint; retain all-version records only in history with an explicit stale/resolved state.

### BLOCKER 8: Evidence-set construction can materialize millions of rows despite bounded request lists

**Evidence:**
- `backend/app/shadow/api.py:26-29 permits 128 batches plus 100,000 included and 100,000 excluded IDs`
- `backend/app/shadow/importer.py:62-66 permits 100,000 rows per batch`
- `backend/app/shadow/repository.py:249-264 executes `fetchall()` for every trade in all included batches before checking the selected-ID set at lines 266-271`

**Impact:** A valid principal can select 128 full batches and force roughly 12.8 million rows and decoded objects into memory even though at most 200,000 IDs can satisfy the manifest, causing resource exhaustion before rejection.

**Fix:** Check aggregate batch row counts in SQL against one evidence-member ceiling before fetching, reject oversized manifests, and stream/page any allowed rows.

### BLOCKER 9: Arbitrary assumption JSON has no byte, key-count, or string bounds

**Evidence:**
- `backend/app/shadow/api.py:32-40 accepts `exit_assumptions` and `holding_assumptions` as unrestricted `dict[str, object]``
- `backend/app/shadow/distillation.py:305-308 checks only that each mapping is non-empty and lines 233-234 copy it into the immutable candidate`
- `backend/app/shadow/repository.py:432-436 serializes both without a maximum size`
- `backend/app/shadow/projections.py:221-233 recursively projects every mapping entry and leaves scalar string lengths unbounded`

**Impact:** An authenticated request can drive excessive validation/serialization, persist very large immutable blobs, and generate oversized API responses.

**Fix:** Replace arbitrary dictionaries with strict typed schemas; cap nesting, key count, list length, scalar string length, and canonical serialized bytes at both service and repository boundaries.

### BLOCKER 10: Pagination and history are applied only after unbounded database/materialization work

**Evidence:**
- `backend/app/shadow/api.py:248-256, 310-325, 370-389, and 423-442 load and project complete collections before slicing`
- `backend/app/shadow/repository.py:461-466, 647-660, and 747-761 use unbounded `fetchall()``
- `backend/app/theses/service.py:54-70 and 165-189 load every check/history record (with per-condition queries) before the API pages at backend/app/theses/api.py:122-129 and 194-217`
- `backend/app/theses/api.py:220-226 exposes the complete unpaginated history ledger`

**Impact:** `limit <= 100` does not bound DB rows, authorization traversals, projection memory, or response size. Long-lived immutable ledgers can exhaust request workers.

**Fix:** Move ownership filters, deterministic ORDER BY, LIMIT/OFFSET (prefer keyset cursors), and counts into repository queries; separately paginate/bound versions, checks, pending records, and history events.

### BLOCKER 11: Evidence lookup uses the UTC calendar date instead of the condition's declared timezone

**Evidence:**
- `backend/app/theses/evidence.py:58 and 212-218 normalize `due_at` to UTC`
- `backend/app/theses/evidence.py:73-78 calls the reader with `as_of=due.date()``
- `backend/app/theses/schemas.py:121-123 makes cadence timezone an explicit condition field (`Asia/Shanghai`)`

**Impact:** For a Shanghai due instant whose local date differs from UTC (for example local midnight), the resolver requests and freshness-checks the previous calendar day's evidence.

**Fix:** Convert the due instant to `ZoneInfo(validated_condition.timezone)` and use that local date consistently for reader `as_of` and freshness bounds.

### WARNING 1: One scanner exception aborts the entire leased batch and can repeatedly starve later conditions

**Evidence:**
- `backend/app/theses/scheduler.py:41-67 processes all leases in one loop with no per-lease isolation or release path`

**Impact:** A persistent poison condition at the front of stable due ordering causes every later lease to remain untouched until expiry; the same ordered batch can then repeat indefinitely.

**Fix:** Handle failures per lease, record a bounded safe error/retry state, explicitly release or complete that lease, and continue processing the remaining acquired conditions.

### WARNING 2: Observed evidence fingerprints are not bound to the instrument

**Evidence:**
- `backend/app/theses/evidence.py:115-124 hashes source ID/revision, source kind, field, value, unit, and date but omits `resolved_instrument``
- `backend/app/theses/evidence.py:163-171 does include instrument for non-observation fingerprints`

**Impact:** If a governed reader reuses source IDs/revisions across instruments, equal values produce indistinguishable observed fingerprints, weakening pending-review attribution and audit identity.

**Fix:** Include the canonical instrument in both the observed evidence record and fingerprint payload.

### WARNING 3: Failed artifact cleanup is silently discarded after database failure

**Evidence:**
- `backend/app/shadow/importer.py:205-212 catches `ShadowArtifactError` from `discard_uncommitted` and does nothing`

**Impact:** Raw broker files can remain orphaned and unmanaged after a failed import transaction, with no surfaced remediation signal.

**Fix:** Record/raise a cleanup-specific failure or enqueue a durable reconciliation record so unreferenced namespaces are discoverable and removed safely.

## Forecast/Supply

### BL-01 — BLOCKER

**File:** `backend/app/forecast/catalog.py:303-331; backend/app/forecast/kronos_adapter.py:313-334; backend/scripts/provision_kronos.py:258-286`

**Issue:** The approved source/config identity is not bound to the bytes actually executed. Runtime source validation trusts only the self-reported `UPSTREAM.json` revision, while the worker imports `app.vendor.kronos` directly rather than the verified `checkpoint.source_dir`. Checkpoint verification hashes only `model.safetensors`; arbitrary `config.json` content passes if it parses as a dict. Modified vendored Python therefore passes revision checks and executes, and a poisoned config passes the approved weight digest.

**Fix:** At pre-spawn and worker load, verify the exact allowlisted vendored file SHA-256 values and ensure the verified directory is the imported directory. Add approved SHA-256 identities for both model/tokenizer `config.json` files and reject any mismatch; revalidate inside the child immediately before loading.

### BL-02 — BLOCKER

**File:** `backend/app/forecast/input.py:166-197`

**Issue:** `input_fingerprint` hashes only provenance/session metadata; none of the frozen OHLCV/amount values or the created artifact checksum participates. Changed market data can therefore produce the same trusted input identity and collide in idempotency, records, and audit provenance.

**Fix:** Compute a canonical digest of the selected frame (schema, row order, values) and include it in the fingerprint, or derive the input identity from the immutable artifact checksum plus the canonical metadata.

### BL-03 — BLOCKER

**File:** `backend/app/forecast/repository.py:442-481,509-538`

**Issue:** The sole immutable commit point accepts untrusted/defaulted provenance. Missing or malformed source/model/tokenizer digests are replaced with the unrelated input fingerprint; missing revisions become `unknown-*`; numeric sampling fields are merely coerced. The output descriptor horizon is only checked against `{5,20,60}`, not against the job/record horizon. A verifier-approved malformed manifest can therefore be committed as apparently trusted, internally inconsistent history.

**Fix:** Reject rather than default every provenance field; validate immutable revisions/digests against the selected catalog identity, validate finite/ranged sampling fields and future-session cardinality, and require descriptor horizon/sample/feature shape to match the committed record and verified artifact.

### BL-04 — BLOCKER

**File:** `backend/app/forecast/runner.py:154-162,351,413-490`

**Issue:** The advertised subprocess output bound is enforced only after output has already accumulated or crossed the IPC boundary. `StringIO` grows without limit during worker execution, and an arbitrary manifest is pickled, queued, and fully deserialized by `output.get()` before `_manifest_is_capped` checks JSON size. A faulty/compromised worker can exhaust child or parent memory despite `output_bytes`.

**Fix:** Use a streaming writer that refuses bytes beyond the cap, serialize the manifest to bytes inside the child, reject it there before IPC, and receive through a byte-oriented pipe with a hard maximum frame length before decoding/deserializing.

### BL-05 — BLOCKER

**File:** `backend/app/forecast/runner.py:149-153,536-547`

**Issue:** Process-group cleanup races child startup. The parent only calls `killpg(pid)`, but the process group does not exist until the child reaches `os.setsid()`. A timeout during spawn/import makes both `killpg` calls no-ops, and `_reap` can return with the worker alive, violating the wall-clock/restart bound.

**Fix:** Add a child-ready handshake after `setsid()` before starting the work deadline, and always fall back to `process.terminate()`/`process.kill()` when the group is absent or the child remains alive; verify descendants are gone before returning.

### BL-06 — BLOCKER

**File:** `backend/app/forecast/calibration.py:56-58,129-143; backend/app/forecast/repository.py:595-598`

**Issue:** The maturity scanner permanently starves newer forecasts. It scans oldest-first, counts canonical outcomes and `not_mature` results toward `max_items_per_scan`, then starts from the same first row next time. Once the first 32 horizon items exist, later forecasts are never reached.

**Fix:** Query only pending maturity candidates with a durable cursor/keyset pagination, or skip existing/not-yet-mature rows without consuming the append budget; advance the cursor transactionally across restarts.

### BL-07 — BLOCKER

**File:** `backend/app/forecast/calibration.py:56-58,70-75,84-112,150-161`

**Issue:** Restart/data-lag calibration is not correct. Maturity is recognized only when the current as-of ID is literally inside the forecast's finite future-session list, so a scanner restarted after that list ends reports `not_mature` forever. Conversely, if the target session is reached before actuals arrive, `missing_actual` is appended as a terminal fact and the canonical-outcome early return prevents later repair.

**Fix:** Compare governed calendar sequence values under the frozen calendar revision (`as_of_sequence >= target_sequence`). Treat unavailable actuals as retryable until a governed finality policy says they are permanently absent; only then append an unevaluable terminal fact.

### BL-08 — BLOCKER

**File:** `backend/scripts/provision_kronos.py:439-459,490-513`

**Issue:** Checkpoint provisioning is not concurrency-safe. Concurrent invocations read the same catalog snapshot and last-writer-wins their atomic replacements, dropping the other entry. Rollback also recursively deletes every directory this invocation promoted; with shared tokenizer directories, another successful invocation can begin using that directory before the loser deletes it.

**Fix:** Hold an inter-process lease/lock over catalog read-modify-write and promotions, or implement catalog CAS on a revision/digest. Promote each content-addressed asset once and never delete shared final directories during rollback; clean only invocation-owned staging paths.

### BL-09 — BLOCKER

**File:** `backend/app/forecast/calendar.py:52-74`

**Issue:** Future sessions are selected by lexicographic `session_id > after_session_id` without requiring the as-of session to exist in the selected calendar/revision or anchoring on its sequence. A malformed ID, missing calendar row, or daily/calendar revision mismatch silently produces a forecast against the wrong future-session window.

**Fix:** Validate the full `CNA-YYYYMMDD` form, resolve exactly one as-of calendar row, require it to be an open governed session, and select rows by `sequence > as_of.sequence`.

### BL-10 — BLOCKER

**File:** `backend/app/forecast/api.py:234-247; backend/app/forecast/calibration.py:129-143`

**Issue:** The record-scoped calibration refresh authorizes one record, then calls global `scanner.scan()`, which reads and appends maturity facts for every forecast. A caller authorized for one instrument can therefore trigger writes and actual-data access for unrelated instruments/principals.

**Fix:** Have this endpoint evaluate only the already-authorized record's eligible horizons. Keep global scanning in a trusted scheduler/operator path with its own authorization.

### WR-01 — WARNING

**File:** `backend/app/forecast/input.py:268-276`

**Issue:** An `amount` column is admitted after checking only non-null values, then included as a model feature even when other rows are null. The frozen matrix consequently contains null/NaN values and fails later at inference instead of governed-input validation.

**Fix:** Include `amount` only when every selected row is non-null and finite, or reject incomplete amount coverage.

### WR-02 — WARNING

**File:** `backend/app/forecast/artifacts.py:60-92`

**Issue:** The artifact store labels quantiles as path-derived and records the path checksum, but accepts any finite tensor of the right shape; it never recomputes or compares `np.quantile(paths, ...)`. Paths and calibration quantiles can be mutually inconsistent while both artifacts verify individually.

**Fix:** Derive quantiles inside `persist` from the validated paths, or compare the supplied tensor bit-for-bit/tolerance-bounded against the fixed path-axis quantiles before writing.

### WR-03 — WARNING

**File:** `backend/app/forecast/api.py:66-92,250-258,318-343`

**Issue:** SSE reconnection/admission is incomplete: `Last-Event-ID` is explicitly discarded, IDs restart at 1 on every connection, and subscribers are appended without any global/per-principal bound. Reconnects cannot resume a stable event sequence, and authenticated clients can create unbounded queues and polling streams.

**Fix:** Use persisted transition versions as stable event IDs and honor `Last-Event-ID`; add per-principal/job connection limits (plus server-wide rate limiting) and synchronize hub lifecycle.

### WR-04 — WARNING

**File:** `backend/app/forecast/repository.py:524-538`

**Issue:** Output path validation is lexical, not containment-based. It accepts `.` and does not reject absolute/drive-relative forms via `Path.is_absolute()`/drive checks; no resolved path is proven beneath an artifact root at the persistence boundary.

**Fix:** Resolve the descriptor path against the configured artifact root, require a regular non-symlink file, and enforce `resolved.relative_to(root)` before committing. Reject `.`, drive-qualified paths, backslashes/colons where unsupported, and non-normalized forms.

### WR-05 — WARNING

**File:** `backend/pyproject.toml:66-72`

**Issue:** The Forecast supply-chain extra pins the smaller packages exactly but allows any future PyTorch 2.x release (`torch>=2,<3`). Installing from the project manifest without a frozen lock can silently execute an unreviewed binary build.

**Fix:** Pin the reviewed PyTorch version/build exactly and enforce the locked artifact hashes/index in production provisioning.

## Host/Frontend

### BLOCKER 1

**Evidence:**
- `backend/app/main.py:633-642`
- `backend/app/main.py:669-672`

**Issue:** The unauthenticated “local network” branch is combined with wildcard CORS. Any web origin loaded in a browser on the same LAN/host can call and read the unconfigured API because the server trusts only the client IP and returns Access-Control-Allow-Origin: *. This defeats the intended local-only initialization boundary and exposes Phase 05 capability/data endpoints along with the rest of /api.

**Fix:** Require an exact trusted Origin/Host (or bind setup to loopback), do not use wildcard CORS for the unauthenticated state, and require initialization/authentication before exposing data APIs.

### BLOCKER 2

**Evidence:**
- `backend/app/main.py:669-672`
- `backend/app/main.py:683-686`

**Issue:** The supported unconfigured-local branch calls the API without assigning request.state.reviewer_principal; the principal is assigned only for cookie sessions. Shadow, Thesis, and Forecast handlers require that server principal, so the UI can report a module available while all principal-scoped reads/writes fail with 503/401 until a password is configured.

**Fix:** Either require authentication for all Phase 05 routes or mint a stable server-owned local principal only after fixing the Origin/Host exposure above.

### BLOCKER 3

**Evidence:**
- `backend/app/optional_modules.py:76-91`
- `backend/app/optional_modules.py:318-323`
- `backend/app/optional_modules.py:340-347`
- `backend/app/optional_modules.py:358-380`
- `backend/app/optional_modules.py:693-717`

**Issue:** Production capability probes/factories do not represent usable modules. Forecast always falls through to unavailable; Shadow is advertised available when sklearn exists but is wired with distiller=None and an evaluator that always raises; Thesis is always advertised available but all three governed evidence readers return None. A missing scheduler is also silently accepted, leaving Thesis checks and Forecast maturity scans inert while status remains available.

**Fix:** Probe the complete per-module dependency set and wire real distillation/evaluation, governed evidence readers, forecast catalog/runner, and required scanner. Report available only after that module’s complete service contract is operational; keep peers independent.

### BLOCKER 4

**Evidence:**
- `frontend/src/lib/phase5Api.ts:215-225`
- `frontend/src/pages/backtest/ShadowAccount.tsx:333-343`

**Issue:** The typed Shadow distillation payload cannot satisfy the server contract: it sends min_samples_leaf, min_support, min_precision, and training_window, while the endpoint requires min_leaf_support and forbids extra fields. Every distillation attempt returns 422.

**Fix:** Make ShadowDistillInput exactly match the backend schema and send min_leaf_support; remove unsupported fields or add them coherently to both contracts.

### BLOCKER 5

**Evidence:**
- `backend/app/optional_modules.py:260-279`
- `frontend/src/components/analysis/ForecastPanel.tsx:160-177`
- `frontend/src/components/analysis/ForecastPanel.tsx:303-321`

**Issue:** Forecast path pagination is row-based while the UI is path-based. The Parquet reader slices raw rows and returns their columns unchanged; stored artifacts use sample_index, but the frontend expects path_index and therefore collapses every row to path 0. total is the Parquet row count, so the UI reports thousands of “paths” and each page contains partial path/session data instead of 12 complete samples.

**Fix:** Project sample_index to path_index and paginate distinct samples, returning all horizon/feature rows for each selected sample plus total sample count (32). Type that response explicitly end to end.

### BLOCKER 6

**Evidence:**
- `frontend/src/components/analysis/AnalysisWorkspace.tsx:31-36`
- `frontend/src/components/analysis/ThesisPanel.tsx:211-219`
- `frontend/src/components/analysis/ThesisPanel.tsx:233-270`
- `frontend/src/components/analysis/ForecastPanel.tsx:281-315`

**Issue:** Subject changes retain previous-subject data via keepPreviousData while record IDs drive object endpoints. During a stock switch, old reports, Thesis versions/pending decisions, Forecast records, paths, calibration, and active jobs render under the new stock title; Thesis revision/review controls can mutate the old instrument because their endpoints accept only the stale object ID. Forecast path/calibration responses are also cached under the new instrument key.

**Fix:** Never use previous-subject data as placeholder data. Reset subject-owned selection/draft/job state on instrument changes, key the panels by canonical subject, and verify returned object.instrument matches the active subject before display or mutation.

### BLOCKER 7

**Evidence:**
- `frontend/src/components/analysis/AnalysisWorkspace.tsx:23`
- `frontend/src/components/analysis/AnalysisWorkspace.tsx:31-36`
- `frontend/src/lib/queryKeys.ts:59-63`

**Issue:** Analysis API requests use canonical server kinds instrument/account, but query keys use UI kinds stock/portfolio. The shared analysis_progress invalidator consumes server kinds, so completed runs do not invalidate these caches; reports/evidence/history can remain stale after terminal progress.

**Fix:** Use canonical serverSubject.kind in analysis query keys, or normalize SSE subject kinds to the UI namespace consistently before invalidation.

### BLOCKER 8

**Evidence:**
- `backend/app/operational/migrations.py:1219-1222`

**Issue:** Migrations are not atomic. sqlite3.executescript commits pending work and these scripts contain no explicit transaction, so a failure midway through the large Phase 05 schema can leave partially-created tables/triggers with user_version unchanged. Restart then replays the same migration and fails on existing objects, bricking the shared operational database and unrelated modules.

**Fix:** Execute each migration and user_version update in one explicit transaction, with a safe strategy for the scripts that toggle foreign_keys, and roll back the entire version on any statement failure.

### BLOCKER 9

**Evidence:**
- `frontend/src/pages/backtest/ShadowAccount.tsx:382-387`
- `frontend/src/pages/backtest/ShadowAccount.tsx:449-450`
- `frontend/src/pages/backtest/ShadowAccount.tsx:473-477`
- `frontend/src/pages/backtest/ShadowAccount.tsx:604`

**Issue:** Shadow confirmation is not bound to what was previewed. Preview runs only when a file is chosen or retry is clicked; mapping and timezone edits merely update local state, while confirm submits the edited values with the old preview still visible. Users can therefore approve an import transformation they never reviewed.

**Fix:** Invalidate/re-run preview whenever file, mapping, or timezone changes, and bind confirm to an immutable preview token or mapping/content fingerprint verified by the server.

### WARNING 1

**Evidence:**
- `frontend/src/components/analysis/ForecastPanel.tsx:287-292`
- `frontend/src/components/analysis/ForecastPanel.tsx:363`

**Issue:** A fresh idempotency key is generated inside every mutation invocation. Retrying after a response-loss/transport error submits a different key and can create a duplicate expensive job even if the first request committed.

**Fix:** Create and retain one operation key before submission; reuse it for ambiguity retries and rotate it only after a conclusive response or explicit new-job action.

### WARNING 2

**Evidence:**
- `frontend/src/components/analysis/ForecastPanel.tsx:369`

**Issue:** “基于相同配置创建新预测” calls setHorizon/setCatalogId and immediately invokes mutate; React state updates are asynchronous, so the mutation uses the previous render’s horizon/catalog rather than the selected record’s configuration.

**Fix:** Pass the record configuration directly as mutation variables instead of relying on just-scheduled state updates.

### WARNING 3

**Evidence:**
- `frontend/src/components/analysis/ForecastPanel.tsx:326-330`

**Issue:** Stale-record detection feeds governed session IDs such as CNA-YYYYMMDD to Date.parse. Those are not dates, so both values become NaN and the “已有更新行情” warning never appears.

**Fix:** Parse and compare canonical session ordinals explicitly (for example, validate/strip CNA- and compare YYYYMMDD), not with Date.parse.

### WARNING 4

**Evidence:**
- `frontend/src/lib/forecastTask.ts:188-206`
- `frontend/src/lib/forecastTask.ts:220-240`

**Issue:** The reconnect limit is ineffective for a flapping SSE connection because onopen resets the attempt counter to zero. A connection that repeatedly opens and then errors reconnects forever and never reaches the stopped/transportError state.

**Fix:** Reset the budget only after a sustained healthy interval or valid event; track consecutive failures across short-lived opens.

### WARNING 5

**Evidence:**
- `frontend/src/pages/backtest/ShadowAccount.tsx:304-308`
- `frontend/src/lib/queryKeys.ts:87-96`

**Issue:** Shadow mutation invalidation keys include the default offset/limit, so only page 0 is invalidated. When the user is on another batch/evidence/candidate/evaluation/retention page, writes leave the visible page stale even though inserts can shift every offset.

**Fix:** Invalidate the resource prefix (for example ['phase5','shadow','batches']) or the module-wide Shadow prefix, not a concrete default page key.

### WARNING 6

**Evidence:**
- `frontend/src/components/analysis/ThesisPanel.tsx:168-179`
- `frontend/src/components/analysis/ThesisPanel.tsx:293-319`

**Issue:** Client validation does not enforce the typed Thesis condition contract: between accepts one number and produces [value, undefined], while lookback accepts zero, negative, or fractional values. The form advances to confirmation and then receives a server 422.

**Fix:** Require exactly two finite ordered bounds for between and a positive integer lookback before opening review.

### WARNING 7

**Evidence:**
- `frontend/src/pages/StockAnalysis.tsx:95-133`
- `frontend/src/pages/StockAnalysis.tsx:302-305`
- `frontend/src/pages/StockAnalysis.tsx:327-351`

**Issue:** The stock page breaks its mobile/accessibility contract: fixed px-8 padding plus a non-wrapping row containing a fixed w-72 search and three buttons overflows narrow viewports; the confirmation overlay has no dialog semantics, focus trap, Escape handling, or focus return; and the delete control remains opacity-0 for keyboard focus because visibility is hover-only.

**Fix:** Use responsive padding/widths and flex-wrap; implement a labelled aria-modal dialog with managed focus/Escape/return; add focus-visible/group-focus-within visibility for delete.

### WARNING 8

**Evidence:**
- `backend/app/optional_artifacts.py:95-105`
- `backend/app/optional_artifacts.py:135-140`
- `backend/app/optional_artifacts.py:196-201`

**Issue:** Managed artifact cleanup/error translation catches only OSError/TypeError/ValueError. Real Parquet library failures (for example PolarsError/ComputeError) escape as raw exceptions and bypass _remove_temporary, leaving sensitive .<id>.tmp payload directories behind.

**Fix:** Catch the library’s documented exception base (and ensure cleanup in finally), then translate it to ManagedArtifactError while preserving the cause.

### WARNING 9

**Evidence:**
- `frontend/src/components/analysis/ThesisPanel.tsx:211-219`
- `frontend/src/components/analysis/ForecastPanel.tsx:280-282`
- `frontend/src/components/analysis/ForecastPanel.tsx:389`

**Issue:** Thesis and Forecast hard-code only their first API pages (25 versions/jobs/records; 50 checks/pending) and expose no pagination despite receiving totals/page metadata. Older immutable history silently disappears from the UI.

**Fix:** Add bounded pagination or progressive loading keyed by page/offset, preserving selection by immutable ID.

### WARNING 10

**Evidence:**
- `frontend/src/pages/backtest/ShadowAccount.tsx:58-105`
- `frontend/src/pages/backtest/ShadowAccount.tsx:586-590`
- `frontend/src/pages/backtest/ShadowAccount.tsx:606-607`

**Issue:** The retention dialog’s textarea minLength is not enforced because submission is a direct button click, and the dialog confirm button only checks pending. A short rationale triggers an API error rendered behind the modal, where keyboard users cannot reach or see it.

**Fix:** Disable confirm until the trimmed rationale is valid and render/announce mutation errors inside the active dialog.
