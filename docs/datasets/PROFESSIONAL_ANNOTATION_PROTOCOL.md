# Professional volleyball video annotation protocol

**Protocol version:** `volley-signals-v1`  
**Target dataset:** `next-level-golden-v1`  
**Status:** operational contract; human labels not yet completed

## Purpose

This protocol defines what “correctly labelled” means for high-level volleyball analysis. It prevents a common failure mode: training several independent detectors whose outputs cannot be joined into a coherent rally. Every retained label must ultimately answer one or more of these questions:

- Where is the court and how reliable is its metric calibration?
- Which people are active players, which team and track do they belong to, and where are they?
- Where is every relevant body joint before, during and after a contact?
- Where is the ball in every live-play frame, including explicit occlusions?
- Which player touched it, in which exact frame, with what action and contact surface?
- What trajectory segment occurred between two contacts?
- Which tactical and biomechanical measurements are valid, estimated or unavailable?

## Annotation hierarchy

```
match → set → rally → possession → ordered contact → source frame
                                      ├─ actor track + pose
                                      ├─ ball 2D / optional 3D
                                      ├─ action + contact surface
                                      └─ incoming/outgoing trajectory
```

No event may be identified by a frame number alone. Every reference carries the video hash, source frame index and timestamp.

## Coordinate systems

1. **Image coordinates:** original 1280×720 pixels; origin at top-left, x rightward, y downward.
2. **Court plane:** metres; origin at the near-left court corner from the calibrated camera, x across the 9 m width and y toward the far baseline over 18 m.
3. **Metric 3D:** same court axes, z upward. This is reference-quality only when reconstructed from at least two synchronized calibrated cameras.
4. **Monocular 3D:** always labelled `monocular_physics` or `monocular_size_prior`, with uncertainty. It is an estimate, never ground truth.
5. **Player-centric tactical frame:** derived later from court coordinates and team direction; never annotated independently.

## Court calibration marks

Annotate the ten named intersections whenever the camera moves or a new clip begins:

- Near and far baseline × left/right sideline.
- Near and far attack line × left/right sideline.
- Centre line × left/right sideline.

Lines hidden by players are marked occluded, not guessed as visible. Calibration must record its homography, method, confidence and reprojection error. Metric 3D additionally requires camera intrinsics and extrinsics. A calibration above 3 px reprojection error is reviewed; it cannot silently feed precision metrics.

**Data model (added 2026-08-31, in direct response to an external annotation-spec review)**: `volley_domain.ontology.CameraSegment` is a contiguous span of one video where a single camera framing holds -- a broadcast cut, pan or zoom starts a new segment, since one homography is only ever valid within one framing. Every segment carries `shot_type` (`main_wide`/`endline_wide`/`side_wide`/`closeup`/`replay`/`scoreboard`/`other`) and `tactical_usable` (`usable`/`not_usable`/`partial`) -- **replays and close-ups get `tactical_usable=not_usable` and must never silently enter real-match statistics alongside genuine live-play framing.**

`volley_domain.ontology.CourtCalibration` is the production-side mirror of the ground-truth `volley_domain.annotation.CameraCalibrationAnnotation` schema (the schema this protocol and `dataset_factory.professional_signal_qa`'s 3 px gate already assume) -- deliberately kept field-compatible with it rather than a separate vocabulary. It holds `image_width`/`image_height` (a homography is only valid for the exact pixel frame it was fitted on -- record these, don't assume the video's own dimensions, since a calibration may be fitted on a downscaled proxy), the homography (3x3 matrix, JSON) plus the named keypoints used to compute it (JSON, same field names/polarity as `CourtKeypointAnnotation`: `keypoint_name`/`x_pixel`/`y_pixel`/`visible`), `method` (`automatic`/`manual`/`hybrid` -- matching `calibration_mode` and CLAUDE.md's own "hybrid auto-calibration ... with a manual ... fallback" wording), `confidence`, `reprojection_error_px`, and the optional Phase-B metric-3D fields (`camera_matrix`, `rotation_world_to_camera`, `translation_world_to_camera_m`, `supports_metric_3d`) for one `CameraSegment`. A segment may accumulate more than one calibration over time (e.g. a manual recalibration superseding an earlier automatic one); superseded rows are kept, never deleted, marked via `superseded_at` (not "most recent `created_at` wins" -- two calibrations written in the same transaction get an identical Postgres `now()`, verified directly). `created_by_user_id` is set for a manual/hybrid calibration; null for a fully automatic one.

