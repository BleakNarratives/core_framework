# core_framework/design/VERTICAL_AI_ORIGINAL_VISION.md

## Original Vertical AI Architecture (Preserved Intent)

### The Pipeline

```
USER INPUT (idea/plan/codebase decision)
    │
    ▼
BOARDROOM ─── 8 personas argue merits, find flaws, vote
    │
    ▼ (if passes sniff test)
TRACKS ──── Multiple strategic plans generated
    │
    ▼
FRACTAL SIMULATOR ──── Ultra-realistic market response chains
    │                      tracks × iterations
    ▼
GENETIC ARENA ──── Score, eliminate, breed, mutate
    │                 strongest genes preserved
    ▼
CHAMPION TRACK ──── Best mutated roadmap
    │
    ▼
CODE CITY ARENA ──── Head-to-head combat or breading
                       for genetic mutations based on
                       simulated market responses
```

### Key Concepts

1. **Tracks**: Strategic plans/roadmaps for a codebase or business idea
2. **Sniff Test**: Boardroom consensus — if the idea survives the personalities, it becomes tracks
3. **Fractal Simulation**: Each track is run through market response iterations (competitors, customers, regulators)
4. **Genetic Arena**: Tracks are scored on fitness, top performers breed, mutations introduced
5. **Code City Arena**: Winner rendered as buildings in Code City, or used for head-to-head implementation battles

### Canonical Components (untouched)

| Component | Location |
|-----------|----------|
| Boardroom | `The-Werkz/Official-Vertical-AI-Boardroom/core/boardroom.py` |
| Simulator | `The-Werkz/Official-Vertical-AI-Boardroom/core/simulator.py` |
| Genetics | `The-Werkz/Official-Vertical-AI-Boardroom/core/genetics.py` |
| Mutation | `The-Werkz/Official-Vertical-AI-Boardroom/core/mutation_engine.py` |
| State | `The-Werkz/Official-Vertical-AI-Boardroom/core/state.py` |
| Arena | `Code-City-Apocalypse/src/buildings/arena.py` |
| Router | `The-Werkz/Official-Vertical-AI-Boardroom/core/router.py` |

### Current Drift Notes

- Vertical AI has accumulated business scouting/outreach features (CFPB, Google Business, etc.)
- The Code City Arena exists as a standalone PvP coding challenge system
- The genetic arena winner does NOT currently feed into Code City visualization
- The "tracks" concept exists but isn't connected to actual code generation

### Restoration Path

To restore original intent without destroying current work:
1. Keep boardroom, simulator, genetics, mutation_engine as-is
2. Add a `pipeline.py` that connects: boardroom → simulator → genetics → arena
3. Add Code City integration: champion track → buildings in Code City
4. Keep all scouts/outreach as optional sidecars
