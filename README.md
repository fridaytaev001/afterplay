# Afterplay — an opponent that remembers

A playable, two-player Quoridor-style browser game with Qwen opponent decisions, shared player history across rounds, a four-condition context comparison, and 4/8/32-request inference load tests.

**No fine-tuning is performed.** Adaptation uses saved history in the prompt. The same model weights answer all requests. No new GPU model or server tuning is required.

## Fastest workshop deployment

1. Download and unzip the project ZIP on your laptop.
2. In the workshop JupyterLab file browser, upload the ZIP. Open a Jupyter terminal.
3. Extract and enter the directory:

```bash
python3 -m zipfile -e afterplay.zip .
cd adaptive-quoridor
NAMESPACE=workshop-s21 bash deploy.sh
```

If you uploaded under a different directory, first `cd` to that directory. The script uses the workshop terminal's existing Kubernetes configuration. It creates a new ConfigMap, Deployment and Service. It does not attempt NetworkPolicy changes under the student role. It does not edit `manifests/vllm.yaml`, replace `sa-agent`, or request another GPU.

4. On your Windows laptop, open PowerShell:

```powershell
Set-Location "$HOME\Downloads"
.\kubectl.exe --kubeconfig ".\s21.yaml" --namespace workshop-s21 port-forward svc/afterplay 8080:8080
```

Use `kubectl` instead of `.\kubectl.exe` if it is on PATH. Adjust the paths if your kubeconfig or kubectl is elsewhere. Leave this window open.

5. Open **http://localhost:8080** on that same laptop.

This route connects the game service directly to `http://vllm:8000/v1` inside your namespace; your separate vLLM port-forward on port 8000 is not needed for this route. The game automatically discovers the served model ID.

## Alternative: run the app on your laptop

Requires Python 3.10+. No pip packages.

Keep your existing Qwen port-forward running:

```powershell
.\kubectl.exe --kubeconfig ".\s21.yaml" --namespace workshop-s21 port-forward svc/vllm 8000:8000
```

In a second PowerShell window, enter the extracted project folder:

```powershell
$env:VLLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:PORT = "8080"
python app.py
```

Use `py -3 app.py` if your Windows Python launcher is `py`. Open http://localhost:8080. No API key or kubeconfig is sent to your browser. Set MODEL_NAME only if automatic discovery is unsuitable.

For offline practice:

```powershell
$env:OFFLINE = "1"
python app.py
```

Offline mode uses a CPU shortest-path opponent. It **does not** use the GPU or demonstrate history adaptation. Remove the variable and restart to reconnect Qwen:

```powershell
Remove-Item Env:OFFLINE
python app.py
```

## Playing and saving history

- Your teal pawn starts at the bottom and wins by reaching the top. The coral opponent has the opposite goal.
- On a turn, move to a highlighted square or choose a wall orientation and click a glowing intersection.
- The server validates legal moves, jumps, diagonal jumps, overlapping/crossing walls, remaining wall count and a remaining route for each player.
- Finished matches are saved automatically.
- **Save & restart** explicitly saves an unfinished round; its history is labeled unfinished.
- **New match** discards an unfinished match while keeping previously saved rounds.
- History is per browser session, stored server-side in SQLite. The latest 12 rounds are kept. The comparison uses the two latest saved rounds, called Round 1 and Round 2.
- Closing the browser can end its session cookie. History on a laptop persists in the SQLite file; the Kubernetes example uses emptyDir, so pod replacement erases it. For a longer-lived deployment, mount a namespace PVC at /data instead.
- The model sees only prior saved rounds, not the unsaved current-round action trace. The current board is always supplied.

## The four-context experiment

Click **Compare decisions** on a nonterminal board.

Four concurrent requests use the same board, candidate shortlist, model, seed, temperature and token cap:
1. No history.
2. Recent Round 1.
3. Recent Round 2.
4. Both recent rounds.

If it is your turn, the panel considers a hypothetical opponent turn on the current board. Recommendations do not apply a move. Highlighting a recommendation overlays it on the board.

With no saved rounds, all conditions have no history. With one saved round, Round 2 has none and Both matches Round 1. Collect two rounds before interpreting differences.