## Person boxes and identity

- Use a tight full-person box around the physical body, excluding cast shadows and loose background.
- For partial occlusion, estimate the full body extent and set `occluded=true`.
- If the body crosses the image boundary, fit only to the visible image extent and set `truncated=true`.
- Maintain one `track_id` for the same physical player across the full clip; never recycle an ID.
- Anatomical left/right is the player's left/right, not the viewer's.
- Assign `person_role`: `on_court_player`, `substitute`, `official`, `staff` or `spectator`. Hard-negative people remain labelled so the detector learns not to turn benches and officials into active players.
  - A referee (on the stand or on the floor) is `official`. A coach standing off-court before/during a rally is `staff`. Both roles already exist in the schema; the work is applying them consistently, not inventing new ones.
  - **A detected box that is not a person at all (net post, ball cart, camera/broadcast equipment) is not a role -- reject it** with `review.status="rejected"` and a concrete `reason` ("net post, not a person"). Do not force it into `spectator`/`staff` just because the box shape resembles a person; a generic COCO-pretrained detector will produce these, especially on thin vertical structures near the net, and rejecting them (not silently dropping them unreviewed) is what teaches the next detector iteration not to repeat the mistake.
- The **libero** is identified by a jersey visibly distinct from their own team's other players, per FIVB rules -- confirm with `position="L"` (an existing `RosterPosition` value; no separate boolean is needed) rather than inventing a new field. Never infer team membership purely from jersey similarity when the player in question is a libero -- their jersey is deliberately different from their own teammates', which is exactly why `volley_ml.detection.jersey_color`'s clustering heuristic (see below) flags them as a color outlier for review rather than assuming they belong to whichever team's color they're closer to.
- Team, jersey and roster position may be `unknown`; uncertain identity must not be guessed from appearance.
- Face recognition is prohibited.

### Roster position taxonomy

`RosterPosition` (`volley_domain.ontology`) is the specialized playing position, not the current rotational court zone (1-6, which changes every rotation -- see "Rotation/zone derivation" above): `OH` (outside hitter / receptor), `OP` (opposite / opuesto), `MB` (middle blocker / central), `S` (setter / colocador), `L` (libero). This is a match-long attribute of the physical player, not a per-frame fact.

**A player's position generally cannot be determined from a single frame's bounding box alone** -- unlike the libero (visually distinct jersey) and unlike rotational zone (derivable from calibrated position + `volley_ml.court.rotation`), telling a setter from an outside hitter from a single static box requires either recognizing their jersey number and cross-referencing a known roster (jersey-number OCR is not implemented; a roster mapping would need to be supplied per match, which this project does not yet have for real footage) or observing their *behavior* across a rally (who sets, who blocks at the net, who attacks from the pins) -- a temporal/tracking task, not a single-frame one. Guessing position from a player's momentary body position or role-typical zone is exactly the "uncertain identity must not be guessed from appearance" case above -- mark it `unknown` (`position=None`) rather than inferring it.

**What is buildable, and built**: `volley_domain.annotation.propagate_roster_position_by_track` cuts the labeling cost from "once per frame" to "once per track" -- a reviewer confirms a player's position once, for one frame of their track, and it propagates to every other frame of the same physical player in the same clip. It never overwrites an already-labeled frame and only propagates from a *reviewed* label (an unconfirmed model guess must never fan out). Run it once per imported clip before `professional_signal_qa`.

### Model-assisted reviewer aids (heuristics, never authoritative)

Two heuristics exist purely to raise a candidate's position in the human review queue -- neither ever sets `person_role` or `team` directly, and both are unvalidated against real calibrated footage as of 2026-08-30 (no reviewed labels exist yet to validate against, see TECH_DEBT.md):

