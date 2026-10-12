# Verification
- 20 automated tests pass.
- Rules covered: legal pawn movement, jumps, diagonal jumps, wall crossings/overlap, wall resources, remaining routes, winning, and rejection after game over.
- API covered: session isolation, board revisions, model ID discovery, invalid model output without applying a move, offline labeling, and same-origin handling.
- Four-context requests use identical boards and shortlists, with history counts 0/1/1/2 after two saved rounds.
- Mock inference completed at concurrency 4, 8, and 32.
- Chromium browser smoke checks pass at desktop 1440px and mobile 390px: moving, wall placement, saving a round, four comparison cards, move overlays, offline benchmark restriction, no horizontal overflow and no JavaScript errors.
- JavaScript syntax, shell syntax, and Kubernetes YAML parsing pass.
- The builder successfully deployed the application in workshop-s21 and reports that gameplay works. Automated tests used mock inference. Independent measurements of live GPU throughput and memory benefit remain unverified.
- No model training is performed, and no claim of stronger gameplay is established.
