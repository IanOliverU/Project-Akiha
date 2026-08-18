# Project Akiha — Pet Animation & Interaction Architecture

## Purpose

This document defines the planned animation and interaction architecture for Project Akiha's desktop-pet system.

The goal is to make Akiha feel like a living desktop companion rather than a static animated sprite. The system should support idle behavior, walking, sleeping, waking, reactions, interaction animations, voice reactions, and future simulation-driven behavior without coupling animation logic to the AI provider.

This design is inspired by the interaction depth and animation organization found in VPet, while keeping Akiha's architecture native to Python/PySide6.

VPet demonstrates useful patterns including separation of core logic, rendering, UI, and tooling; dedicated animation management; interaction-specific animations; and start/loop/end animation segments. citeturn0search0turn0search1turn0search2

Reference:
- VPet repository: https://github.com/LorisYounger/VPet
- VPet English README: https://github.com/LorisYounger/VPet/blob/main/README_en.md

---

## 1. Canonical Asset Rule

### `assets/animations/akiha/standing/000.png` is the source of truth.

This is a hard rule.

`000.png` is the original Akiha mascot sprite and must remain visually unchanged.

Animation generation must not silently redesign, redraw, recolor, rescale, blur, interpolate, or otherwise alter the character.

The following must remain consistent unless a future artist-approved asset explicitly replaces the canonical artwork:

- Character design
- Face
- Hair
- Clothing
- Body proportions
- Colors
- Shading
- Outline
- Palette
- Transparency
- Pixel-art style

Animation exists to bring the character to life, **not to create a different interpretation of Akiha**.

If additional frames are required, they must be created from approved artwork or carefully controlled transformations. AI-generated artwork must never automatically become the new canonical design.

---

# 2. Design Goals

The animation system should:

1. Make Akiha feel alive while idle.
2. Make movement visually readable and smooth.
3. Support sleeping and waking transitions.
4. Support interaction reactions.
5. Connect voice playback to visual behavior.
6. Allow mood and activity systems to influence animation.
7. Keep animation independent from AI providers.
8. Avoid dialogue-string-driven animation logic.
9. Allow new animations to be added without rewriting the pet controller.
10. Support different FPS and durations for different animations.
11. Provide deterministic playback for testing.
12. Leave room for future Live2D, Spine, or 3D rendering.

---

# 3. Animation Categories

## 3.1 Idle

Idle is the default state when Akiha has no higher-priority behavior.

Potential variants:

- Normal breathing
- Blinking
- Looking around
- Small posture shift
- Subtle head movement
- Stretching
- Randomized idle variation

Instead of one endlessly repeating loop:

```text
Idle -> Idle -> Idle -> Idle
```

the system should eventually support:

```text
Idle
 ├── IdleNormal
 ├── IdleBlink
 ├── IdleLookAround
 ├── IdleShiftWeight
 └── IdleStretch
```

Until proper artist-created frames exist, idle animation should favor controlled, deterministic transformations and preserve the canonical artwork.

---

# 4. Walking

The current walking animation is weak because the existing sprite sheet has roughly one visual frame per second.

Increasing playback FPS alone will not solve this.

A real walking animation needs additional visual poses.

A basic cycle can follow:

```text
Contact
   ↓
Down
   ↓
Passing
   ↓
Up
   ↓
Contact
```

### Recommended initial target

- 8–12 visual frames per cycle
- Approximately 12–24 animation FPS
- Left/right orientation handled independently
- Movement speed separated from animation playback
- No arbitrary stretching
- No unintended rescaling

The exact frame count should be determined by the artwork.

### Important separation

Walking animation and walking movement are separate systems:

```text
WalkingAnimation
      ↓
Visual frame

MovementController
      ↓
Screen position
```

The animation determines **how Akiha looks while walking**.

The movement system determines **where Akiha moves**.

---

# 5. Sleeping

Sleeping should be a proper state instead of simply freezing idle.

Recommended structure:

```text
Idle
  ↓
SleepStart
  ↓
SleepLoop
```

### SleepStart

A short transition:

- Movement slows
- Eyes close
- Head/body lowers
- Akiha settles
- Final transition frame

### SleepLoop

A low-frequency loop:

- Eyes closed
- Very subtle breathing
- Occasional small movement
- Low rendering/animation cost

---

# 6. Waking Up

Waking should be a transition out of sleep:

```text
SleepLoop
   ↓
WakeStart
   ↓
Idle
```

Possible sequence:

1. Small movement
2. Eyes open
3. Head/body rises
4. Brief stretch
5. Return to idle

This should feel like a continuation of the sleeping state rather than an instantaneous sprite swap.

---

# 7. Speaking / Voice Animation

Akiha now has voice synthesis, so voice playback should produce animation events.

Architecture:

```text
Dialogue
   ↓
Voice Service
   ├──→ Audio Playback
   └──→ VoiceAnimationEvent
              ↓
       Animation Controller
```

Potential states:

- SpeakingNeutral
- SpeakingHappy
- SpeakingSad
- SpeakingAngry
- SpeakingSurprised

The first implementation can be simple.

For example:

```text
MouthClosed
MouthOpen
MouthClosed
MouthOpen
```

However, facial animation should only be introduced when approved artwork supports it without altering Akiha's canonical design.

The voice provider should never need to know how the renderer works.

---

# 8. Interaction Animations

Akiha should eventually have dedicated reactions to user interaction.

Examples:

- Head petting
- Body clicking
- Attention
- Surprise
- Happiness
- Annoyance
- Confusion

Use typed interaction events:

```python
PetInteractionEvent(
    interaction_type="head_petted"
)
```

rather than dialogue text:

```python
handle_text("user clicked Akiha's head")
```

This keeps interaction logic independent from language and AI providers.

---

# 9. Mood-Reactive Animation

Akiha already has a mood system.

Animation should **consume mood**, not determine it.

```text
MoodService
    ↓
MoodChanged
    ↓
AnimationPolicy
    ↓
AnimationController
```

Possible moods:

- Calm
- Attentive
- Happy
- Curious
- Sleepy
- Sad
- Frustrated
- Excited
- Resting
- CheckingIn

Mood should influence animation selection without directly changing pet-state rules.

---

# 10. Animation Priority

Multiple systems may request animations simultaneously.

Example:

- Akiha is idle.
- User pets her.
- A proactive check-in fires.
- Voice starts.

Therefore animation requests need predictable priority.

Example priority model:

```text
100  Critical/system transition
90   Direct interaction
80   Voice reaction
70   Mood reaction
50   Walking
20   Idle variation
10   Background visual effect
```

The exact numbers are implementation details.

The important rule is:

> Important animations must not be randomly interrupted by lower-priority animations.

---

# 11. Start / Loop / End Model

A useful concept to borrow from VPet is:

```text
START
LOOP
END
```

For example:

```text
sleep_start
sleep_loop
sleep_end

pet_start
pet_loop
pet_end

wave_start
wave_loop
wave_end
```

This allows natural transitions:

```text
Idle
  ↓
SleepStart
  ↓
SleepLoop
  ↓
WakeStart
  ↓
Idle
```

rather than abruptly switching between unrelated sprites.

VPet's own animation metadata includes single animations and start/loop/end structures, along with categories such as idle, movement, sleep, speaking, touch interactions, and startup/shutdown. citeturn0search2turn0search10

---

# 12. Animation Manifest

Animation metadata should remain outside Python code.

Example:

```toml
[idle]
type = "loop"
fps = 30
frames = [
    "000.png",
    "001.png",
    "002.png"
]

[walk]
type = "loop"
fps = 18
frames = [
    "000.png",
    "001.png",
    "002.png",
    "003.png"
]

[sleep_start]
type = "sequence"
fps = 12
frames = [
    "000.png",
    "001.png",
    "002.png"
]

[sleep_loop]
type = "loop"
fps = 8
frames = [
    "000.png",
    "001.png"
]

[wake_start]
type = "sequence"
fps = 12
frames = [
    "000.png",
    "001.png",
    "002.png"
]
```