- **Jersey-color clustering** (`volley_ml.detection.jersey_color.cluster_jersey_colors`): groups on-court-sized boxes in one frame by dominant torso color and flags any box with no close-color company as `jersey_color_outlier=True` -- exactly the signal that catches a libero, a referee in a distinctly colored shirt, or (as a side effect) a non-person false detection whose "torso crop" color happens not to match either team. `preannotation_queue.py` raises that candidate's review priority; it does not change what the reviewer must still decide.
- **Rotation/zone derivation** (`volley_ml.court.rotation`): once a calibrated homography exists for a camera setup, converts a player's real-world court-plane position into `volley_domain.court`'s standard 1-6 rotational zone and front/back row -- letting a reviewer (or a future overlay UI) show "this player is currently in zone 1 (back-right, about to serve)" instead of requiring it to be worked out by eye. This module is unvalidated against a real calibrated frame (see its own docstring for the specific camera-orientation caveat on the left/right axis) -- confirm its output against a frame with a visually-obvious server position (server always starts in zone 1) before trusting it on a new camera setup.

## Pose marks

The reference skeleton has 23 COCO-WholeBody-compatible body/foot points: face anchors, shoulders, elbows, wrists, hips, knees, ankles, heels, big toes and small toes. Derived joints such as neck or pelvis centre are computed from labelled points, not manually invented.

- `visible`: exact pixel can be seen.
- `occluded`: anatomical position can be inferred from the tracked body but is hidden.
- `outside_frame`: joint lies beyond the frame and receives no pixel coordinate.
- `uncertain`: visible evidence is insufficient for a reliable point.

Cadence:

- Baseline pose: 10 fps through active rallies.
- Contact windows: every 50 fps frame from 10 frames before through 10 frames after each contact.
- Jump actions: every frame from final two approach steps through stable landing.
- Pose at every contact receives independent review.

## Ball labels

One ball-state record is required for every frame between rally start and end:

- `visible`: mark the centre of the ball; record radius when its boundary is discernible.
- `occluded`: ball expected in the frame but hidden; do not fabricate a centre.
- `outside_frame`: explicitly outside the image.
- `uncertain`: candidate exists but cannot be confirmed.

Motion blur, truncation and visibility are separate fields. The 2D centre is preferred to an unstable tiny box. A model-assisted point becomes ground truth only after human review.

## Contact labels

Every physical touch receives a contiguous `contact_index`, exact frame, actor track, team, action type, contact surface and quality. `transition` is a phase and cannot be used as a contact.

