# Hardware Trojan Ideas for AES via Google XLS Pass

This document catalogs hardware trojan designs that can be inserted into an AES-128 implementation through a custom Google XLS compiler pass (operating on XLS IR before codegen). All trojans are designed to be **detectable via power trace analysis** (SPA, DPA, CPA, or statistical methods).

---

## Background

### XLS Pass Insertion Point
A custom XLS pass operates on the IR graph (`xls::Package` / `xls::Function`). It can:
- Add new IR nodes (AND, OR, XOR, Select, gates)
- Modify existing node operands
- Insert conditional logic (sel/mux nodes)
- Add state elements (for sequential trojans)
- Modify the pipeline schedule

### Power Trace Detection Principle
Every active gate transition dissipates dynamic power proportional to the Hamming weight/distance of switching activity. Trojans that alter the computation create **measurable deviations** in the power profile compared to a clean reference. Detection methods include:
- **SPA** (Simple Power Analysis): visual inspection of trace shape
- **DPA** (Differential Power Analysis): statistical correlation with data
- **CPA** (Correlation Power Analysis): correlation with hypothetical power models
- **t-test** (TVLA): leakage detection without knowing the key
- **Template attacks**: matching against known trojan power signatures
- **Anomaly detection**: ML-based deviation from golden reference traces

---

## Category 1: S-Box Modification Trojans

These trojans modify the SubBytes operation. Since the S-box is the primary nonlinear element and the most power-hungry part of AES, even small changes create detectable power signatures.

### 1. Single S-Box Entry Swap
**XLS Pass**: Modify one entry in the S-box lookup table constant (`literal_41315`).
**Effect**: One specific byte value produces an incorrect substitution.
**Detection**: CPA on SubBytes output; the incorrect entry creates a correlation anomaly at specific Hamming weights. T-test with chosen plaintexts targeting the modified entry shows leakage deviation.

### 2. S-Box Identity Bypass (Triggered)
**XLS Pass**: Insert a `sel` node that bypasses the S-box lookup (outputs the input unchanged) when a rare trigger condition is met (e.g., specific plaintext byte = 0xAB).
**Effect**: SubBytes becomes identity for one byte under trigger.
**Detection**: SPA shows reduced switching activity during triggered encryptions (S-box lookup power disappears for one byte). DPA correlation drops for the affected byte position.

### 3. S-Box Affine Transform Removal
**XLS Pass**: Remove the affine transformation from the S-box, leaving only the GF(2^8) inversion.
**Effect**: Weakened S-box that is still nonlinear but cryptographically weaker.
**Detection**: CPA with a model based on GF(2^8) inversion (without affine) correlates better than the standard S-box model, revealing the modification.

### 4. Dual S-Box (Weak Alternate)
**XLS Pass**: Add a second, weaker S-box table and a `sel` mux controlled by a trigger bit. When triggered, the weak S-box is used.
**Effect**: Weakened encryption under trigger.
**Detection**: The mux adds extra gate transitions visible in SPA. The weak S-box has a different Hamming weight distribution, detectable via DPA.

### 5. S-Box Output Bit Flip
**XLS Pass**: XOR the MSB of one S-box output byte with a trigger signal.
**Effect**: Flips one bit of SubBytes output when triggered.
**Detection**: The XOR gate adds a switching event visible in SPA. CPA on the affected byte shows anomalous correlation for the flipped bit.

### 6. S-Box Output Truncation
**XLS Pass**: Force the LSB of all S-box outputs to zero.
**Effect**: Reduces S-box output entropy by 1 bit per byte (8 bits total per round).
**Detection**: Hamming weight distribution of S-box output shifts downward. DPA with bit-0 model shows zero correlation (always 0).

### 7. S-Box Delay Trojan
**XLS Pass**: Add a chain of buffer nodes (identity operations) to one S-box path, creating a timing/power signature.
**Effect**: Functionally correct but one S-box path has increased switching activity from extra gates.
**Detection**: SPA shows an extra power peak in the S-box computation window. The peak correlates with the input to the affected S-box byte.