Actual frame names and FPS values should be determined after testing the artwork.

---

# 13. Proposed Architecture

```text
                  Pet State
                     |
                     v
              Pet State Service
                     |
                     v
              Pet State Changed
                     |
            +--------+--------+
            |                 |
            v                 v
          Mood             Behavior
            |                 |
            +--------+--------+
                     |
                     v
              Animation Policy
                     |
                     v
            Animation Controller
                     |
              +------+------+
              |             |
              v             v
        Frame Player   Animation Events
              |             |
              v             v
           Renderer        Voice
```

Core principle:

> Pet state determines what Akiha is allowed or expected to do. Animation determines how that state is visually expressed.

---

# 14. Proposed Module Structure

```text
project_akiha/
  core/
    animation/
      models.py
      states.py
      requests.py
      priorities.py
      transitions.py
      manifest.py
      policy.py

  services/
    animation.py
    animation_policy.py

  app/
    animation_controller.py
    pet_reaction_controller.py

  ui/
    pet_window.py

  assets/
    animations/
      akiha/
        standing/
          000.png
        idle/
        walk/
        sleep/
        wake/
        reactions/
        speaking/
```

The exact structure should be adapted to the existing Project Akiha codebase instead of creating duplicate abstractions.

---

# 15. Animation State Machine

Example:

```text
                    +----------+
                    |   Idle   |
                    +----+-----+
                         |
            +------------+------------+
            |            |            |
            v            v            v
         Walking      Sleeping     Speaking
            |            |            |
            v            v            v
         WalkLoop    SleepLoop    SpeakLoop
                         |
                         v
                       WakeUp
                         |
                         v
                        Idle
```

Interaction animations temporarily override lower-priority states:

```text
Idle
  ↓
PetReaction
  ↓
Idle
```

---

# 16. Randomized Idle Behavior

Akiha should eventually have multiple idle variants.

The system can select a variant based on:

- Mood
- Pet state
- Time since interaction
- Activity state
- Whether Akiha is speaking
- Whether a proactive action is pending

Randomness should remain bounded and deterministic enough for testing.

---

# 17. Renderer FPS vs Animation FPS

The renderer does not need to run at the same FPS as every animation.

Example:

```text
Renderer:       60 FPS
Idle animation: 30 FPS
Walking:        24 FPS
Sleeping:        8 FPS
UI updates:     event-driven
```

A 60 FPS renderer can display a 30 FPS animation smoothly without requiring every animation to contain 60 unique frames.

This is especially important for pixel-art animation: duplicate frames are preferable to inventing unnecessary visual changes.

---

# 18. Voice + Animation Synchronization

Voice playback can emit:

```text
VoiceStarted
VoicePaused
VoiceFinished
```

The animation controller can respond:

```text
VoiceStarted
    ↓
SpeakingAnimation

VoicePaused
    ↓
Pause/hold current speaking state

VoiceFinished
    ↓
Return to previous state
```

This keeps GPT, Gemini, Claude, OpenAI TTS, GPT-SoVITS, and future voice providers interchangeable.

---

# 19. Future Rendering Options

The current sprite renderer should remain the foundation.

Possible future rendering implementations include:

### Sprite animation

Current approach.

Advantages:

- Simple
- Predictable
- Low resource usage
- Easy to package
- Good for pixel art

### Live2D

Possible future upgrade for:

- Facial expressions
- Eye movement
- Mouth movement
- Hair movement
- Body deformation

VPet itself has a separate Live2D animation component, illustrating that richer rendering can be introduced as a separate component rather than forcing the entire application to use Live2D. citeturn0search7

### 3D

A future 3D model can become another renderer while the pet-state, behavior, assistant, and animation-policy layers remain intact.

---

# 20. What NOT To Do

## Do not let the AI directly select arbitrary animation files

Bad:

```text
LLM → "play ../../something.png"
```

Good:

```text
LLM / Behavior
       ↓
Typed event/intent
       ↓
Animation Policy
       ↓
Known animation ID
       ↓
Animation Controller
```