**Contact point convention (added 2026-08-31)**: the frame corresponds to the exact instant of contact, but the *spatial* point recorded for homography purposes is the **ground projection directly beneath the contact/player**, never the ball's own aerial position. A homography transforms points on one plane (the court floor); it cannot correctly place a ball 1-3 m in the air just because a matrix exists. This mirrors OpenVolley/ovscout2's own click-scouting convention (click the floor point under the ball, not the ball itself). In `volley_domain.annotation.BallContactAnnotation` this is `contact_ground_pixel` -- a **separate, optional** field from `ball_center_pixel` (the ball's own real visible position, required, unchanged). Never conflate them, and never overwrite `ball_center_pixel` with a ground-projected value: `ball_center_pixel` stays the ball's real position for every contact frame; `contact_ground_pixel` is filled in only when a confident floor point can be estimated, and is what any court-plane math for this contact must actually use.

The contact frame is the frame with the best combined evidence of minimum ball–body distance, ball deformation or direction/velocity change. If two frames are indistinguishable, mark uncertainty and send the contact to adjudication rather than choosing arbitrarily.

Valid contact actions are serve, reception, set, attack, tip, block, dig and free ball. Block touches do not consume one of the team's three counted contacts. Complete rallies must begin with a serve and obey the three-contact rule.

For setters, attackers and blockers, contact windows must support:

- Contact/release height.
- Incoming and outgoing ball velocity.
- Set target and distribution zone.
- Attack takeoff, contact and landing frames.
- Block takeoff, maximum reach and landing frames.

## Block participation (`BlockAttempt`)

A blocker can be tactically committed to a block -- jumped, positioned, read or committed -- without ever touching the ball. Counting only ball contacts loses roughly half of real defensive block information. `volley_domain.ontology.BlockAttempt` (added 2026-08-31) records this separately from `Action(action_type=block)`: `block_mode` (`read`/`commit`/`swing`/`unknown`), `block_role` (`solo`/`left`/`middle`/`right`/`assist`/`unknown`), and `jumped`. When the blocker also touched the ball, both rows exist for the same event -- the `BlockAttempt` for tactical participation, an `Action(action_type=block)` for the contact itself, linked via `BlockAttempt.action_id`.

`block_mode=commit` requires the blocker's *intent* to be reasonably determinable from the footage, not just early movement -- a central moving early is not, by itself, evidence of `commit` versus `read`. When intent cannot be determined, use `unknown`; do not guess. `block_count`, seam width and distance-to-attacker are derived from multiple `BlockAttempt` rows plus player positions -- never annotated directly, matching this protocol's "annotate the fact, derive the feature" rule (see docs/domain/ONTOLOGY.md).

## Rally boundaries and outcomes

- Start: server initiates the service action, with the exact serve contact stored separately.
- End: first frame after the terminal ball contact/outcome is unambiguous.
- Store set/rally index, score before the rally, serving team and point winner.
- Timeouts, substitutions, warm-ups and empty-court transitions are negative segments, not rallies.
- This is the *within-clip* rule. The *clip-selection* counterpart -- catching a whole candidate segment that is mostly warm-up, ceremony or court cleaning before it ever reaches annotation -- is `dataset_factory.visual_qa`'s controlled rejection vocabulary (`warmup`, `pregame_ceremony`, `court_cleaning_or_maintenance`, `timeout_or_stoppage`, `celebration_or_dead_time`, `camera_transition_or_broadcast_cutaway`, `low_active_play_density`), checked against every accepted/rejected clip in `VISUAL_QA.json`. Use the named category, not free text -- `reason="other"` requires a substantive explanation and is not a shortcut past picking a real one.

## 2D/3D trajectory and speed

Split the trajectory at every contact. Each free-flight segment is fitted and evaluated separately; no smoother may cross a contact discontinuity. Every point retains `observed`, `interpolated` or `predicted` provenance.

- 2D trajectory is always retained in source pixels and court-plane projection where valid.
- Monocular height/speed uses calibrated physics or ball-size priors and carries axis-specific uncertainty.
- Reference 3D uses synchronized views and triangulation, with per-point reprojection error.
- A metric is suppressed when calibration, visibility or uncertainty thresholds fail.

## Biomechanical phases and metrics

Biomechanics remains separate from tactical match analysis. Required phases are approach, takeoff, contact/block and landing. Candidate metrics include jump/contact/reach height, approach speed, takeoff velocity, knee flexion, trunk inclination, shoulder abduction, elbow extension, arm-swing angular velocity, hip–shoulder separation and 2D landing asymmetry.

Single-camera footage may produce image-plane angles and clearly labelled estimates. It must not claim clinical-grade 3D kinematics, forces, loads, diagnosis or injury prediction.

Every metric stores value, unit, uncertainty, confidence, measurement mode, supporting frames and abstention reason where applicable.

## Review and acceptance gates

- At every fifth frame from rally start, plus the rally end frame, exactly 12 boxes must carry `person_role=on_court_player`; officials, staff, spectators and substitutes are labelled separately.
- A training export may contain only reviewed labels. Detection, pose and ball use independent image catalogs so an incompletely labelled image can never be interpreted as a negative for another signal.

- All tasks receive a second-pass review.
- Every court calibration and contact frame is double-reviewed.
- At least 20% of all other labels are independently double-annotated to measure agreement.
- Ball coverage during live rallies must be at least 98% including explicit occlusion/outside states.
- Every contact must link to an exact-frame ball record and exact-frame actor pose.
- Critical contact pose coverage must be at least 95%.
- No duplicate frame labels, source-match leakage, impossible contact order or invalid coordinate units.
- Train/validation/test is frozen by complete source match before annotation begins.

The dataset version is promoted only when the automated report passes and all adjudication queues are empty. “Model-assisted” never means “automatically trusted.”