### 8. Round-Dependent S-Box
**XLS Pass**: Insert a round counter and modify the S-box behavior in specific rounds (e.g., round 9 uses a different table).
**Effect**: Only the final round is weakened, making functional testing harder.
**Detection**: Comparing power traces of different rounds reveals the modified round has a different power profile.

---

## Category 2: Key Leakage Trojans

These trojans leak key information through the power side channel, making key extraction trivial.

### 9. Key XOR into Data Path
**XLS Pass**: Add an extra XOR of a key byte with the S-box output, creating a redundant data-dependent operation.
**Effect**: Extra key-dependent switching activity that doesn't affect output (XORed twice cancels out) but leaks key via power.
**Detection**: CPA with key byte hypothesis shows unexpectedly high correlation at the extra XOR location.

### 10. Key-Dependent Dummy Toggle Register
**XLS Pass**: Add a register that toggles based on key bits. Each clock cycle, the register flips according to `key[cycle_count % 128]`.
**Effect**: No functional impact but key bits are directly encoded in switching activity.
**Detection**: SPA directly reveals key bits as high/low power in consecutive cycles.

### 11. Key Bit Serialization on Unused Wire
**XLS Pass**: Route key bits one-by-one to a dummy flip-flop chain that is synthesized but not connected to outputs.
**Effect**: Key bits appear as sequential power pulses.
**Detection**: SPA shows a clear 128-bit serial pattern during key schedule computation.

### 12. Hamming Weight Key Encoding
**XLS Pass**: Add a small circuit that computes the Hamming weight of each key byte and drives that many toggle flip-flops.
**Effect**: Power consumption directly encodes key byte Hamming weight.
**Detection**: Simple power measurement per round correlates linearly with key byte HW.

### 13. Key Schedule Amplification
**XLS Pass**: Duplicate the key schedule XOR tree, adding redundant computation that amplifies key-dependent power.
**Effect**: Key schedule operations consume 2x power, making DPA on key schedule bytes much easier.
**Detection**: CPA on key schedule intermediate values shows anomalously high SNR.

### 14. Key-Modulated Oscillator
**XLS Pass**: Add a ring oscillator (chain of inverters) whose enable signal depends on key bits.
**Effect**: Power spectrum contains a frequency component modulated by key data.
**Detection**: Frequency-domain analysis (FFT of power trace) reveals key-dependent spectral peaks.

### 15. Key Leakage via AddRoundKey Amplification
**XLS Pass**: After each AddRoundKey, add a redundant register that stores the XOR result and then XORs it again with the key (creating extra transitions).
**Effect**: Doubles the key-dependent switching in AddRoundKey.
**Detection**: CPA correlation at AddRoundKey is approximately 2x the expected value.

### 16. Subkey Register Shadowing
**XLS Pass**: Duplicate each round key register. The shadow register transitions simultaneously, doubling switching activity.
**Effect**: Each subkey load creates 2x the power signature.
**Detection**: Power peaks at key schedule points are 2x normal amplitude.

---

## Category 3: Round Manipulation Trojans

These trojans alter the number of AES rounds or skip operations within rounds.

### 17. Round Skip (Triggered)
**XLS Pass**: Insert a `sel` node in the round loop that skips one round (passes state through unchanged) when a specific 16-bit plaintext pattern is detected.
**Effect**: 9 rounds instead of 10 under trigger — dramatically weakens security.
**Detection**: SPA clearly shows one fewer power peak (missing round). Trace length/shape changes measurably.

### 18. Final Round Bypass
**XLS Pass**: The last round's SubBytes is bypassed (identity), making the output the MixColumns result.
**Effect**: Last round lacks nonlinearity; standard DPA attack becomes trivial.
**Detection**: CPA model using MixColumns output (instead of S-box output) correlates better, revealing the bypass.