## Do not let dialogue strings control animation

Bad:

```python
if "happy" in response:
    play_animation(...)
```

Good:

```text
MoodChanged(HAPPY)
        ↓
AnimationPolicy
```

## Do not modify the canonical sprite automatically

`000.png` remains protected.

## Do not make every subsystem responsible for animation

There should be one animation orchestration layer.

---

# 21. Recommended Implementation Order

## Stage 1 — Stabilize Idle

- Protect `000.png`.
- Preserve the canonical palette.
- Prevent accidental scaling/filtering.
- Verify transparency and dimensions.
- Establish deterministic playback.
- Add visual regression checks.

## Stage 2 — Improve Walking

- Create a real multi-frame walking cycle.
- Add left/right handling.
- Separate animation FPS from movement speed.
- Add movement transitions.
- Test screen-bound movement.

## Stage 3 — Sleeping

Implement:

```text
SleepStart
SleepLoop
WakeStart
```

Integrate with pet-state and activity systems.

## Stage 4 — Reactions

Add:

- Petting
- Clicking
- Attention
- Surprise
- Happy reaction
- Sad/frustrated reaction

## Stage 5 — Speaking

Connect voice playback events to simple speaking animations.

## Stage 6 — Mood

Allow the existing mood system to influence animation selection.

## Stage 7 — Animation Variants

Add multiple idle variants and contextual behaviors.

## Stage 8 — Advanced Rendering

Only after the sprite architecture is stable should Akiha consider:

- Live2D
- Spine
- More advanced 2D deformation
- 3D rendering

---

# 22. Testing Requirements

Animation should have automated and visual validation.

Automated checks:

- Asset dimensions
- RGBA format
- Transparency rules
- Canonical palette
- Manifest validity
- Missing frames
- Duplicate frame definitions
- Invalid animation IDs
- Invalid transition targets
- FPS bounds
- State transition validity
- Priority behavior
- Animation requests cannot bypass the controller

Visual checks:

- No blur
- No unintended scaling
- No palette drift
- No character redesign
- No sudden frame jumps
- No broken loops
- Walking direction looks correct
- Sleep/wake transitions look natural

A preview GIF or animation artifact can be generated for manual review.

---

# 23. VPet Inspiration

VPet is useful inspiration because it demonstrates that a desktop pet can have a large animation and interaction vocabulary without putting everything into one UI class.

Useful concepts to borrow:

- Separate core logic from desktop UI.
- Dedicated animation loading/management.
- Explicit animation categories.
- Start/loop/end animation segments.
- Interaction-specific animations.
- Movement-specific animation handling.
- Tooling for animation assets.
- Extensible rendering architecture.
- Ability to support richer animation implementations later.

VPet currently describes a large set of animation/interaction combinations and separates its Windows application, core, graphics, display, and tooling components. citeturn0search0turn0search1

This is **inspiration, not a requirement to copy VPet's implementation**.

---

# 24. Long-Term Goal

The goal is not to create hundreds of animations immediately.

The goal is to build an animation system that can eventually support hundreds of animations without becoming unmaintainable.

The long-term flow should be:

```text
Pet State
   +
Mood
   +
User Interaction
   +
Activity
   +
Voice
   +
Time
   +
Behavior
   |
   v
Animation Policy
   |
   v
Appropriate Animation
```

The architectural separation should remain:

```text
AI Companion
    ↓
What Akiha says / proposes

Pet Simulation
    ↓
Akiha's internal state

Behavior System
    ↓
Whether something should happen

Animation System
    ↓
How Akiha visually expresses it

Renderer
    ↓
How the animation is displayed
```

Each layer should remain replaceable.

---

# 25. Final Principle

Akiha should not become a collection of hard-coded animations.

She should have an actual animation system.

Adding a new animation should ideally require:

```text
New approved asset
       +
Manifest entry
       +
Known animation state
       +
Optional policy rule
```

rather than rewriting the application.

Most importantly:

> **Akiha's original `000.png` sprite remains the visual identity of the character. Animation exists to bring that character to life, not to redesign her.**