Candidates are shortlisted using CPU path calculations without consulting history. All legal pawn moves and the six top-scored legal wall placements are presented. Qwen chooses the candidate; code executes it. This limits the action space and may exclude a move that would be best for exploiting a habit. It is a prototype, not a championship-strength solver.

**Different recommendations are not proof that memory improves performance.** Compare against the no-history model and CPU baseline across many independent matches, using the same starting positions and controlled opponent policies. A fixed replay can be useful for a demonstration, but may become illegal after alternative wall placements; use a legal policy for outcome evaluation. No win-rate results are fabricated in this version.

## GPU load test

Choose 4, 8 or 32 and click **Run benchmark**. The backend sends concurrent Qwen decisions from independent synthetic board positions. It reports:
- Successful and failed requests.
- Decisions per second.
- Output tokens per second, when the endpoint reports usage.
- Median and p95 total decision latency.
- Sampled peak running requests and KV cache use, when vLLM metrics are accessible.

It does not measure TTFT, GPU compute utilization or actual match outcomes. Requests have varying prompt lengths; compare repeated runs of the same level/workload after warm-up. Prefix caching may contribute to performance, so do not attribute all speedup solely to batching.

Thirty-two is a load-test concurrency level, not 32 GPUs or model copies. One vLLM model answers separate request contexts. The existing max-num-seqs cap may queue excess work. This project does not change it.

## Configuration

| Variable | Default |
|---|---|
| VLLM_BASE_URL | http://127.0.0.1:8000/v1 |
| MODEL_NAME | Auto-discover from /v1/models |
| VLLM_API_KEY | not-needed |
| MODEL_TIMEOUT | 60 seconds per model HTTP request |
| OFFLINE | 0 |
| HOST | 127.0.0.1 (Kubernetes manifest sets 0.0.0.0) |
| PORT | 8080 |
| DATA_PATH | data/game.sqlite |

The Qwen request uses non-thinking mode and vLLM structured JSON output. Failed or invalid model output is shown as an error; it never silently switches to the offline bot. Candidate legality is checked again before applying.

## Troubleshooting

**Disconnected:** Check the vLLM service/pod and your forwarding window.

```bash
kubectl -n workshop-s21 get pods
kubectl -n workshop-s21 logs deploy/afterplay --tail=80
kubectl -n workshop-s21 logs deploy/vllm --tail=80
```

**HTTP 400 from Qwen:** The request expects the workshop's Qwen3/vLLM structured-output and chat-template support. Check server logs and version before changing the request.

**Model traffic blocked:** The student deployment does not change network policies. If the existing rules block Afterplay from reaching vLLM, ask an organizer to review organizer-networkpolicy.yaml. Only an organizer with appropriate permissions should apply it. The laptop route still works through the existing vLLM port-forward.

**Port 8080 busy:** Use `port-forward svc/afterplay 18080:8080` and open http://localhost:18080.

**Request timeout:** Start with 4 requests, check server load, then optionally raise MODEL_TIMEOUT and redeploy/restart. Do not change GPU reservation or scheduler settings without a measured baseline.

**After code changes:** Run deploy.sh again. This updates the code ConfigMap and restarts only Afterplay. Saved cluster history is erased by the pod restart.

## Verification

```bash
python -m unittest discover -s tests -v
node --check app.js
```

Tests cover game rules and a mock OpenAI-compatible endpoint. Mock inference is not real GPU validation. Test the actual Qwen connection after deployment, make one move, run the four-context comparison, then try the 4-request benchmark.

## Scope and demo

This project is inspired by Quoridor; it is not affiliated with Gigamic. It uses original interface graphics.

Suggested demo:
1. Play/save two rounds with visibly different route choices.
2. Start a third match and compare the four memories.
3. Highlight the recommendations and explain why histories may help or mislead.
4. Run the 4-request benchmark, then 8/32 if time allows.
5. Explain: rules/path checks run on CPU; Qwen decisions run on the workshop GPU.

There is no video model, full self-play tournament or training job in this first version.

If Python is available only inside the notebook kernel, extract the ZIP using Python zipfile there and run deploy.sh via subprocess. Rename opaque download filenames to afterplay.zip before using the examples.