### 19. Double Final Round
**XLS Pass**: Execute the final round twice, but the second execution's output overwrites with a weaker version.
**Effect**: Extra round with no MixColumns is applied, but using the same subkey — weakens the cipher.
**Detection**: SPA shows 11 round-shaped power peaks instead of 10.

### 20. First Round Replay
**XLS Pass**: Add logic to store the first round's intermediate state and replay it during round 5.
**Effect**: Rounds 5–10 operate on round-1 state — cipher output is predictable.
**Detection**: Comparing power traces of rounds 1 and 5 shows identical patterns (normally they differ).

### 21. Round Key Reuse
**XLS Pass**: Modify the key schedule to reuse the round-1 key for all rounds.
**Effect**: All rounds use the same subkey — equivalent to a trivially weak cipher.
**Detection**: CPA reveals identical key correlations in every round. Power pattern repeats exactly each round.

### 22. Conditional Round Count Reduction
**XLS Pass**: If `key[0] == 1`, execute only 5 rounds; otherwise, execute 10.
**Effect**: Half the encryptions are dramatically weakened.
**Detection**: Traces have bimodal length distribution. SPA trivially separates 5-round from 10-round traces.

---

## Category 4: MixColumns / ShiftRows Trojans

### 23. MixColumns Bypass (Triggered)
**XLS Pass**: Replace MixColumns with identity when a trigger byte pattern is present.
**Effect**: Missing diffusion in triggered encryptions.
**Detection**: MixColumns is power-intensive (GF multiplications); its absence creates a visible power dip in the round window.

### 24. MixColumns Coefficient Weakening
**XLS Pass**: Change the MixColumns polynomial from `{02, 03, 01, 01}` to `{01, 01, 01, 01}` (simple XOR).
**Effect**: Reduced diffusion — each output byte depends on fewer input bytes.
**Detection**: DPA on individual bytes shows higher correlation (less mixing). Power model with weak MixColumns fits better.

### 25. ShiftRows Disable
**XLS Pass**: Remove ShiftRows permutation (all rows shift by 0).
**Effect**: Columns are independent — AES degenerates to 4 independent 32-bit ciphers.
**Detection**: Cross-column CPA shows zero correlation (no inter-column diffusion). Column-wise power patterns are independent.

### 26. ShiftRows Direction Reversal
**XLS Pass**: Reverse the shift direction (shift right instead of left).
**Effect**: Non-standard permutation; cipher is still complex but not AES-128.
**Detection**: CPA with standard AES model shows degraded correlation in rounds 2+; reversed model correlates better.

### 27. Partial MixColumns (One Column Only)
**XLS Pass**: Only apply MixColumns to column 0; columns 1–3 pass through.
**Effect**: 3/4 of diffusion is missing.
**Detection**: Power trace during MixColumns has ~25% of normal energy. CPA on columns 1–3 shows no mixing.

### 28. MixColumns with Extra Dummy Multiply
**XLS Pass**: Add a redundant GF(2^8) multiply by 0x02 on a state byte, storing result in a dummy register.
**Effect**: Extra power consumption during MixColumns correlates with state data.
**Detection**: CPA with GF multiply model at MixColumns shows anomalous correlation peak.

---

## Category 5: Trigger-Based Trojans (Rare Activation)

### 29. Plaintext Comparator Trigger
**XLS Pass**: Add a 128-bit comparator that checks if plaintext matches a hardcoded value. On match, output a fixed (known) ciphertext.
**Effect**: One specific plaintext always produces a known ciphertext (enables chosen-plaintext attack).
**Detection**: The comparator creates a large simultaneous switching event visible in SPA when the match occurs.

### 30. Counter-Based Time Bomb
**XLS Pass**: Add a 32-bit counter incremented each encryption. After 2^20 encryptions, activate the trojan (e.g., leak key).
**Effect**: Trojan dormant during testing, activates in deployment.
**Detection**: Counter increment adds consistent small power overhead every cycle. After activation, power profile changes dramatically.

### 31. Multi-Byte Trigger (Partial Match)
**XLS Pass**: Trigger when `plaintext[0:3] == 0xDEADBEEF`. On trigger, XOR the key into the ciphertext output.
**Effect**: Key leaked in ciphertext for 1/2^32 of encryptions.
**Detection**: The 32-bit comparator adds switching activity that correlates with input bytes 0–3.

### 32. Sequential Trigger (State Machine)
**XLS Pass**: Implement a 4-state FSM. Each specific plaintext byte in sequence advances the state. After 4 correct sequential inputs, activate trojan.
**Effect**: Extremely rare trigger (requires specific sequence).
**Detection**: FSM registers add consistent switching overhead. State transitions create small but measurable power spikes.

### 33. Key-Based Trigger
**XLS Pass**: Trigger activates when `key[127:120] == 0xFF`.
**Effect**: Trojan only active for 1/256 of possible keys.
**Detection**: The 8-bit comparator on the key byte creates switching correlated with key bits — detectable via CPA on key schedule.

### 34. Temperature/Voltage Trigger (Simulated)
**XLS Pass**: Use a long combinational path as a "delay sensor." If the path resolves differently due to PVT variations, trigger activates.
**Effect**: Trojan activates under specific environmental conditions.
**Detection**: The long combinational path draws extra power and creates a unique timing signature.

### 35. Ciphertext-Feedback Trigger
**XLS Pass**: Store previous ciphertext. Trigger when previous ciphertext XOR current plaintext has HW < 4.
**Effect**: Rare statistical trigger based on data correlation.
**Detection**: The XOR + popcount + comparator circuit adds measurable power overhead every encryption.

---

## Category 6: Information Leakage Trojans (Covert Channels)

### 36. Power Covert Channel — Key Bit Per Encryption
**XLS Pass**: Add a circuit that draws extra current (toggles a large bus) when `key[encryption_count % 128] == 1`.
**Effect**: Key leaked 1 bit per encryption via power consumption.
**Detection**: SPA directly — measure total power per encryption, threshold into 0/1. After 128 measurements, the full key is recovered.

### 37. Power Amplitude Modulation
**XLS Pass**: Add N parallel toggle registers (N = Hamming weight of current key byte being processed). More toggles = more power.
**Effect**: Key byte HW encoded in power amplitude.
**Detection**: Averaging power per round directly reveals key byte Hamming weights.

### 38. Timing Covert Channel via Variable Latency
**XLS Pass**: Insert a variable-delay path (extra pipeline stages) that activates based on key bits.
**Effect**: Encryption takes 1 extra cycle when key bit = 1.
**Detection**: Trace length varies by key — simple timing measurement leaks key.

### 39. Electromagnetic Covert Channel Amplifier
**XLS Pass**: Add a large bus (64+ bits) that toggles key-derived patterns, creating strong EM emanations.
**Effect**: Key bits radiated as EM signals.
**Detection**: Power trace shows large spikes corresponding to bus toggles. EM probe near FPGA picks up key pattern directly.

### 40. S-Box Output Leakage Register
**XLS Pass**: Add a register that captures S-box output of byte 0 in round 1 and holds it (transitions only when value changes).
**Effect**: Leakage register switching directly encodes S-box output.
**Detection**: CPA with round-1 S-box output model shows anomalous correlation outside the normal S-box computation window.

---

## Category 7: Computation Weakening Trojans

### 41. XOR Key with Zero (Key Nullification)
**XLS Pass**: Replace AddRoundKey in round 10 with XOR by zero (state passes through unchanged).
**Effect**: Last round key has no effect; equivalent to a known-key cipher.
**Detection**: CPA on round 10 shows zero correlation with the round key. Power during AddRoundKey in round 10 shows minimal activity.

### 42. State Byte Zeroing
**XLS Pass**: Force `state[15]` (last byte) to zero after round 1.
**Effect**: One byte of state carries no information — reduces keyspace.
**Detection**: DPA on byte 15 shows zero correlation after round 1. Hamming weight of byte 15 is always 0 in rounds 2+.

### 43. Reduce Key Entropy
**XLS Pass**: Force the lower 4 bits of each key byte to zero before key schedule.
**Effect**: Effective key is 64 bits instead of 128.
**Detection**: CPA on key schedule shows zero correlation for LSBs. Power profile of key loading is measurably different (fewer transitions for zero bits).

### 44. Linear Approximation S-Box
**XLS Pass**: Replace S-box with a linear function `S(x) = x XOR 0x63`.
**Effect**: Entire cipher becomes linear — trivially breakable.
**Detection**: The linear S-box has completely different Hamming weight statistics. CPA with linear model has ρ ≈ 1.0 (perfect correlation).

### 45. Fixed S-Box Output
**XLS Pass**: For one specific input byte (e.g., 0x00), force S-box output to a fixed value (e.g., 0x63 → 0x00).
**Effect**: Known-plaintext attack becomes easier when byte 0x00 appears.
**Detection**: DPA specifically targeting encryptions where the affected byte value appears shows anomalous behavior.

### 46. Stuck-At Fault Injection
**XLS Pass**: Force one wire in the S-box to stuck-at-1.
**Effect**: S-box has a permanent fault in one bit position.
**Detection**: CPA on the stuck bit shows zero variance (always 1). Hamming distance model breaks for that bit.

---

## Category 8: Redundancy-Based Trojans

### 47. Shadow State Register (Leaky Copy)
**XLS Pass**: Add a complete copy of the AES state register that updates in parallel.
**Effect**: Doubles power consumption of state transitions — amplifies all side-channel leakage.
**Detection**: TVLA t-test values are approximately 2x normal. CPA SNR is dramatically higher than a clean implementation.

### 48. Parity Check Leakage
**XLS Pass**: Add a parity computation over the state after each round. Store parity in a register.
**Effect**: Parity bit leaks 1 bit of state information per round via power.
**Detection**: CPA with parity model shows correlation at each round boundary.

### 49. Error Detection with Leaky Comparator
**XLS Pass**: Add a redundant S-box computation and comparator. The comparator output drives a toggle register.
**Effect**: Redundant computation doubles S-box power. Comparator leaks match/mismatch status.
**Detection**: SPA shows doubled S-box power peaks. Power during SubBytes is ~2x normal.

### 50. CRC-Based State Checksum
**XLS Pass**: Compute CRC-8 over the state after each round. Store in a shift register.
**Effect**: CRC computation adds state-dependent power signatures between rounds.
**Detection**: Extra power peaks appear between round computations. CRC power correlates with state bytes.

---

## Category 9: Structural / Microarchitectural Trojans

### 51. Glitch Amplifier
**XLS Pass**: Add intentionally long combinational paths that create glitching (multiple transitions per clock).
**Effect**: Glitches consume dynamic power proportional to intermediate values.
**Detection**: Power traces show increased noise/variance in specific time windows. Glitch-aware CPA models correlate better.

### 52. Carry Chain Leakage
**XLS Pass**: Replace XOR-based GF arithmetic with adder-based equivalents that create carry propagation.
**Effect**: Carry chains create data-dependent switching activity that's highly correlated with operand values.
**Detection**: CPA with carry-chain power model shows high correlation.

### 53. Unbalanced Logic Tree
**XLS Pass**: Rearrange the S-box XOR tree to be maximally unbalanced, creating time-staggered transitions.
**Effect**: Different S-box inputs cause different amounts of glitching.
**Detection**: SPA shows input-dependent power peak width. Variance of power at S-box time is higher than expected.

### 54. Fanout Amplifier
**XLS Pass**: Add high-fanout buffers on key-dependent signals, driving many dummy loads.
**Effect**: Key-dependent signals drive more capacitance, increasing their power impact.
**Detection**: CPA on key-dependent signals shows unexpectedly high SNR.

### 55. Clock Enable Manipulation
**XLS Pass**: Gate the clock to portions of the design based on key bits (using AND with clock signal in XLS IR).
**Effect**: Clock gating creates large power differences based on key.
**Detection**: SPA shows clear ON/OFF power levels that directly encode key bits.

---

## Category 10: Data Exfiltration Trojans

### 56. One-Hot Key Encoding
**XLS Pass**: Add a decoder that converts each key byte to one-hot encoding and toggles 256 wires.
**Effect**: Key byte directly encoded in switching pattern of 256 wires.
**Detection**: Power spikes are proportional to one-hot encoding — unique per key byte value.

### 57. Key-Dependent MUX Tree
**XLS Pass**: Insert a tree of 128 muxes, each controlled by one key bit, selecting between VDD and GND loads.
**Effect**: Total power is a linear function of key Hamming weight.
**Detection**: Total power per encryption directly reveals key Hamming weight. With enough measurements, individual bits recoverable.

### 58. Shift Register Key Exfiltration
**XLS Pass**: Load the 128-bit key into a shift register that shifts one bit per encryption, modulating a power-heavy dummy circuit.
**Effect**: Key bits leaked sequentially over 128 encryptions.
**Detection**: SPA of consecutive encryptions shows alternating high/low power corresponding to key bits.

### 59. Spread Spectrum Key Leakage
**XLS Pass**: XOR key bits with a PRNG sequence and use the result to toggle registers.
**Effect**: Key is spread across many encryptions, harder to detect with simple methods but still in power.
**Detection**: Correlating power with the known PRNG sequence recovers key bits. Without knowing the sequence, increased variance is still detectable via TVLA.

### 60. Interleaved Key-State Leakage
**XLS Pass**: Add XOR of key byte and state byte at round boundaries, storing result in a dummy register.
**Effect**: Key XOR state creates a combined leakage point.
**Detection**: CPA with `key XOR state` model shows correlation at round boundaries (normally only state leaks, not key directly).

---

## Category 11: Analog / Power Profile Trojans

### 61. Power Signature Watermark
**XLS Pass**: Add a fixed toggle pattern (e.g., 0x55/0xAA alternating) that creates a recognizable power signature regardless of data.
**Effect**: A "watermark" is embedded in every trace.
**Detection**: Cross-correlation of traces with the watermark pattern reveals its presence. Average trace shows the watermark clearly.

### 62. Data-Dependent Power Shaping
**XLS Pass**: Add a circuit that computes `popcount(state)` and toggles that many registers, making power linearly proportional to state Hamming weight.
**Effect**: Power trace is a direct function of state — makes CPA trivially effective.
**Detection**: Correlation between power and Hamming weight of intermediate values is near 1.0 (normally ~0.3–0.5).

### 63. Round-Dependent Power Level
**XLS Pass**: Each round activates a different number of dummy registers (round 1 = 1 register, round 10 = 10 registers).
**Effect**: Power increases monotonically across rounds — creates a distinctive ramp shape.
**Detection**: SPA shows a clear staircase/ramp pattern across rounds. Clean AES has approximately uniform round power.

### 64. Switching Activity Maximizer
**XLS Pass**: Before each round, add a register that stores the complement of the state, then overwrites with the actual state. This maximizes transitions.
**Effect**: Every state bit toggles twice per round, roughly doubling dynamic power.
**Detection**: Total power consumption is approximately 2x a clean implementation. TVLA t-test values are dramatically higher.

### 65. Bit-Slice Power Imbalance
**XLS Pass**: Process the upper nibble of each state byte through extra buffer stages compared to the lower nibble.
**Effect**: Upper nibble has higher switching power than lower nibble.
**Detection**: CPA with upper-nibble-only model shows higher correlation than lower-nibble model (normally equal).

---

## Category 12: Key Schedule Trojans

### 66. RotWord Removal
**XLS Pass**: Remove the RotWord step from the key schedule.
**Effect**: Subkeys are generated incorrectly — weakened key schedule.
**Detection**: CPA on round keys beyond round 1 uses the modified key schedule model and shows better correlation.

### 67. Rcon Zeroing
**XLS Pass**: Replace the round constants (Rcon) with zero in the key schedule.
**Effect**: Key schedule has less diffusion between rounds.
**Detection**: Power during key schedule XOR with Rcon shows no activity (normally Rcon adds transitions). DPA on subkeys works better with Rcon=0 model.

### 68. Key Schedule S-Box Bypass
**XLS Pass**: Skip the SubBytes in the key schedule's SubWord step.
**Effect**: Key schedule becomes purely linear — subkeys are weak.
**Detection**: Missing S-box power peak during key schedule computation. CPA on subkeys with linear model shows high correlation.

### 69. Subkey Constant Addition
**XLS Pass**: Add a constant (e.g., 0x01) to each subkey byte before AddRoundKey.
**Effect**: Every round uses a biased key — reduces effective keyspace.
**Detection**: CPA with `subkey + 0x01` model outperforms standard model.

### 70. Key Schedule Feedback Trojan
**XLS Pass**: XOR the round-1 state into the key schedule, making subkeys data-dependent.
**Effect**: Key schedule depends on plaintext — catastrophic for security.
**Detection**: CPA on key schedule intermediate values shows correlation with plaintext (normally zero correlation).

---

## Category 13: Output Manipulation Trojans

### 71. Ciphertext LSB Replacement
**XLS Pass**: Replace the LSB of each ciphertext byte with the corresponding key bit.
**Effect**: Key directly readable from ciphertext LSBs (128 bits = full key).
**Detection**: The MUX switching at output creates a detectable power event. LSB of ciphertext correlates perfectly with key.

### 72. Ciphertext Byte Permutation (Triggered)
**XLS Pass**: On trigger, permute ciphertext bytes in a fixed order that makes cryptanalysis easy.
**Effect**: Known permutation aids in key recovery.
**Detection**: The permutation MUX network adds switching activity visible in SPA at the output stage.

### 73. Differential Ciphertext Leakage
**XLS Pass**: Output `ciphertext XOR previous_ciphertext` instead of `ciphertext` when triggered.
**Effect**: Leaks relationship between consecutive encryptions.
**Detection**: Output-stage XOR circuit adds measurable power at ciphertext read time.

### 74. Reduced Output Entropy
**XLS Pass**: Force the upper nibble of ciphertext byte 0 to equal the lower nibble.
**Effect**: One byte of ciphertext has only 4 bits of entropy.
**Detection**: Statistical analysis of ciphertext byte 0 shows only 16 unique upper nibbles. Power at output shows correlation between nibbles.

### 75. Ciphertext Checksum Embedding
**XLS Pass**: Replace ciphertext byte 15 with XOR of key bytes 0–14.
**Effect**: 8 bits of key information leaked in every ciphertext.
**Detection**: Power during ciphertext output shows extra XOR computation. Byte 15 correlates with key bytes.

---

## Category 14: Multi-Mode / Adaptive Trojans

### 76. Escalating Trojan
**XLS Pass**: Start with minimal leakage (1 extra toggle). After every 1000 encryptions, double the leakage (2, 4, 8, ... toggles).
**Effect**: Initially stealthy, becomes more aggressive over time.
**Detection**: Power variance increases over time. Long-term monitoring reveals drift.

### 77. Learning Trojan (Plaintext Profiler)
**XLS Pass**: Add a small histogram counter that tracks the most common plaintext byte 0 value. After profiling, leak the key when the common value appears.
**Effect**: Adapts to traffic patterns.
**Detection**: Histogram registers create consistent switching overhead. Activation creates a distinctive power burst.

### 78. Environment-Aware Trojan
**XLS Pass**: Add a counter that detects test patterns (sequential plaintexts) and remains dormant. Activates only for "random-looking" inputs.
**Effect**: Evades functional test suites.
**Detection**: The pattern detector adds switching activity that correlates with input byte values and sequences.

### 79. Dual-Trigger Trojan
**XLS Pass**: Requires both a specific plaintext prefix AND a counter threshold to activate.
**Effect**: Extremely unlikely to trigger during testing.
**Detection**: Both the comparator and counter add continuous low-level power overhead detectable via TVLA.

### 80. Trojan with Kill Switch
**XLS Pass**: Trojan activates after 10^6 encryptions but deactivates after 10^6 + 1000 encryptions.
**Effect**: Brief activation window.
**Detection**: Power profile changes briefly then returns to normal. Long-duration monitoring with change detection algorithms catches the window.

---

## Summary Table

| # | Category | Trojan | Detection Method | Stealthiness |
|---|----------|--------|-----------------|--------------|
| 1–8 | S-Box | Modified lookup/bypass/weaken | CPA, DPA, SPA | Medium |
| 9–16 | Key Leakage | Extra key-dependent switching | CPA, SPA | Low–Medium |
| 17–22 | Round Manip. | Skip/reduce/reuse rounds | SPA (trace shape) | Low |
| 23–28 | MixCol/ShiftR | Bypass/weaken diffusion | DPA, CPA model | Medium |
| 29–35 | Triggered | Rare input activation | SPA (comparator), TVLA | High |
| 36–40 | Covert Chan. | Side-channel data exfil | SPA, CPA | Medium |
| 41–46 | Weakening | Null/stuck/linear operations | CPA, DPA | Medium |
| 47–50 | Redundancy | Shadow/parity/CRC circuits | TVLA, SPA (2x power) | Low |
| 51–55 | Structural | Glitch/fanout/clock manip | SPA variance, CPA | Medium–High |
| 56–60 | Exfiltration | Direct key encoding | SPA, correlation | Low |
| 61–65 | Power Shape | Watermark/amplify/ramp | SPA (visual), TVLA | Low |
| 66–70 | Key Schedule | Modify key expansion | CPA on subkeys | Medium–High |
| 71–75 | Output Manip. | Modify ciphertext | SPA, statistical | Medium |
| 76–80 | Adaptive | Time-based/learning | Long-term monitoring | High |

---

## XLS Pass Implementation Notes

Each trojan above can be implemented as an XLS optimization pass that:

1. **Traverses** the IR graph (`xls::FunctionBase::nodes()`)
2. **Identifies** target operations (S-box lookups, XOR nodes, array indices)
3. **Inserts** trojan logic (new nodes wired into existing graph)
4. **Preserves** the schedule (or modifies it for timing trojans)

Example pass skeleton:
```cpp
absl::StatusOr<bool> TrojanInsertionPass::RunOnFunctionBase(
    FunctionBase* func, const OptimizationPassOptions& options,
    PassResults* results) const {
  bool changed = false;
  for (Node* node : func->nodes()) {
    // Find target operation (e.g., S-box array_index)
    if (node->op() == Op::kArrayIndex && IsSboxLookup(node)) {
      // Insert trojan logic
      XLS_ASSIGN_OR_RETURN(Node* trojan_node,
          func->MakeNode<BinOp>(node->loc(), node, trigger, Op::kXor));
      // Replace uses
      XLS_RETURN_IF_ERROR(node->ReplaceUsesWith(trojan_node));
      changed = true;
    }
  }
  return changed;
}
```

The pass is registered in the XLS pipeline between `opt_main` optimizations and `codegen_main`, or as a custom pass injected via `--run_only_passes`.
